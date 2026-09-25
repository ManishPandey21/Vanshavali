"""Account emails (verification, existing-account notice, password reset) in English and Hindi.

Plain text plus minimal HTML. No images, tracking pixels, remote resources or redirecting links.
"""

from __future__ import annotations

from html import escape
from typing import TypedDict
from urllib.parse import quote

from app.core import mailer
from app.core.config import get_settings


class _Copy(TypedDict):
    subject: str
    greeting: str
    body: list[str]
    action: str
    footer: str


def _lang(language: str | None) -> str:
    return "hi" if (language or "").lower().startswith("hi") else "en"


def link(path: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}{path}"


def verify_link(token: str, next_path: str | None = None) -> str:
    url = link(f"/verify-email/{token}")
    if next_path:
        url += f"?next={quote(next_path, safe='/')}"
    return url


def _copy(kind: str, lang: str, hours: int, minutes: int) -> _Copy:
    en: dict[str, _Copy] = {
        "verify": {
            "subject": "Confirm your email for Vanshavali",
            "greeting": "Namaste {name},",
            "body": [
                "Please confirm this email address to finish creating your Vanshavali account.",
                f"The link works once and expires in {hours} hours.",
            ],
            "action": "Confirm my email",
            "footer": "If you did not create an account, you can ignore this email; nothing will happen.",
        },
        "exists": {
            "subject": "Someone tried to register with your email",
            "greeting": "Namaste {name},",
            "body": [
                "Someone (perhaps you) tried to create a new Vanshavali account with this email address, "
                "but you already have an account.",
                "If it was you, sign in. If you have forgotten your password, you can reset it.",
            ],
            "action": "Sign in or reset your password",
            "footer": "If this wasn't you, you can ignore this email. Your account has not been changed.",
        },
        "reset": {
            "subject": "Reset your Vanshavali password",
            "greeting": "Namaste {name},",
            "body": [
                "We received a request to reset the password for your Vanshavali account.",
                f"The link works once and expires in {minutes} minutes. "
                "Resetting your password signs you out on every device.",
            ],
            "action": "Choose a new password",
            "footer": "If you did not ask for this, ignore this email; your password stays the same.",
        },
    }
    hi: dict[str, _Copy] = {
        "verify": {
            "subject": "वंशावली के लिए अपना ईमेल पुष्टि करें",
            "greeting": "नमस्ते {name},",
            "body": [
                "अपना वंशावली खाता बनाना पूरा करने के लिए कृपया इस ईमेल पते की पुष्टि करें।",
                f"यह लिंक केवल एक बार काम करता है और {hours} घंटे में समाप्त हो जाता है।",
            ],
            "action": "मेरा ईमेल पुष्टि करें",
            "footer": "अगर आपने खाता नहीं बनाया है, तो इस ईमेल को अनदेखा करें; कुछ नहीं होगा।",
        },
        "exists": {
            "subject": "किसी ने आपके ईमेल से पंजीकरण करने की कोशिश की",
            "greeting": "नमस्ते {name},",
            "body": [
                "किसी ने (शायद आपने) इस ईमेल पते से नया वंशावली खाता बनाने की कोशिश की, "
                "लेकिन आपका खाता पहले से मौजूद है।",
                "अगर यह आप थे, तो साइन इन करें। पासवर्ड भूल गए हों तो उसे रीसेट कर सकते हैं।",
            ],
            "action": "साइन इन करें या पासवर्ड रीसेट करें",
            "footer": "अगर यह आप नहीं थे, तो इस ईमेल को अनदेखा करें। आपके खाते में कोई बदलाव नहीं हुआ है।",
        },
        "reset": {
            "subject": "अपना वंशावली पासवर्ड रीसेट करें",
            "greeting": "नमस्ते {name},",
            "body": [
                "हमें आपके वंशावली खाते का पासवर्ड रीसेट करने का अनुरोध मिला है।",
                f"यह लिंक केवल एक बार काम करता है और {minutes} मिनट में समाप्त हो जाता है। "
                "पासवर्ड रीसेट करने से आप हर डिवाइस से साइन आउट हो जाएँगे।",
            ],
            "action": "नया पासवर्ड चुनें",
            "footer": "अगर आपने यह अनुरोध नहीं किया, तो इस ईमेल को अनदेखा करें; आपका पासवर्ड वही रहेगा।",
        },
    }
    return (hi if lang == "hi" else en)[kind]


def _safe_name(name: str) -> str:
    """Display names are user-chosen: keep them short and never let them carry a link."""
    name = " ".join(name.split())[:60]
    if not name or "://" in name or "www." in name.lower():
        return ""
    return name


def _render(
    kind: str, language: str | None, name: str, url: str, extra_url: str | None = None
) -> tuple[str, str, str]:
    s = get_settings()
    c = _copy(kind, _lang(language), s.email_verify_ttl_hours, s.password_reset_ttl_minutes)
    safe = _safe_name(name)
    greeting = c["greeting"].format(name=safe) if safe else c["greeting"].replace(" {name}", "")
    urls = [url, extra_url] if extra_url else [url]
    text = "\n\n".join(
        [greeting, *c["body"], f"{c['action']}:\n" + "\n".join(urls), c["footer"], "— Vanshavali"]
    )
    paras = "".join(f"<p>{escape(p)}</p>" for p in c["body"])
    html = (
        '<!doctype html><html><body style="font-family:sans-serif;line-height:1.5;color:#1f1a17">'
        f"<p>{escape(greeting)}</p>{paras}"
        f'<p><a href="{escape(url)}">{escape(c["action"])}</a></p>'
        + "".join(f'<p style="font-size:13px;color:#555">{escape(u)}</p>' for u in urls)
        + f'<p style="font-size:13px;color:#555">{escape(c["footer"])}</p>'
        f'<p style="font-size:13px;color:#555">{escape(c["footer"])}</p>'
        "<p>— Vanshavali</p></body></html>"
    )
    return c["subject"], text, html


def send_verification(
    to: str, name: str, language: str | None, token: str, next_path: str | None = None
) -> None:
    subject, text, html = _render("verify", language, name, verify_link(token, next_path))
    mailer.send(to, subject, text, html, sensitive=[token], kind="verify_email")


def send_existing_account_notice(to: str, name: str, language: str | None) -> None:
    subject, text, html = _render("exists", language, name, link("/login"), link("/forgot-password"))
    mailer.send(to, subject, text, html, kind="existing_account")


def send_password_reset(to: str, name: str, language: str | None, token: str) -> None:
    subject, text, html = _render("reset", language, name, link(f"/reset-password/{token}"))
    mailer.send(to, subject, text, html, sensitive=[token], kind="password_reset")
