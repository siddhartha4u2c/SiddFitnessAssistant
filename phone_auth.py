"""Phone normalization (E.164) and SMS OTP via Twilio when configured."""

from __future__ import annotations

import os
import re

_PHONE_PLACEHOLDER_SUFFIX = "@phone.sidfitness.local"


def phone_placeholder_suffix() -> str:
    return _PHONE_PLACEHOLDER_SUFFIX


def is_placeholder_login_username(username: str | None) -> bool:
    if not username:
        return False
    return str(username).lower().rstrip().endswith(_PHONE_PLACEHOLDER_SUFFIX.lower())


def synthetic_username_from_e164(e164: str) -> str:
    """Stable synthetic email-shaped username for phone-only accounts (unique in users.username)."""
    digits = re.sub(r"\D", "", e164)
    if not digits:
        digits = "0"
    return f"{digits}{_PHONE_PLACEHOLDER_SUFFIX}"


def normalize_phone_e164(raw: str, default_region: str | None = None) -> str | None:
    """Return E.164 like +919876543210 or None if invalid."""
    s = (raw or "").strip()
    if not s:
        return None
    region = (default_region or os.getenv("PHONE_DEFAULT_REGION") or "IN").strip().upper()
    try:
        import phonenumbers
        from phonenumbers.phonenumberutil import NumberParseException

        parsed = phonenumbers.parse(s, region if not s.startswith("+") else None)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except (NumberParseException, ImportError, Exception):
        return None


def _twilio_from_number() -> str:
    """Sender: TWILIO_FROM_NUMBER, or TWILIO_PHONE_NUMBER (e.g. Render), in E.164."""
    for key in ("TWILIO_FROM_NUMBER", "TWILIO_PHONE_NUMBER"):
        v = (os.getenv(key) or "").strip()
        if v:
            return v
    return ""


def sms_otp_configured() -> bool:
    return bool(
        (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
        and (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
        and (
            (os.getenv("TWILIO_MESSAGING_SERVICE_SID") or "").strip()
            or _twilio_from_number()
        )
    )


def send_otp_sms(to_e164: str, code: str) -> None:
    """Send OTP via Twilio. Raises on failure."""
    if not sms_otp_configured():
        raise RuntimeError("SMS (Twilio) is not configured.")
    from twilio.rest import Client

    sid = os.environ["TWILIO_ACCOUNT_SID"].strip()
    token = os.environ["TWILIO_AUTH_TOKEN"].strip()
    client = Client(sid, token)
    body = f"Your SID Fitness Assistant sign-in code is {code}. It expires in 10 minutes."
    ms = (os.getenv("TWILIO_MESSAGING_SERVICE_SID") or "").strip()
    from_num = _twilio_from_number()
    if ms:
        client.messages.create(messaging_service_sid=ms, to=to_e164, body=body)
    else:
        if not from_num:
            raise RuntimeError("Set TWILIO_FROM_NUMBER or TWILIO_PHONE_NUMBER (or TWILIO_MESSAGING_SERVICE_SID).")
        client.messages.create(from_=from_num, to=to_e164, body=body)
