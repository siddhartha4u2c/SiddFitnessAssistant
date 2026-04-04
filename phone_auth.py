"""Phone normalization (E.164) for optional profile contact; legacy placeholder usernames."""

from __future__ import annotations

import os

_PHONE_PLACEHOLDER_SUFFIX = "@phone.sidfitness.local"


def is_placeholder_login_username(username: str | None) -> bool:
    if not username:
        return False
    return str(username).lower().rstrip().endswith(_PHONE_PLACEHOLDER_SUFFIX.lower())


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
