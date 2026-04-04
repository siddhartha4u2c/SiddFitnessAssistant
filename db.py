"""SQLite persistence for users, profiles, weight/meal logs, and coach chat."""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from passlib.hash import bcrypt

import phone_auth

_LOGIN_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.IGNORECASE)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
PROFILE_IMAGES_DIR = DATA_DIR / "profile_images"


def _bcrypt_secret(password: str) -> str:
    """Bcrypt only accepts secrets up to 72 bytes; normalize longer UTF-8 passwords."""
    raw = password.encode("utf-8")
    if len(raw) <= 72:
        return password
    return hashlib.sha256(raw).hexdigest()


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
        _ensure_user_columns(conn)
        _ensure_goal_tracking_table(conn)
        _ensure_daily_activities_table(conn)


def _ensure_user_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "google_sub" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub "
            "ON users(google_sub) WHERE google_sub IS NOT NULL"
        )
    if "phone_e164" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN phone_e164 TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_e164 "
            "ON users(phone_e164) WHERE phone_e164 IS NOT NULL "
            "AND length(trim(phone_e164)) > 0"
        )


def _ensure_daily_activities_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS daily_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            activity_date TEXT NOT NULL,
            kind TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_daily_activities_user_date
            ON daily_activities (user_id, activity_date DESC, id DESC);
        """
    )


_ACTIVITY_KINDS = frozenset({"exercise", "meal_food", "other"})


def add_daily_activity(user_id: int, activity_date: str, kind: str, notes: str) -> None:
    """Log one calendar-day activity (exercise, meal/food, or other). ``activity_date`` YYYY-MM-DD."""
    notes = (notes or "").strip()
    if not notes:
        return
    k = (kind or "other").strip().lower()
    if k not in _ACTIVITY_KINDS:
        k = "other"
    day = (activity_date or "").strip()[:10]
    if len(day) < 10:
        return
    try:
        day_d = date.fromisoformat(day)
    except ValueError:
        return
    if day_d > date.today():
        return
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO daily_activities (user_id, activity_date, kind, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, day, k, notes, _utc_now_iso()),
        )


def list_daily_activities(user_id: int, days_back: int = 90) -> list[dict[str, Any]]:
    """Newest calendar days first; within a day, newest id first."""
    start = (datetime.now(timezone.utc).date() - timedelta(days=max(1, days_back))).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, activity_date, kind, notes, created_at FROM daily_activities
            WHERE user_id = ? AND activity_date >= ?
            ORDER BY activity_date DESC, id DESC
            """,
            (user_id, start),
        ).fetchall()
    return [dict(r) for r in rows]


def list_daily_activities_on_date(user_id: int, activity_date: str) -> list[dict[str, Any]]:
    """All entries for one calendar day (oldest first within the day)."""
    day = (activity_date or "").strip()[:10]
    if len(day) < 10:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, activity_date, kind, notes, created_at FROM daily_activities
            WHERE user_id = ? AND activity_date = ?
            ORDER BY id ASC
            """,
            (user_id, day),
        ).fetchall()
    return [dict(r) for r in rows]


def _ensure_goal_tracking_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS goal_tracking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            recorded_at TEXT NOT NULL,
            source TEXT NOT NULL,
            primary_goal_at_time TEXT DEFAULT '',
            body_weight_kg REAL,
            height_feet REAL,
            coach_notes_excerpt TEXT DEFAULT '',
            detail TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_goal_tracking_user_time
            ON goal_tracking_events (user_id, recorded_at DESC);
        """
    )


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
    """Register; login_email is stored in users.username."""
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
                "INSERT INTO users (username, password_hash, phone_e164, created_at) VALUES (?, ?, ?, ?)",
                (login_email, ph, None, _utc_now_iso()),
            )
        return True, "Account created. You can sign in with your email and password."
    except sqlite3.IntegrityError:
        return False, "That email is already registered."


def get_user_id_by_phone_e164(e164: str) -> int | None:
    if not (e164 or "").strip():
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE phone_e164 = ?", (e164.strip(),)
        ).fetchone()
    return int(row["id"]) if row else None


def verify_user(login_email: str, password: str) -> int | None:
    login_email = normalize_login_email(login_email)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            (login_email,),
        ).fetchone()
    if row is None:
        return None
    if not bcrypt.verify(_bcrypt_secret(password), row["password_hash"]):
        return None
    return int(row["id"])


def verify_user_identifier(login: str, password: str) -> int | None:
    """Sign in with email + password only."""
    s = (login or "").strip()
    if not s or "@" not in s:
        return None
    if not is_valid_login_email(s):
        return None
    return verify_user(s, password)


