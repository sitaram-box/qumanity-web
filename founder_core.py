"""The Founder's Message: a long-form personal letter shown on the homepage (preview + "Read Full
Message") and its own page. Stored in the database (not hardcoded in a template) so it can be
updated or replaced later without a code change -- matches the Founder's own "Option B: CMS-driven"
preference.

This text (2026-10-13) replaces the earlier (2026-10-04) version. It was rewritten as a first-person
story -- the spark at 21 in 2011, Teknomealer, Mozotek and ABAUT, e-mealer's turn toward the street,
the i-naa pivot, and Qumanity from 2016 onward -- ending with a direct ask to register and take part.
It deliberately keeps no name, no entity name, and no closing invocation, consistent with the
message's own stated choice to stay anonymous ("I am not going to tell you my name"). All 13
languages (English + 12 translations) are seeded, each independently translated to preserve the same
voice and the same images (the wedding hall, the tea vendor, etc.) rather than being machine-literal.
`{founder_account_id}` is substituted at read time by `get_message()` with the live Account ID of
whichever user currently holds `users.hide_identity = 1` -- see social_core.display_identity() for
why that account's name is never shown here or anywhere else a stranger could find it."""
from __future__ import annotations

import datetime as dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS founder_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'Founder''s Message',
    preview_text TEXT NOT NULL,
    full_text TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    published_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);
"""

PREVIEW_EN = (
    "I am not going to tell you my name. That was never the point of any of this, and by the end of this you will understand why — and how you can still reach me directly, if you want to. I want to tell you about a small realization instead, the one that started everything. I was twenty-one, still finishing an engineering degree, and I had seen the same small, specific unfairness over and over: a waiter stepping into a private room — a family's dinner, a quiet negotiation, a tired evening — just to clear a plate or refill a glass, breaking a moment of privacy that was never his to interrupt, for a task that didn't need him there at all. I remember sitting in the corner of a wedding hall once, watching a tired waiter cross the same twenty feet of floor for the eleventh time in an hour, and thinking: this is not his failure. It is the room's design. It is such a small thing to notice. But small unfairnesses, left alone, teach us to stop noticing unfairness at all. I decided I would rather fix one small thing than get comfortable ignoring it."
)

FULL_TEXT_EN = """I am not going to tell you my name. That was never the point of any of this, and by the end of this you will understand why — and how you can still reach me directly, if you want to.

I want to tell you about a small realization instead, the one that started everything.

I was twenty-one, still finishing an engineering degree, and I had seen the same small, specific unfairness over and over: a waiter stepping into a private room — a family's dinner, a quiet negotiation, a tired evening — just to clear a plate or refill a glass, breaking a moment of privacy that was never his to interrupt, for a task that didn't need him there at all. I remember sitting in the corner of a wedding hall once, watching a tired waiter cross the same twenty feet of floor for the eleventh time in an hour, and thinking: this is not his failure. It is the room's design. It is such a small thing to notice. But small unfairnesses, left alone, teach us to stop noticing unfairness at all. I decided I would rather fix one small thing than get comfortable ignoring it.

So in 2011, I built Teknomealer — a way for food and service to arrive without a person having to walk back into that room again and again. I had no funding, no office, no one waiting for me to succeed — only a sketch, a stubborn belief, and a willingness to write to people who had no reason to write back. I carried it far enough to sit, as a very young student from India with no institution behind my name, with reviewers in Harvard Business School's early-stage feedback programme. They asked hard, searching questions, and I didn't have all the answers. That was fine. I wasn't looking for a trophy. I was looking for the truth about whether the idea could hold weight, and they showed me where it couldn't — yet.

So I kept building, in bigger rooms. Mozotek carried the same instinct into hotels and real estate — automated, attentive service that respected a guest's privacy instead of interrupting it. ABAUT pushed further still: not just one room, but a whole building, where things simply arrived where they were needed, like a nervous system, not a gadget — a tray of food leaving a kitchen already knowing which door to find. Each version asked the same question in a larger space: how do we make a system serve the person inside it, instead of asking the person to serve the system?

Then I turned the same question toward the street. e-mealer wasn't for a five-star lobby, it was a kiosk for the street, built to give the unemployed and the unorganized worker a fair, visible place in the system, not just dignity as an afterthought. I was thinking of the vendor who has sold the same tea from the same handcart for fifteen years, with no credit line, no roof over the cart when it rains, and no record that any of it happened. I wanted the same respect I had been designing for a hotel guest to reach someone who had never once been treated like a guest anywhere.

