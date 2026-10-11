"""
WARNING: THIS SCRIPT IS RETIRED.
It has already been run once against production. Do NOT re-run without a specific reason.
See docs/private_id_and_login.md. The founder's real Private ID and readable ID are no
longer hardcoded here (2026-10-11, ahead of this repo going public) -- set
QM_FOUNDER_PRIVATE_ID and QM_FOUNDER_READABLE_ID before running; the script exits
immediately if either is unset. The --i-know-what-im-doing guard below remains in place
regardless -- it's a safety feature against accidental re-runs, not a secrecy feature,
since a public reviewer can read this file's source either way.

Historical docstring (for reference only -- do not run casually):

One-off: give every existing user a 9-digit Private ID + 5-digit PIN.

  QM_FOUNDER_PIN=<5 digits> QM_FOUNDER_PRIVATE_ID=<9 digits> QM_FOUNDER_READABLE_ID=<readable id> \\
      python3 scripts/_retired/migrate_private_codes.py --i-know-what-im-doing

The Founder (identified by QM_FOUNDER_READABLE_ID) gets the fixed code QM_FOUNDER_PRIVATE_ID and
the PIN from QM_FOUNDER_PIN (never written to a file). Every other existing user gets a random
unique code and the development PIN 12345. Safe to re-run: users that already have a code keep it.
"""
import os
import sys
from pathlib import Path

if "--i-know-what-im-doing" not in sys.argv:
    print(__doc__)
    print(
        "Refusing to run: this script is retired. Pass --i-know-what-im-doing if you have a "
        "specific, deliberate reason to run it (QM_FOUNDER_PRIVATE_ID/QM_FOUNDER_READABLE_ID "
        "must also be set).",
        file=sys.stderr,
    )
    sys.exit(1)

FOUNDER_CODE = os.environ.get("QM_FOUNDER_PRIVATE_ID")
if not FOUNDER_CODE:
    raise SystemExit("QM_FOUNDER_PRIVATE_ID must be set to run this script")
FOUNDER_READABLE = os.environ.get("QM_FOUNDER_READABLE_ID")
if not FOUNDER_READABLE:
    raise SystemExit("QM_FOUNDER_READABLE_ID must be set to run this script")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from werkzeug.security import generate_password_hash

import app  # noqa: F401  (runs the column migration)
import id_generator
from db import get_db

DEV_PIN = "12345"

conn = get_db()
founder_pin = os.environ.get("QM_FOUNDER_PIN", "")
f = conn.execute("SELECT id, private_id_9digit FROM users WHERE private_id = ?", (FOUNDER_READABLE,)).fetchone()
if f:
    if founder_pin:
        conn.execute("UPDATE users SET private_id_9digit = ?, pin_hash = ?, pin_fails = 0, pin_locked_until = NULL WHERE id = ?",
                     (FOUNDER_CODE, generate_password_hash(founder_pin), f["id"]))
    elif not f["private_id_9digit"]:
        conn.execute("UPDATE users SET private_id_9digit = ? WHERE id = ?", (FOUNDER_CODE, f["id"]))
n = 0
for u in conn.execute("SELECT id FROM users WHERE private_id_9digit IS NULL").fetchall():
    conn.execute("UPDATE users SET private_id_9digit = ?, pin_hash = ? WHERE id = ?",
                 (id_generator.generate_private_code(conn), generate_password_hash(DEV_PIN), u["id"]))
    conn.commit(); n += 1
conn.commit()
print(f"founder set: {bool(f)}; new codes issued: {n}")