def update_user_login_email(user_id: int, new_email: str) -> tuple[bool, str]:
    """Set real sign-in email (e.g. phone-first user adds Gmail)."""
    new_email = normalize_login_email(new_email)
    if not new_email:
        return False, "Enter an email address."
    if not is_valid_login_email(new_email):
        return False, "Please enter a valid email address."
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (new_email, user_id),
            )
    except sqlite3.IntegrityError:
        return False, "That email is already in use."
    upsert_profile(user_id, {"email": new_email})
    return True, ""


def set_user_phone_e164(user_id: int, phone_raw: str | None) -> tuple[bool, str]:
    """Update mobile on file; must stay unique. Empty clears if allowed."""
    raw = (phone_raw or "").strip()
    if not raw:
        un = get_username(user_id)
        if phone_auth.is_placeholder_login_username(un or ""):
            return (
                False,
                "Add a sign-in email in your profile before removing your mobile number.",
            )
        with get_conn() as conn:
            conn.execute("UPDATE users SET phone_e164 = NULL WHERE id = ?", (user_id,))
        return True, ""
    e164 = phone_auth.normalize_phone_e164(raw)
    if not e164:
        return False, "Invalid phone number format."
    other = get_user_id_by_phone_e164(e164)
    if other is not None and other != user_id:
        return False, "That phone number is already used by another account."
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE users SET phone_e164 = ? WHERE id = ?",
                (e164, user_id),
            )
    except sqlite3.IntegrityError:
        return False, "That phone number is already in use."
    return True, ""


def get_user_phone_e164(user_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT phone_e164 FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None or row["phone_e164"] is None:
        return None
    s = str(row["phone_e164"]).strip()
    return s if s else None


def display_login_email_for_profile(user_id: int) -> str:
    """Empty when account is phone-placeholder (user should add real email)."""
    u = get_username(user_id)
    if not u:
        return ""
    if phone_auth.is_placeholder_login_username(u):
        return ""
    return u


def is_phone_placeholder_account(user_id: int) -> bool:
    return phone_auth.is_placeholder_login_username(get_username(user_id))


def sign_in_or_register_google(
    *, email: str, google_sub: str, full_name: str | None
) -> tuple[int | None, str | None]:
    """Find or create user from Google OIDC. Links google_sub to an existing email if unlinked."""
    email = normalize_login_email(email)
    if not is_valid_login_email(email):
        return None, "Google did not return a valid email address."
    gsub = (google_sub or "").strip()
    if not gsub:
        return None, "Invalid Google account identifier."

    unusable_pw_hash = bcrypt.hash(_bcrypt_secret(secrets.token_urlsafe(48)))
    fn = (full_name or "").strip()

    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE google_sub = ?", (gsub,)
            ).fetchone()
            if row:
                uid = int(row["id"])
            else:
                row = conn.execute(
                    "SELECT id, google_sub FROM users WHERE username = ? COLLATE NOCASE",
                    (email,),
                ).fetchone()
                if row:
                    prev = row["google_sub"]
                    if (
                        prev
                        and str(prev).strip()
                        and str(prev).strip() != gsub
                    ):
                        return None, "This email is already linked to a different Google account."
                    conn.execute(
                        "UPDATE users SET google_sub = ? WHERE id = ?",
                        (gsub, int(row["id"])),
                    )
                    uid = int(row["id"])
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO users (username, password_hash, google_sub, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (email, unusable_pw_hash, gsub, _utc_now_iso()),
                    )
                    uid = int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None, "Could not link your Google account (conflict)."

    p = get_profile(uid)
    fields: dict[str, Any] = {"email": email}
    if fn and not (p.get("full_name") or "").strip():
        fields["full_name"] = fn
    upsert_profile(uid, fields)
    return uid, None


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
    """Password reset inbox: real sign-in email, else profile email (not phone-placeholder username)."""
    login = get_username(user_id)
    if login and "@" in login and not phone_auth.is_placeholder_login_username(login):
        return login.strip()
    pe = get_profile_email(user_id)
    return pe.strip() if pe else None


