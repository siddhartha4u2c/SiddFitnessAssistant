"""Send transactional email via SMTP (e.g. Gmail) or Resend HTTPS API.

Render **Free** web services block outbound **SMTP** (ports 25, 465, 587). Local dev can use
SMTP; on Render Free set **RESEND_API_KEY** + **RESEND_FROM_EMAIL** instead (HTTPS, port 443).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import smtplib
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_logger = logging.getLogger(__name__)


def _smtp_password() -> str:
    raw = os.getenv("SMTP_PASSWORD") or ""
    return raw.replace(" ", "").strip()


def smtp_configured() -> bool:
    user = (os.getenv("SMTP_USERNAME") or "").strip()
    return bool(
        (os.getenv("SMTP_SERVER") or "smtp.gmail.com").strip()
        and user
        and _smtp_password()
        and (os.getenv("MAIL_DEFAULT_SENDER") or user).strip()
    )


def resend_configured() -> bool:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    from_addr = (os.getenv("RESEND_FROM_EMAIL") or "").strip()
    return bool(key and from_addr)


def transactional_email_configured() -> bool:
    """True if either Resend (HTTPS) or SMTP can send activation/reset mail."""
    return resend_configured() or smtp_configured()


def _send_via_resend(to_address: str, subject: str, body: str) -> None:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    from_addr = (os.getenv("RESEND_FROM_EMAIL") or "").strip()
    if not key or not from_addr:
        raise RuntimeError("RESEND_API_KEY and RESEND_FROM_EMAIL must be set.")

    payload = json.dumps(
        {
            "from": from_addr,
            "to": [to_address],
            "subject": subject,
            "text": body,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Resend returns HTTP 403 / error 1010 if User-Agent is missing (urllib omits it by default).
            "User-Agent": "SID-Fitness-Assistant/1.0 (python-urllib; transactional-email)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace") if e.fp else str(e)
        raise RuntimeError(f"Resend API HTTP {e.code}: {detail}") from e
    _logger.info("Resend send OK to=%s subject=%r", to_address, subject)


def _send_transactional(to_address: str, subject: str, body: str) -> None:
    if resend_configured():
        _send_via_resend(to_address, subject, body)
    else:
        _send_smtp_plain(to_address, subject, body)


def _send_smtp_plain(to_address: str, subject: str, body: str) -> None:
    to_address = (to_address or "").strip()
    if not to_address:
        raise RuntimeError("No recipient address for email.")

    server = (os.getenv("SMTP_SERVER") or "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT") or "587")
    user = os.getenv("SMTP_USERNAME", "").strip()
    password = _smtp_password()
    sender = (os.getenv("MAIL_DEFAULT_SENDER") or user).strip()
    if not (user and password and sender):
        raise RuntimeError("SMTP is not fully configured in the environment.")

    _sl = server.lower().rstrip("/")
    if _sl.endswith("gmail.co") and not _sl.endswith("gmail.com"):
        raise RuntimeError(
            f"SMTP_SERVER is {server!r}, which is not a real host—usually a typo. "
            f"For Gmail set SMTP_SERVER=smtp.gmail.com (note the **.com**) in your .env file."
        )

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain", "utf-8"))

    _dns_err = (
        f"Cannot reach mail server {server!r}: your system could not resolve that hostname "
        f"(DNS/network). In .env set SMTP_SERVER to a valid host with no typos—e.g. "
        f"smtp.gmail.com for Gmail—and check internet access. Underlying error: {{}}"
    )

    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(sender, [to_address], msg.as_string())
        _logger.info(
            "SMTP send OK: from=%s to=%s subject=%r server=%s",
            sender,
            to_address,
            subject,
            server,
        )
    except socket.gaierror as e:
        raise RuntimeError(_dns_err.format(e)) from e
    except OSError as e:
        code = getattr(e, "errno", None)
        win = getattr(e, "winerror", None)
        if code == -2 or win in (11001, 11002, 11003) or "Name or service not known" in str(
            e
        ):
            raise RuntimeError(_dns_err.format(e)) from e
        raise


def send_password_reset_email(
    to_address: str,
    reset_url: str,
    *,
    username_hint: str | None = None,
) -> None:
    subject = "Password reset — SID Fitness Assistant"
    name_part = f" for account ({username_hint})" if username_hint else ""
    body = f"""Hello,

You requested a password reset{name_part} for the SID Fitness Assistant app.

Open this link in your browser (valid for 1 hour):

{reset_url}

If you did not request this, you can ignore this email. Your password will not change.

—
This message was sent from an automated address. Do not reply.
"""
    _send_smtp_plain(to_address, subject, body)


def send_email_verification_email(to_address: str, verify_url: str) -> None:
    subject = "Activate your account — SID Fitness Assistant"
    body = f"""Hello,

Thanks for registering with the SID Fitness Assistant app.

Open this link in your browser to activate your account (valid for 1 hour):

{verify_url}

If you did not create an account, you can ignore this email.

—
This message was sent from an automated address. Do not reply.
"""
    _send_transactional(to_address, subject, body)
