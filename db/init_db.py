#!/usr/bin/env python3
"""Create (or update) the prototype SQLite DB and seed zodiac reference data.

Usage:
    python3 db/init_db.py
"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "qumanity_prototype.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    print("Schema applied to", DB_PATH)

    import seed_zodiac_data
    seed_zodiac_data.seed(conn)

    n_signs = conn.execute("SELECT COUNT(*) FROM zodiac_signs").fetchone()[0]
    n_nakshatras = conn.execute("SELECT COUNT(*) FROM nakshatras").fetchone()[0]
    print(f"Seeded {n_signs} zodiac signs, {n_nakshatras} nakshatras")

    conn.close()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
