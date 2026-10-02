"""Notification channel adapters (ADR-0016; docs/operations/notification-providers.md).

Every adapter takes an :class:`OutboundMessage` and either returns a :class:`SendResult` or raises
:class:`ProviderError` with a short code. The code (never the provider's raw response, which can
quote the recipient or the message) is what ``notification_delivery.last_error_code`` stores.

* Email: the existing mailer backends (console / file / SMTP), delivered synchronously inside the
  notification job so its outcome is recorded.
* SMS: ``mock`` (JSON outbox) or ``twilio`` (Programmable Messaging REST API).
* WhatsApp: ``mock``, ``twilio`` (WhatsApp via Twilio) or ``meta`` (WhatsApp Business Cloud API,
  pre-approved template; business-initiated messages must use a template).

Credentials come only from settings (environment / secret manager); nothing is hard-coded.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings
from app.models.enums import NotificationChannel

log = logging.getLogger("app.notifications")


@dataclass
class OutboundMessage:
    channel: NotificationChannel
    to: str  # email address or E.164 phone number
    subject: str
    text: str
    html: str | None = None
    kind: str = "reminder"
    # values used to fill a provider template (WhatsApp Cloud API); never logged
    template_params: list[str] = field(default_factory=list)


@dataclass
class SendResult:
    provider: str
    message_id: str | None = None


class ProviderError(Exception):
    def __init__(self, code: str, *, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ChannelProvider(Protocol):
    name: str

    def send(self, msg: OutboundMessage) -> SendResult: ...


def mask_phone(number: str) -> str:
    digits = number.strip()
    if len(digits) <= 6:
        return "***"
    return digits[:3] + "*" * (len(digits) - 7) + digits[-4:]


# ---------------------------------------------------------------- email
class EmailProvider:
    def __init__(self) -> None:
        self.name = f"email:{get_settings().mail_backend}"

    def send(self, msg: OutboundMessage) -> SendResult:
        from app.core import mailer

        payload = {
            "to": msg.to,
            "subject": msg.subject,
            "text": msg.text,
            "html": msg.html or "",
            "sensitive": [],
            "kind": msg.kind,
        }
        try:
            mailer.deliver(payload)
        except Exception as exc:  # the mailer already counted and logged it without content
            raise ProviderError(f"email_{type(exc).__name__}".lower()[:80]) from exc
        return SendResult(provider=self.name)


# ---------------------------------------------------------------- mock (tests, E2E, demos)
class MockProvider:
    """Writes each message as JSON into ``<notification_outbox_dir>/<channel>/`` (like the mail
    ``file`` backend). Set ``VSH_NOTIFICATION_MOCK_FAIL=<channel>`` to simulate provider failures."""

    def __init__(self, channel: NotificationChannel) -> None:
        self.channel = channel
        self.name = f"{channel.value}:mock"

    def send(self, msg: OutboundMessage) -> SendResult:
        if os.environ.get("VSH_NOTIFICATION_MOCK_FAIL") == self.channel.value:
            raise ProviderError("mock_failure")
        out = Path(get_settings().notification_outbox_dir) / self.channel.value
        out.mkdir(parents=True, exist_ok=True)
        mid = f"mock-{uuid.uuid4().hex[:12]}"
        name = f"{time.time_ns():020d}-{mid}"
        tmp = out / f".{name}.json.tmp"
        tmp.write_text(
            json.dumps({"to": msg.to, "text": msg.text, "kind": msg.kind, "id": mid}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, out / f"{name}.json")
        return SendResult(provider=self.name, message_id=mid)


# ---------------------------------------------------------------- HTTP helpers
def _post(url: str, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ProviderError("provider_url_not_https", retryable=False)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # noqa: S310 - https only
    try:
        with urllib.request.urlopen(req, timeout=get_settings().provider_timeout_seconds) as resp:  # noqa: S310
            body = resp.read(65536)
    except urllib.error.HTTPError as exc:
        # 4xx (bad number, unapproved template, auth) are not retried; 429/5xx are
        retryable = exc.code == 429 or exc.code >= 500
        raise ProviderError(f"http_{exc.code}", retryable=retryable) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError("provider_unreachable") from None
    try:
        parsed = json.loads(body or b"{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------- Twilio (SMS and WhatsApp)
class TwilioProvider:
    def __init__(self, channel: NotificationChannel) -> None:
        s = get_settings()
        self.channel = channel
        self.name = f"{channel.value}:twilio"
        sender = s.twilio_sms_from if channel == NotificationChannel.SMS else s.twilio_whatsapp_from
        if not (s.twilio_account_sid and s.twilio_auth_token and sender):
            raise ProviderError("provider_not_configured", retryable=False)
        self.sid, self.token, self.sender = s.twilio_account_sid, s.twilio_auth_token, sender
        self.base = s.twilio_api_base.rstrip("/")

    def send(self, msg: OutboundMessage) -> SendResult:
        wa = self.channel == NotificationChannel.WHATSAPP
        form = {
            "To": f"whatsapp:{msg.to}" if wa else msg.to,
            "Body": msg.text[:1500],
        }
        if self.sender.startswith("MG"):
            form["MessagingServiceSid"] = self.sender
        else:
            form["From"] = f"whatsapp:{self.sender}" if wa else self.sender
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        data = _post(
            f"{self.base}/2010-04-01/Accounts/{urllib.parse.quote(self.sid)}/Messages.json",
            urllib.parse.urlencode(form).encode(),
            {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        return SendResult(provider=self.name, message_id=str(data.get("sid") or "")[:120] or None)


# ---------------------------------------------------------------- WhatsApp Business Cloud API (Meta)
class MetaWhatsAppProvider:
    def __init__(self) -> None:
        s = get_settings()
        if not (s.whatsapp_meta_token and s.whatsapp_meta_phone_number_id):
            raise ProviderError("provider_not_configured", retryable=False)
        self.name = "whatsapp:meta"
        self.s = s

    def send(self, msg: OutboundMessage) -> SendResult:
        s = self.s
        params = msg.template_params or [msg.text[:900]]
        body = {
            "messaging_product": "whatsapp",
            "to": msg.to.lstrip("+"),
            "type": "template",
            "template": {
                "name": s.whatsapp_meta_template,
                "language": {"code": s.whatsapp_meta_template_language},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}],
            },
        }
        data = _post(
            f"{s.whatsapp_meta_api_base.rstrip('/')}/{urllib.parse.quote(str(s.whatsapp_meta_phone_number_id))}/messages",
            json.dumps(body).encode(),
            {"Authorization": f"Bearer {s.whatsapp_meta_token}", "Content-Type": "application/json"},
        )
        messages = data.get("messages") or [{}]
        mid = messages[0].get("id") if isinstance(messages[0], dict) else None
        return SendResult(provider=self.name, message_id=str(mid)[:120] if mid else None)


# ---------------------------------------------------------------- registry
def channel_available(channel: NotificationChannel) -> bool:
    s = get_settings()
    if channel == NotificationChannel.EMAIL:
        return True
    backend = s.sms_backend if channel == NotificationChannel.SMS else s.whatsapp_backend
    return backend != "disabled"


def provider_for(channel: NotificationChannel) -> ChannelProvider:
    s = get_settings()
    if channel == NotificationChannel.EMAIL:
        return EmailProvider()
    backend = s.sms_backend if channel == NotificationChannel.SMS else s.whatsapp_backend
    if backend == "disabled":
        raise ProviderError("channel_disabled", retryable=False)
    if backend == "mock":
        return MockProvider(channel)
    if backend == "twilio":
        return TwilioProvider(channel)
    return MetaWhatsAppProvider()
