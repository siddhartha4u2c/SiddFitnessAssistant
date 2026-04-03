"""Resolve Gemini API key and optional proxy base URL from the environment."""

from __future__ import annotations

import os

# Official EURI gateway (OpenAI-compatible). Override with env **BASE_URL** if needed.
EURI_DEFAULT_BASE_URL = "https://api.euron.one/api/v1/euri"


def resolve_gemini_credentials() -> tuple[str, str | None]:
    """Return (api_key, base_url_or_none).

    If **EURI_API_KEY** is set, use Euron's OpenAI-compatible API. **BASE_URL** defaults to
    :data:`EURI_DEFAULT_BASE_URL` when unset. Set **BASE_URL** explicitly for another gateway.

    Otherwise **GEMINI_API_KEY** is used with Google's default Gemini endpoint (base None).

    Raises **ValueError** if configuration is missing or inconsistent.
    """
    euri = (os.getenv("EURI_API_KEY") or "").strip()
    base = (os.getenv("BASE_URL") or "").strip().rstrip("/")
    gem = (os.getenv("GEMINI_API_KEY") or "").strip()

    if euri:
        if not base:
            base = EURI_DEFAULT_BASE_URL.rstrip("/")
        return euri, base
    if gem:
        return gem, None
    raise ValueError(
        "No API key: set EURI_API_KEY (optional BASE_URL; defaults to Euron EURI), "
        "or set GEMINI_API_KEY for Google."
    )


def resolve_image_api_credentials() -> tuple[
    tuple[str, str | None],
    tuple[str | None, str | None],
]:
    """((primary_key, primary_base), (fallback_key, fallback_base)) for image calls.

    Primary follows :func:`resolve_gemini_credentials`. Fallback is **GEMINI_API_KEY**
    on Google's default endpoint when it differs from the primary key (invalid-key retry).
    """
    key, base = resolve_gemini_credentials()
    gem = (os.getenv("GEMINI_API_KEY") or "").strip()
    if base is not None and gem and gem != key:
        return (key, base), (gem, None)
    return (key, base), (None, None)
