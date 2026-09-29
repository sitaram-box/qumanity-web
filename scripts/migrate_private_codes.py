"""One-off: give every existing user a 9-digit Private ID + 5-digit PIN.

  QM_FOUNDER_PIN=<5 digits> python3 scripts/migrate_private_codes.py

The Founder (readable ID FIM-RM-GMA2-ZFL-CS.DL.1.A.12) gets the fixed code 014918240 and the PIN from QM_FOUNDER_PIN
(never written to a file). Every other existing user gets a random unique code and the development PIN 12345.
Safe to re-run: users that already have a code keep it.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werkzeug.security import generate_password_hash

import app  # noqa: F401  (runs the column migration)
import id_generator
from db import get_db

FOUNDER_READABLE = "FIM-RM-GMA2-ZFL-CS.DL.1.A.12"
FOUNDER_CODE = "014918240"
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
