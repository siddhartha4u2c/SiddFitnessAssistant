"""Google OAuth 2.0 (web) for Streamlit. Configure env vars; redirect URI must match Google Console."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def redirect_uri_resolved() -> str:
    u = (os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if u:
        return u
    base = (
        os.getenv("PASSWORD_RESET_APP_URL") or os.getenv("APP_BASE_URL") or ""
    ).strip().rstrip("/")
    if base:
        return f"{base}/"
    return ""


def is_configured() -> bool:
    return bool(
        (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        and (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
        and redirect_uri_resolved()
    )


def _flow(redirect_uri: str):
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=_SCOPES,
        redirect_uri=redirect_uri,
    )


def authorization_url(state: str) -> str:
    redirect_uri = redirect_uri_resolved()
    flow = _flow(redirect_uri)
    url, _ = flow.authorization_url(
        access_type="online",
        include_granted_scopes="true",
        prompt="select_account",
        state=state,
    )
    return url


def exchange_code_for_userinfo(code: str) -> dict:
    redirect_uri = redirect_uri_resolved()
    flow = _flow(redirect_uri)
    flow.fetch_token(code=code)
    token = flow.credentials.token
    req = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"userinfo HTTP {e.code}: {body}") from e
