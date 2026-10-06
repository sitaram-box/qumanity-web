"""Recovering access: a forgotten PIN (self-service, by OTP) and a forgotten 9-digit Private ID
(never self-service -- the ID is a login credential, so it only ever leaves the system as a
physical letter the Founder's team prepares by hand after checking the requester's identity).

No SMS/email provider is wired up yet (Spark-plan / no Twilio-Sendgrid key), so OTP delivery is
SIMULATED: the code is generated and hashed exactly as a real one would be, but "sending" it just
logs it server-side (see app.py's QM_DEV_SHOW_OTP switch) until a provider is connected.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS otp_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    channel TEXT NOT NULL,          -- phone | email
    purpose TEXT NOT NULL DEFAULT 'pin_reset',
    code_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS id_recovery_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, dob TEXT NOT NULL, birth_country TEXT, birth_state TEXT,
    phone TEXT, email TEXT, mailing_address TEXT NOT NULL, note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | matched | sent | rejected
    candidate_user_id INTEGER,
    admin_note TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS id_recovery_reveals (
    request_id INTEGER NOT NULL,
    revealed_by INTEGER NOT NULL,
    revealed_at TEXT NOT NULL
);
"""


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


# ---- PIN reset by OTP (phone or email already on file) ----

def request_pin_reset(conn, private_code: str, channel: str):
    """Returns (ok, message_or_dev_code). Only a phone or email already on the account can be used,
    matching the founder's rule that the Private ID itself is never recovered this way."""
    ensure_tables(conn)
    if channel not in ("phone", "email"):
        raise ValueError("Choose phone or email")
    user = conn.execute("SELECT id, phone, email FROM users WHERE private_id_9digit = ?", (private_code,)).fetchone()
    if not user or not user[channel]:
        # deliberately the same message whether the ID is unknown or just has no such contact on file,
        # so a guesser can't use this to test which 9-digit IDs exist
        return False, f"No account with that Private ID and a registered {channel} was found."
    code = f"{secrets.randbelow(1_000_000):06d}"
    conn.execute(
        "INSERT INTO otp_requests (user_id, channel, code_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (user["id"], channel, _hash(code), (_now() + dt.timedelta(minutes=OTP_TTL_MINUTES)).isoformat(), _now().isoformat()),
    )
    conn.commit()
    masked = (user[channel][:2] + "…" + user[channel][-2:]) if len(user[channel]) > 4 else "…"
    return True, {"masked_target": masked, "dev_code": code}  # dev_code is stripped by the route unless QM_DEV_SHOW_OTP is on