def resolve_user_for_password_reset(identifier: str) -> tuple[int | None, str | None]:
    """Match sign-in email or profile email; reset only if we have an email destination."""
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
    ph = bcrypt.hash(_bcrypt_secret(new_password))
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
        urow = conn.execute(
            "SELECT phone_e164 FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    d: dict[str, Any] = dict(row) if row else {}
    if urow and urow["phone_e164"]:
        pe = str(urow["phone_e164"]).strip()
        if pe:
            d["phone_e164"] = pe
    if "phone_e164" not in d:
        d["phone_e164"] = None
    return d


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
    """Return messages oldest-first for UI (user turn, then coach reply). Same-second pairs need id tie-break."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at FROM chat_messages
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    chronological = list(reversed(rows))
    return [dict(r) for r in chronological]


def _user_message_suggests_goal(text: str) -> bool:
    """Lightweight filter so routine chat does not flood the goal timeline."""
    t = (text or "").strip().lower()
    if len(t) < 10:
        return False
    phrases = (
        "my goal",
        "primary goal",
        "i want to lose",
        "i want to gain",
        "want to lose",
        "want to gain",
        "trying to lose",
        "trying to gain",
        "trying to build",
        "aim to lose",
        "aim to gain",
        "aiming to lose",
        "aiming to gain",
        "target weight",
        "goal weight",
        "lose weight",
        "gain weight",
        "build muscle",
        "fat loss",
        "lose fat",
        "cutting phase",
        "bulking",
        "by summer",
        "by winter",
        "by spring",
        "by fall",
        "by january",
        "by february",
        "by march",
        "by april",
        "by may",
        "by june",
        "by july",
        "by august",
        "by september",
        "by october",
        "by november",
        "by december",
        " lose 5",
        " lose 10",
        " lose 15",
        " gain 5",
        " gain 10",
        " kg by",
        " lbs by",
        " pounds by",
        " kilos by",
        "reach my",
        "get to ",
        "get down to",
        "i hope to",
        "i'd like to lose",
        "i'd like to gain",
    )
    return any(p in t for p in phrases)


def add_goal_tracking_event(
    user_id: int,
    *,
    source: str,
    detail: str,
    primary_goal_at_time: str = "",
    body_weight_kg: float | None = None,
    height_feet: float | None = None,
    coach_notes_excerpt: str = "",
) -> None:
    src = (source or "").strip().lower()
    if src not in ("profile", "chat"):
        src = "chat"
    det = (detail or "").strip()
    if not det:
        return
    cn = (coach_notes_excerpt or "").strip()
    if len(cn) > 500:
        cn = cn[:497] + "..."
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO goal_tracking_events (
                user_id, recorded_at, source, primary_goal_at_time,
                body_weight_kg, height_feet, coach_notes_excerpt, detail
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                _utc_now_iso(),
                src,
                (primary_goal_at_time or "").strip()[:200],
                body_weight_kg,
                height_feet,
                cn,
                det[:4000],
            ),
        )


def record_profile_primary_goal_change(
    user_id: int,
    old_goal: str | None,
    new_goal: str | None,
    *,
    body_weight_kg: float | None,
    height_feet: float | None,
    coach_notes: str = "",
) -> None:
    old = (old_goal or "").strip()
    new = (new_goal or "").strip()
    if old == new:
        return
    cn_ex = (coach_notes or "").strip()
    detail = (
        f"Primary goal in profile: '{old or '(not set)'}' → '{new or '(cleared)'}'."
    )
    add_goal_tracking_event(
        user_id,
        source="profile",
        detail=detail,
        primary_goal_at_time=new,
        body_weight_kg=body_weight_kg,
        height_feet=height_feet,
        coach_notes_excerpt=cn_ex,
    )


def record_chat_goal_mention_if_relevant(user_id: int, user_message: str) -> None:
    if not _user_message_suggests_goal(user_message):
        return
    p = get_profile(user_id)
    bw = p.get("body_weight_kg")
    hf = p.get("height_feet")
    try:
        bwf = float(bw) if bw is not None else None
    except (TypeError, ValueError):
        bwf = None
    try:
        hff = float(hf) if hf is not None else None
    except (TypeError, ValueError):
        hff = None
    pg = (p.get("primary_goal") or "").strip()
    msg = (user_message or "").strip()
    if len(msg) > 1200:
        msg = msg[:1197] + "..."
    detail = f'User wrote in coach chat: "{msg}"'
    add_goal_tracking_event(
        user_id,
        source="chat",
        detail=detail,
        primary_goal_at_time=pg,
        body_weight_kg=bwf,
        height_feet=hff,
        coach_notes_excerpt=(p.get("coach_notes") or "").strip()[:500],
    )


def list_goal_tracking_events(user_id: int, limit: int = 40) -> list[dict[str, Any]]:
    """Oldest-first within the window (latest ``limit`` rows by time)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, recorded_at, source, primary_goal_at_time,
                   body_weight_kg, height_feet, coach_notes_excerpt, detail
            FROM goal_tracking_events
            WHERE user_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    rev = list(reversed(rows))
    return [dict(r) for r in rev]