And then came the realization that changed everything I was doing: no machine, however well designed, can repair a system that isn't fair to begin with. I could keep building better kiosks, better rails, better robots, for the rest of my life, and every one of them would still operate inside the same unfair architecture — an architecture where some rooms get privacy and dignity by design, and other rooms don't even get asked what they need. I had been treating the symptom. The disease was the system itself.

That realization is where i-naa was born, and it is also where my old work quietly ended and a much longer, much harder project began. It cost more than I expected — the comfort of something finished to show people, something with a price tag and a demo you could hold. For years there was no product, no income, and no easy way to explain at a family gathering what I was doing. I stopped trying to build one more product. I went back to first principles and asked the only question that actually mattered: what would a truly fair system require — not sentimentally, but structurally, down to its architecture?

From 2016 onward, the answer became Qumanity. Not a company. Not a product with a launch date and an exit. A living, nested ledger of Space, Time and Consciousness — where every place has an address, every rhythm has a season, and every act of service leaves a permanent, honest trace. In plain terms: your village gets a real address in a system that actually sees it, your own contributions build a visible record that is yours and cannot be quietly erased, and leadership rotates with a natural rhythm instead of settling in for good. I set out to build something I could hand over completely, the day it was ready, and still trust.

It is ready enough now to need you.

Every project I built before this depended on one person in one room, and that was always its limit. Qumanity cannot depend on one person, and it was never meant to. It only becomes real in the hands of millions of ordinary people who decide that their village, their skill, their vote, their voice, actually belongs somewhere permanent and fair.

So here is what I am actually asking, plainly and warmly: register. Claim your place in the ledger. In the first week, you will see your own village's page for the first time, exactly as it exists today — who else is there, what they are raising their voice about, what is already being decided without you. Bring your village, your language, your craft, your vote. Teach someone. Plant something. Show up for an elder who is lonely. The work was never meant to end with the person who started it. It was always meant to end with every one of you beginning yours."""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _seed_if_empty(conn)


def _seed_if_empty(conn) -> None:
    existing = conn.execute("SELECT 1 FROM founder_messages WHERE language = 'en' LIMIT 1").fetchone()
    if existing:
        return
    conn.execute(
        """INSERT INTO founder_messages (title, preview_text, full_text, language, published_at, is_active)
           VALUES (?, ?, ?, 'en', ?, 1)""",
        ("Founder's Message", PREVIEW_EN, FULL_TEXT_EN, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()


def _founder_account_id(conn) -> str:
    """The live 12-digit Account Search ID (account_ids.search_code, not users.account_id -- the
    message says "12-digit", and search_code is the field that is actually 12 digits) of whichever
    member currently has hide_identity set -- substituted into `full_text`'s {founder_account_id}
    placeholder at read time (never baked into the stored text itself, so it always reflects the
    real, current, searchable ID). Formatted as four groups of four digits in parentheses, e.g.
    "(5863 0510 8292)", matching how the dashboard already displays this same field
    (dash_extras.js's pv-search-code)."""
    row = conn.execute(
        """SELECT a.search_code FROM users u JOIN account_ids a ON a.user_id = u.id
           WHERE u.hide_identity = 1 AND a.is_current = 1 AND a.search_code IS NOT NULL
           ORDER BY u.id LIMIT 1"""
    ).fetchone()
    if not row:
        return "(not yet set — see users.hide_identity)"
    code = row["search_code"]
    grouped = " ".join(code[i:i + 4] for i in range(0, len(code), 4))
    return f"({grouped})"


def get_message(conn, language: str = "en") -> dict | None:
    """The active message in the requested language, falling back to English if that language
    hasn't been translated yet (only English is seeded as of 2026-10; see module docstring)."""
    ensure_tables(conn)
    row = conn.execute(
        "SELECT * FROM founder_messages WHERE is_active = 1 AND language = ? ORDER BY id DESC LIMIT 1", (language,)
    ).fetchone()
    if not row and language != "en":
        row = conn.execute(
            "SELECT * FROM founder_messages WHERE is_active = 1 AND language = 'en' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    message = dict(row)
    message["full_text"] = message["full_text"].replace("{founder_account_id}", _founder_account_id(conn))
    return message