def verify_pin_reset(conn, private_code: str, otp: str, new_pin: str):
    import re
    # Item 5: kept in sync with app.py's PIN_RE / PIN_FORMAT_ERROR -- 5 chars, at least one
    # letter or digit, not all special characters.
    if not re.fullmatch(
        r"""^(?=.*[A-Za-z0-9])[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;:'",.<>/?]{5}$""",
        new_pin or "",
    ):
        raise ValueError(
            "PIN must be 5 characters. It can include numbers, letters, or special "
            "characters — but not all special characters."
        )
    user = conn.execute("SELECT id FROM users WHERE private_id_9digit = ?", (private_code,)).fetchone()
    if not user:
        raise ValueError("Incorrect code")
    row = conn.execute(
        "SELECT * FROM otp_requests WHERE user_id = ? AND purpose = 'pin_reset' AND consumed_at IS NULL ORDER BY id DESC LIMIT 1",
        (user["id"],),
    ).fetchone()
    if not row or row["expires_at"] < _now().isoformat():
        raise ValueError("That code has expired — request a new one")
    if row["attempts"] >= OTP_MAX_ATTEMPTS:
        raise ValueError("Too many attempts — request a new code")
    if row["code_hash"] != _hash((otp or "").strip()):
        conn.execute("UPDATE otp_requests SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        conn.commit()
        raise ValueError("Incorrect code")
    from werkzeug.security import generate_password_hash
    conn.execute("UPDATE otp_requests SET consumed_at = ? WHERE id = ?", (_now().isoformat(), row["id"]))
    conn.execute("UPDATE users SET pin_hash = ?, pin_fails = 0, pin_locked_until = NULL WHERE id = ?", (generate_password_hash(new_pin), user["id"]))
    conn.commit()


# ---- Private ID recovery: intake + a manual, admin-mediated reveal ----

def submit_id_recovery(conn, data: dict) -> int:
    ensure_tables(conn)
    required = ["name", "dob", "mailing_address"]
    missing = [f for f in required if not (data.get(f) or "").strip()]
    if missing:
        raise ValueError(f"Missing: {', '.join(missing)}")
    if not (data.get("phone") or "").strip() and not (data.get("email") or "").strip():
        raise ValueError("Give us a phone number or an email so we can reach you")
    try:
        dt.date.fromisoformat(data["dob"])
    except ValueError:
        raise ValueError("Date of birth must be a valid date")

    name = data["name"].strip()
    dob = data["dob"].strip()
    birth_country = (data.get("birth_country") or "").strip()
    birth_state = (data.get("birth_state") or "").strip()

    candidates = []
    for u in conn.execute("SELECT id, name, dob, birth_location_json FROM users WHERE dob = ? AND lower(name) = lower(?)", (dob, name)):
        import json
        loc = json.loads(u["birth_location_json"])
        if birth_country and (loc.get("country") or {}).get("id") != birth_country and (loc.get("country") or {}).get("code") != birth_country:
            continue
        if birth_state and (loc.get("state") or {}).get("id") != birth_state:
            continue
        candidates.append(u["id"])

    status = "matched" if len(candidates) == 1 else "pending"
    candidate_user_id = candidates[0] if len(candidates) == 1 else None
    cur = conn.execute(
        """INSERT INTO id_recovery_requests (name, dob, birth_country, birth_state, phone, email, mailing_address, note, status, candidate_user_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, dob, birth_country or None, birth_state or None, (data.get("phone") or "").strip() or None,
         (data.get("email") or "").strip() or None, data["mailing_address"].strip(), (data.get("note") or "").strip() or None,
         status, candidate_user_id, _now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def list_requests(conn, status=None):
    ensure_tables(conn)
    q = "SELECT * FROM id_recovery_requests"
    args = ()
    if status:
        q += " WHERE status = ?"
        args = (status,)
    q += " ORDER BY id DESC"
    return [dict(r) for r in conn.execute(q, args)]


def decide_request(conn, admin_id, request_id, status, admin_note=None):
    if status not in ("matched", "sent", "rejected", "pending"):
        raise ValueError("Unknown status")
    row = conn.execute("SELECT * FROM id_recovery_requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        raise LookupError("Request not found")
    conn.execute("UPDATE id_recovery_requests SET status = ?, admin_note = ?, decided_at = ? WHERE id = ?",
                 (status, (admin_note or "").strip() or None, _now().isoformat(), request_id))
    conn.commit()


def reveal_private_code(conn, admin_id, request_id):
    """The one place the system will show someone ELSE's 9-digit Private ID -- to the Founder's own
    team, only for a matched recovery request, only so they can write it into the physical letter.
    Every reveal is logged."""
    row = conn.execute("SELECT candidate_user_id FROM id_recovery_requests WHERE id = ?", (request_id,)).fetchone()
    if not row or not row["candidate_user_id"]:
        raise ValueError("This request has no matched account yet")
    user = conn.execute("SELECT private_id_9digit FROM users WHERE id = ?", (row["candidate_user_id"],)).fetchone()
    conn.execute("INSERT INTO id_recovery_reveals (request_id, revealed_by, revealed_at) VALUES (?, ?, ?)", (request_id, admin_id, _now().isoformat()))
    conn.commit()
    return user["private_id_9digit"] if user else None
