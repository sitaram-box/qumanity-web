"""SQLite connection helper for the prototype DB."""

import os
import sqlite3
from pathlib import Path

# QM_DB_PATH overrides this for a real deployment -- e.g. a path inside a Railway Volume, so the
# database survives redeploys (the container filesystem itself is ephemeral). Unset, it stays
# exactly as before: a file next to this repo, for local dev.
DB_PATH = Path(os.environ["QM_DB_PATH"]) if os.environ.get("QM_DB_PATH") else Path(__file__).resolve().parent / "qumanity_prototype.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
