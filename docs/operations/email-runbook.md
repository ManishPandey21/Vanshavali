# Email runbook

Registration, email verification, password reset and "someone tried to register with your
address" notices all depend on email (ADR-0005). An email outage blocks new users and locked-out
users, but no data is ever at risk.

## How email works
- **Path:** an API request queues a job. The worker builds a plain-text + HTML message and
  delivers it over SMTP: STARTTLS with certificate verification, then AUTH (`app/core/mailer.py`).
- **Responses never reveal delivery:** API answers are identical whether or not a message was sent
  or delivered (no account enumeration). A delivery failure never fails the user's request.
- **Retries:**
  - A failed delivery is retried by the worker after **1, 5 and 15 minutes**
    (`mailer.RETRY_INTERVALS_S`), via RQ's scheduler, which `python -m app.cli.worker` runs.
  - After the third retry the job lands in the failed registry, kept for 7 days.
  - A verification link stays valid for 48 h and a reset link for 60 min, so a short outage
    loses nothing. A long one means the user asks for a new link ("Resend verification",
    "Forgot password").
- **What logs show:** each failed attempt logs `email (<kind>) to=r***@domain delivery attempt
  failed: <ExceptionType>` and increments `vsh_events_total{event="mail_delivery_failed"}`.
  - No message body, subject, full address or SMTP reply text is logged.
  - Tokens never appear in logs: RQ job descriptions name the function only (fixed in this
    milestone; previously the worker log carried the recipient and subject).
  - The `console` backend redacts tokens outside development.
- **Alert:** `EmailDeliveryFailing` fires when more than 3 failures occur in 30 minutes
  (`docs/operations/monitoring-alerting.md`).

## Configuration (production)
In `/etc/vanshavali/app.env`:
```
VSH_SMTP_HOST=<provider submission host>   # e.g. email-smtp.ap-south-1.amazonaws.com
VSH_SMTP_PORT=587
VSH_SMTP_USER=<SMTP username>
VSH_SMTP_PASSWORD=<SMTP password>
VSH_MAIL_FROM=Vanshavali <no-reply@example.org>
```
`compose.yml` fixes `VSH_MAIL_BACKEND=smtp`.

**Start-up guards:** production refuses to start with:
- any other mail backend;
- no host;
- STARTTLS off;
- a `@localhost` sender.

Port 465 (implicit TLS) is not supported; use 587.

**Sender domain (before go-live; DNS at the domain's registrar):**
1. **SPF:** a TXT record authorising the provider, e.g. `v=spf1 include:amazonses.com -all`.
2. **DKIM:** the CNAME/TXT records the provider generates for the domain.
3. **DMARC:** start with `v=DMARC1; p=quarantine; rua=mailto:dmarc@example.org`, then `p=reject`
   once reports are clean.
4. If the provider starts accounts in a sandbox (e.g. SES), request production access before
   go-live.
5. Use a bounce/complaint address the team reads. Set it up with the provider's own
   notification feature.

**Credentials:** provider SMTP credentials allowed to send, and nothing else. Rotation is in
`docs/security/secrets-management.md`.

## Test procedure
Run on the VM after any change to email settings, and as part of go-live:
```bash
cd /opt/vanshavali && source deploy/pilot/scripts/lib.sh
# 1. connect, STARTTLS (certificate verified), log in; sends nothing
dc --profile tools run --rm tools python -m app.cli.mail_check
# 2. deliver one content-free message to a mailbox you can read
dc --profile tools run --rm tools python -m app.cli.mail_check --send-to ops@example.org
```
- **Output:** one `[PASS]`/`[FAIL]` line per step, with settings printed and the password shown
  as `set`. Exit status 0 means every step passed.
- **In the received message:** check the headers for `spf=pass`, `dkim=pass` and `dmarc=pass`, and
  that it did not land in spam.
- **End to end (go-live checklist):**
  1. Register a new account through the UI with a real mailbox.
  2. The verification email arrives within a minute (both Hindi and English, depending on the
     language chosen).
  3. The link signs you in.
  4. Request a password reset; the reset email arrives and works.
  5. `vsh_events_total{event="mail_delivery_failed"}` did not move.

The staging drill (`deploy/pilot/drill/run-drill.sh`, phase B) does the same automatically
against an SMTP sink that **requires** STARTTLS:
- registration;
- the worker delivers over STARTTLS;
- the drill follows the link from the received message.

## Common failures

| Symptom | Likely cause | Check | Fix |
|---|---|---|---|
| `mail_check`: `[FAIL] SMTP: ConnectionRefusedError` / `TimeoutError` | Wrong host/port, or outbound 587 blocked by the cloud provider (some block SMTP by default) | `nc -vz $VSH_SMTP_HOST 587` from the VM | Fix the host/port, or ask the provider to lift the egress restriction |
| `SSLCertVerificationError` | The host name doesn't match the certificate (e.g. an IP was used), or an intercepting proxy | `openssl s_client -starttls smtp -connect host:587 -servername host` | Use the provider's DNS name |
| `SMTPAuthenticationError 535` | Wrong or rotated credentials; for SES, IAM keys used instead of SMTP credentials | `mail_check` | Regenerate SMTP credentials; update app.env; restart backend and worker (`dc up -d`) |
| `SMTPSenderRefused` / `554 Message rejected: Email address is not verified` | Sender domain not verified, or account still in sandbox | Provider console | Verify the domain; request production access |
| Accepted, but users don't receive it | Spam placement, or SPF/DKIM/DMARC failing | Headers of a test message (`Authentication-Results`) | Fix the DNS records; warm up gradually |
| `EmailDeliveryFailing` alert, everything above OK | Provider outage or rate limit (`SMTPDataError 454 Throttling`) | Worker logs: `docker compose logs worker \| grep delivery` | Wait (retries cover ~20 min); raise the provider's sending quota |
| No email and no failure counted | Worker not running, or Redis down (job never ran) | `vsh_workers`, `vsh_jobs_queued`, `vsh_queue_up` | Start or restart the worker / Redis (incident runbook) |
| `mail_send_failed` events | The job could not be queued (Redis unreachable from the API) | `JobQueueUnreachable` alert | Restore Redis; users can resend |

## Recovery after an outage
1. Fix the cause, then confirm with `mail_check --send-to`.
2. Re-queue failed email jobs that are less than 48 h old.
   - Their arguments hold verification links; re-queueing does not create new tokens.
   - Command:
     ```bash
     dc exec worker python -c "
     import redis; from rq import Queue; from rq.registry import FailedJobRegistry
     from app.core.config import get_settings as s
     q = Queue(s().job_queue_name, connection=redis.Redis.from_url(s().redis_url))
     reg = FailedJobRegistry(queue=q)
     ids = [j for j in reg.get_job_ids() if q.fetch_job(j) and q.fetch_job(j).description == 'app.core.mailer.deliver']
     for j in ids: reg.requeue(j)
     print(f'requeued {len(ids)} email job(s)')"
     ```
3. For anything older, users click "Resend verification" or "Forgot password". The support
   answer is in the pilot plan's support section.
4. Note the window in the incident log. If the outage exceeded 48 h, verification links expired:
   tell affected pilot users to request a new link.
