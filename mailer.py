"""Send transactional email via SMTP (e.g. Gmail)."""

from __future__ import annotations

import logging
import os
import socket
import smtplib
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
    _send_smtp_plain(to_address, subject, body)
