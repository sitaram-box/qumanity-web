"""One-time rotation of the founder's Private ID.

Runs on app boot only when ROTATE_FOUNDER_ID=1 is set in the environment.
After it runs once, remove this file, the import in app.py, and the
ROTATE_FOUNDER_ID variable on Railway.

Column: users.private_id_9digit (app.py:103), unique index idx_users_code.
Founder row: id=24, name='Rohit Mudgal' (docs/phase_2_5_fix_report.md:43).

The old leaked value is NOT embedded anywhere in this file. The rotation
is by row identity, not by matching the secret. The log prints the length
of the old value only, never the value itself.
"""

import os
import secrets
import sqlite3

COLUMN = "private_id_9digit"
FOUNDER_ID = 24
FOUNDER_NAME = "Rohit Mudgal"
MAX_TRIES = 10


def _log(msg):
    print(f"[rotate_founder_id] {msg}", flush=True)


def _new_9digit():
    return "".join(secrets.choice("0123456789") for _ in range(9))


def rotate():
    db_path = os.environ.get("QM_DB_PATH", "./qumanity.db")

    if not os.path.exists(db_path):
        _log(f"DB not found at {db_path} - skipping")
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        cur.execute(
            f"SELECT id, name, {COLUMN} FROM users WHERE id = ? AND name = ?",
            (FOUNDER_ID, FOUNDER_NAME),
        )
        row = cur.fetchone()

        if row is None:
            _log(f"No user found with id={FOUNDER_ID} AND name={FOUNDER_NAME!r}. "
                 f"Nothing changed.")
            return

        user_id, name, old_id = row
        _log(f"Found user id={user_id} name={name!r}. "
             f"Old {COLUMN} length={len(old_id or '')}.")

        new_id = None
        for attempt in range(1, MAX_TRIES + 1):
            candidate = _new_9digit()
            cur.execute(f"SELECT 1 FROM users WHERE {COLUMN} = ?", (candidate,))
            if cur.fetchone() is None:
                new_id = candidate
                _log(f"Generated a unique new ID after {attempt} try/tries.")
                break

        if new_id is None:
            _log(f"No non-colliding ID in {MAX_TRIES} tries. Nothing changed.")
            return

        cur.execute(
            f"UPDATE users SET {COLUMN} = ? WHERE id = ? AND name = ?",
            (new_id, user_id, name),
        )
        conn.commit()

        cur.execute(f"SELECT {COLUMN} FROM users WHERE id = ?", (user_id,))
        check = cur.fetchone()[0]

        if check == new_id:
            _log("========================================")
            _log(f"ROTATED. New Private ID for {name!r}: {new_id}")
            _log("Save this now. It will not be shown again.")
            _log("========================================")
        else:
            _log(f"Update did not stick. Expected {new_id!r}, found {check!r}.")

    finally:
        conn.close()


if __name__ == "__main__":
    if os.environ.get("ROTATE_FOUNDER_ID") == "1":
        rotate()
    else:
        _log("ROTATE_FOUNDER_ID not set - doing nothing.")
