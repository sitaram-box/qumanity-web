"""Adds users.hide_marquee (2026-10-28): a "hide the poems marquee" preference, set by the small
Hide button on the marquee bar itself (see app.py's POST /api/marquee/hide and static/js/
poems.js). 0 (default) means the marquee shows normally subject to the member's own
religion_belief (migrations/031_religion_belief.py); 1 means api_poems_meta always reports
{"hidden": true} for this member regardless of religion_belief, and home.html's own symbol
(RELIGION_HOME_SYMBOLS in app.py) is suppressed too. Reversible from Private Account settings
(POST /api/marquee/show, 2026-10-28 revision) -- the original cut of this feature made it
one-way; the brief was clarified to want a toggle, not a permanent dismissal."""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "hide_marquee" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN hide_marquee INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    print("    users.hide_marquee ready (default 0 -- marquee shown).")
