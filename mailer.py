"""Send transactional email via SMTP (e.g. Gmail)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _smtp_password() -> str:
    raw = os.getenv("SMTP_PASSWORD") or ""
    return raw.replace(" ", "").strip()


def smtp_configured() -> bool:
    return bool(
        os.getenv("SMTP_SERVER")
        and os.getenv("SMTP_USERNAME")
        and _smtp_password()
        and (os.getenv("MAIL_DEFAULT_SENDER") or os.getenv("SMTP_USERNAME"))
    )


def send_login_otp_email(to_address: str, code: str) -> None:
    """Send a short-lived sign-in code (same SMTP config as password reset)."""
    server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT") or "587")
    user = os.getenv("SMTP_USERNAME", "").strip()
    password = _smtp_password()
    sender = (os.getenv("MAIL_DEFAULT_SENDER") or user).strip()
    if not (user and password and sender):
        raise RuntimeError("SMTP is not fully configured in the environment.")

    subject = "Your sign-in code — SID Fitness Assistant"
    body = f"""Hello,

Your one-time sign-in code is:

{code}

It expires in 10 minutes. If you did not request this, you can ignore this email.

—
This message was sent from an automated address. Do not reply.
"""
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(server, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.sendmail(sender, [to_address], msg.as_string())


def send_password_reset_email(
    to_address: str,
    reset_url: str,
    *,
    username_hint: str | None = None,
) -> None:
    server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT") or "587")
    user = os.getenv("SMTP_USERNAME", "").strip()
    password = _smtp_password()
    sender = (os.getenv("MAIL_DEFAULT_SENDER") or user).strip()
    if not (user and password and sender):
        raise RuntimeError("SMTP is not fully configured in the environment.")

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
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(server, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.sendmail(sender, [to_address], msg.as_string())
