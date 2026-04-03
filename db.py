"""SQLite persistence for users, profiles, weight/meal logs, and coach chat."""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from passlib.hash import bcrypt

_LOGIN_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.IGNORECASE)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
PROFILE_IMAGES_DIR = DATA_DIR / "profile_images"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                full_name TEXT DEFAULT '',
                email TEXT DEFAULT '',
                diet_pattern TEXT DEFAULT '',
                cuisine_preferences TEXT DEFAULT '',
                meal_timing_notes TEXT DEFAULT '',
                foods_to_avoid TEXT DEFAULT '',
                allergy_alerts TEXT DEFAULT '',
                health_conditions TEXT DEFAULT '',
                medication_supplement_notes TEXT DEFAULT '',
                lifestyle_work_pattern TEXT DEFAULT '',
                lifestyle_exercise_freq TEXT DEFAULT '',
                sleep_hours_avg REAL,
                alcohol_caffeine_notes TEXT DEFAULT '',
                primary_goal TEXT DEFAULT '',
                country_or_region TEXT DEFAULT '',
                coach_notes TEXT DEFAULT '',
                gender TEXT DEFAULT '',
                body_weight_kg REAL,
                height_feet REAL,
                activity_level TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weight_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                recorded_at TEXT NOT NULL,
                weight_kg REAL NOT NULL,
                source_unit TEXT NOT NULL,
                raw_value REAL NOT NULL,
                bmr_at_log INTEGER,
                tdee_at_log INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_weight_user_time
                ON weight_entries (user_id, recorded_at DESC);

            CREATE TABLE IF NOT EXISTS meal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                logged_at TEXT NOT NULL,
                description_snippet TEXT DEFAULT '',
                model_response TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_meal_user_time
                ON meal_entries (user_id, logged_at DESC);

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_user_time
                ON chat_messages (user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_password_reset_token_hash
                ON password_reset_tokens (token_hash);
            """
        )
        _ensure_profile_columns(conn)


def _ensure_profile_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
    if "country_or_region" not in cols:
        conn.execute(
            "ALTER TABLE profiles ADD COLUMN country_or_region TEXT DEFAULT ''"
        )
    if "gender" not in cols:
        conn.execute("ALTER TABLE profiles ADD COLUMN gender TEXT DEFAULT ''")
    if "body_weight_kg" not in cols:
        conn.execute("ALTER TABLE profiles ADD COLUMN body_weight_kg REAL")
    if "height_feet" not in cols:
        conn.execute("ALTER TABLE profiles ADD COLUMN height_feet REAL")
    if "activity_level" not in cols:
        conn.execute("ALTER TABLE profiles ADD COLUMN activity_level TEXT DEFAULT ''")


def profile_image_path(user_id: int) -> Path:
    return PROFILE_IMAGES_DIR / f"{user_id}.jpg"


def has_profile_image(user_id: int) -> bool:
    return profile_image_path(user_id).is_file()


def remove_profile_image(user_id: int) -> None:
    p = profile_image_path(user_id)
    if p.is_file():
        p.unlink()


def normalize_login_email(email: str) -> str:
    return email.strip().lower()


def is_valid_login_email(email: str) -> bool:
    return bool(_LOGIN_EMAIL_RE.match(email.strip()))


def create_user(login_email: str, password: str) -> tuple[bool, str]:
    """Register; login_email is stored in users.username (legacy column name)."""
    login_email = normalize_login_email(login_email)
    if not login_email:
        return False, "Please enter your email address."
    if not is_valid_login_email(login_email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    ph = bcrypt.hash(password)
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (login_email, ph, _utc_now_iso()),
            )
        return True, "Account created. You can sign in."
    except sqlite3.IntegrityError:
        return False, "That email is already registered."


def verify_user(login_email: str, password: str) -> int | None:
    login_email = normalize_login_email(login_email)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            (login_email,),
        ).fetchone()
    if row is None:
        return None
    if not bcrypt.verify(password, row["password_hash"]):
        return None
    return int(row["id"])


def get_username(user_id: int) -> str | None:
    """Sign-in email (stored in users.username)."""
    with get_conn() as conn:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    return str(row["username"]) if row else None


def get_user_id_by_login_email(login_email: str) -> int | None:
    login_email = normalize_login_email(login_email)
    if not login_email:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
            (login_email,),
        ).fetchone()
    return int(row["id"]) if row else None


def get_user_id_by_username(username: str) -> int | None:
    """Alias: login identifier is email (users.username)."""
    return get_user_id_by_login_email(username)


def get_user_id_by_profile_email(email: str) -> int | None:
    normalized = email.strip().lower()
    if not normalized:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM profiles
            WHERE lower(trim(email)) = ? AND trim(coalesce(email, '')) != ''
            """,
            (normalized,),
        ).fetchone()
    return int(row["user_id"]) if row else None


