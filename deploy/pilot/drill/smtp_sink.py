"""SMTP sink for the staging drill: STARTTLS required, AUTH accepted, each message saved to /mail."""

import asyncio
import ssl
import time
import uuid
from pathlib import Path

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult


class Sink:
    async def handle_DATA(self, server, session, envelope):  # noqa: N802 - aiosmtpd hook name
        if not session.ssl:
            return "530 Must issue a STARTTLS command first"
        name = f"{time.time_ns()}-{uuid.uuid4().hex[:6]}.eml"
        Path("/mail", name).write_bytes(envelope.original_content or envelope.content)
        return "250 OK"


def authenticator(server, session, envelope, mechanism, auth_data):
    return AuthResult(success=bool(session.ssl))  # credentials only over TLS


ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ctx.load_cert_chain("/drill/smtp.crt", "/drill/smtp.key")
Controller(
    Sink(),
    hostname="0.0.0.0",
    port=587,
    server_hostname="smtp",
    tls_context=ctx,
    require_starttls=True,
    authenticator=authenticator,
    auth_require_tls=True,
).start()
print("smtp sink listening on :587 (STARTTLS required)", flush=True)
asyncio.get_event_loop().run_forever()
