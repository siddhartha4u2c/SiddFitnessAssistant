"""Send transactional email via SMTP (e.g. Gmail) or Resend HTTPS API.

Render **Free** web services block outbound **SMTP** (ports 25, 465, 587). Local dev can use
SMTP; on Render Free set **RESEND_API_KEY** + **RESEND_FROM_EMAIL** instead (HTTPS, port 443).
"""

from __future__ import annotations

import html as html_module
import json
import logging
import os
import socket
import smtplib
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

_logger = logging.getLogger(__name__)


def build_transactional_link(base_url: str, **query: str) -> str:
    """Build ``https://host/?key=value`` with correct encoding (safe for email clients)."""
    root = (base_url or "").strip().rstrip("/")
    if not root:
        root = "http://localhost:8501"
    q = urlencode(query)
    # Explicit "/" before "?" avoids rare 404s where proxies treat host?query as a non-root path.
    return f"{root}/?{q}"


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


def _format_resend_api_error(http_code: int, body: str) -> str:
    """Turn Resend JSON errors into clearer messages for the UI."""
    raw = (body or "").strip()
    if http_code == 403 and raw.startswith("{"):
        try:
            data = json.loads(raw)
            msg = (data.get("message") or raw).strip()
            if "only send testing emails to your own" in msg.lower():
                return (
                    f"{msg} "
                    "Fix: add and verify your domain at https://resend.com/domains , then set "
                    "**RESEND_FROM_EMAIL** to an address on that domain (e.g. noreply@yourdomain.com). "
                    "Until then, Resend only delivers test mail to the email tied to your Resend account."
                )
            return f"Resend API HTTP {http_code}: {msg}"
        except json.JSONDecodeError:
            pass
    return f"Resend API HTTP {http_code}: {raw}"


def _send_via_resend(
    to_address: str,
    subject: str,
    body_plain: str,
    *,
    body_html: str | None = None,
) -> None:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    from_addr = (os.getenv("RESEND_FROM_EMAIL") or "").strip()
    if not key or not from_addr:
        raise RuntimeError("RESEND_API_KEY and RESEND_FROM_EMAIL must be set.")

    payload_obj: dict = {
        "from": from_addr,
        "to": [to_address],
        "subject": subject,
        "text": body_plain,
    }
    if body_html:
        payload_obj["html"] = body_html
    payload = json.dumps(payload_obj).encode("utf-8")
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
        raise RuntimeError(_format_resend_api_error(e.code, detail)) from e
    _logger.info("Resend send OK to=%s subject=%r", to_address, subject)


def _send_transactional(
    to_address: str,
    subject: str,
    body_plain: str,
    *,
    body_html: str | None = None,
) -> None:
    if resend_configured():
        _send_via_resend(to_address, subject, body_plain, body_html=body_html)
    else:
        _send_smtp_plain(to_address, subject, body_plain, body_html=body_html)


def _send_smtp_plain(
    to_address: str,
    subject: str,
    body: str,
    *,
    body_html: str | None = None,
) -> None:
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

    msg = MIMEMultipart("alternative") if body_html else MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

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
    href = html_module.escape(reset_url, quote=True)
    name_html = (
        f" for account ({html_module.escape(username_hint)})"
        if username_hint
        else ""
    )
    body_html = (
        f"<p>Hello,</p><p>You requested a password reset{name_html} for the SID Fitness Assistant app.</p>"
        f'<p><a href="{href}">Set a new password</a> (valid for 1 hour).</p>'
        f"<p>If you did not request this, you can ignore this email.</p>"
    )
    _send_transactional(to_address, subject, body, body_html=body_html)


def send_email_verification_email(to_address: str, verify_url: str) -> None:
    subject = "Confirm your email — SID Fitness Assistant"
    body = f"""Hello,

Thank you for creating an account with SID Fitness Assistant.

To finish setup, open the secure link below in your browser (one time only). It expires in 1 hour:

{verify_url}

After you confirm, you will return to the app’s sign-in page to log in with your email and password.

If you did not register, you can ignore this message.

—
SID Fitness Assistant · Automated message · Do not reply
"""
    href = html_module.escape(verify_url, quote=True)
    body_html = (
        "<p>Hello,</p>"
        "<p>Thank you for creating an account with <strong>SID Fitness Assistant</strong>.</p>"
        "<p>To finish setup, use the button below. The link is valid for <strong>1 hour</strong> and "
        "opens the app so you can sign in.</p>"
        f'<p style="margin:24px 0;"><a href="{href}" style="display:inline-block;padding:12px 20px;'
        "background-color:#1d4ed8;color:#ffffff;text-decoration:none;border-radius:8px;"
        'font-weight:600;">Confirm email &amp; continue</a></p>'
        "<p style=\"font-size:14px;color:#444;\">Or copy and paste this address into your browser:<br/>"
        f'<span style="word-break:break-all;">{href}</span></p>'
        "<p style=\"font-size:14px;color:#444;\">If you did not register, you can ignore this email.</p>"
        "<p style=\"font-size:12px;color:#888;\">SID Fitness Assistant · Automated message · Do not reply</p>"
    )
    _send_transactional(to_address, subject, body, body_html=body_html)