def get_profile_email(user_id: int) -> str | None:
    p = get_profile(user_id)
    e = (p.get("email") or "").strip()
    return e if e else None


def get_delivery_email(user_id: int) -> str | None:
    """Where to send password reset: profile email if set, otherwise sign-in email."""
    pe = get_profile_email(user_id)
    if pe:
        return pe.strip()
    login = get_username(user_id)
    if login and "@" in login:
        return login.strip()
    return None


def resolve_user_for_password_reset(identifier: str) -> tuple[int | None, str | None]:
    """Match sign-in email or profile email; return destination inbox for the reset link."""
    raw = identifier.strip()
    if not raw:
        return None, None
    uid = get_user_id_by_login_email(raw)
    if uid is None:
        uid = get_user_id_by_profile_email(raw)
    if uid is None:
        return None, None
    dest = get_delivery_email(uid)
    return (uid, dest) if dest else (None, None)


def _hash_reset_token(token_plain: str) -> str:
    return hashlib.sha256(token_plain.strip().encode("utf-8")).hexdigest()


def create_password_reset_token(user_id: int) -> str:
    token_plain = secrets.token_urlsafe(32)
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    exp_s = exp.replace(microsecond=0).isoformat()
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ? AND used_at IS NULL",
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO password_reset_tokens
                (user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, _hash_reset_token(token_plain), exp_s, _utc_now_iso()),
        )
    return token_plain


def verify_reset_token(token_plain: str) -> int | None:
    if not token_plain or len(token_plain.strip()) < 20:
        return None
    h = _hash_reset_token(token_plain)
    now = _utc_now_iso()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM password_reset_tokens
            WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
            """,
            (h, now),
        ).fetchone()
    return int(row["user_id"]) if row else None


def mark_reset_token_used(token_plain: str) -> None:
    h = _hash_reset_token(token_plain)
    with get_conn() as conn:
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
            (_utc_now_iso(), h),
        )


def update_user_password(user_id: int, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters."
    ph = bcrypt.hash(new_password)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (ph, user_id),
        )
    return True, "Password updated."


def get_profile(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return {}
    return dict(row)


def upsert_profile(user_id: int, fields: dict[str, Any]) -> None:
    now = _utc_now_iso()
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if exists is None:
            cols = ["user_id", "updated_at"] + list(fields.keys())
            placeholders = ", ".join("?" * len(cols))
            vals = [user_id, now] + [fields[k] for k in fields]
            conn.execute(
                f"INSERT INTO profiles ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        else:
            sets = ", ".join(f"{k} = ?" for k in fields.keys())
            vals = [fields[k] for k in fields.keys()] + [now, user_id]
            conn.execute(
                f"UPDATE profiles SET {sets}, updated_at = ? WHERE user_id = ?",
                vals,
            )


def add_weight_entry(
    user_id: int,
    weight_kg: float,
    source_unit: str,
    raw_value: float,
    bmr_at_log: int | None = None,
    tdee_at_log: int | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO weight_entries (
                user_id, recorded_at, weight_kg, source_unit, raw_value,
                bmr_at_log, tdee_at_log
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                _utc_now_iso(),
                weight_kg,
                source_unit,
                raw_value,
                bmr_at_log,
                tdee_at_log,
            ),
        )


def list_weight_entries(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM weight_entries
            WHERE user_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def add_meal_entry(
    user_id: int, description_snippet: str, model_response: str
) -> None:
    text = model_response if len(model_response) <= 12000 else model_response[:12000]
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO meal_entries (user_id, logged_at, description_snippet, model_response)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, _utc_now_iso(), description_snippet[:2000], text),
        )


def list_meal_entries(user_id: int, limit: int = 15) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM meal_entries
            WHERE user_id = ?
            ORDER BY logged_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def add_chat_message(user_id: int, role: str, content: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (user_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, role, content, _utc_now_iso()),
        )


def list_chat_messages(user_id: int, limit: int = 40) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content, created_at FROM chat_messages
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    chronological = list(reversed(rows))
    return [dict(r) for r in chronological]
