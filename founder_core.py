"""Qumanity Story: the long-form origin story shown on the homepage (preview + "Read Full
Story") and its own page. Stored in the database (not hardcoded in a template) so it can be
updated or replaced later without a code change.

This text (2026-10-15) replaces the earlier first-person "Founder's Message" version entirely.
It is told as the story of Qumanity itself -- the world problem it responds to, then
Teknomealer (2011), Mozotek and ABAUT, e-mealer's turn toward the street, and Qumanity from 2016
onward -- closing with what Qumanity means for the world and a direct invitation to register.
Written with zero first-person pronouns (no "I"/"my"/"me") and no personal anecdote: this is
Qumanity's story, not one person's letter. It mentions no name, no entity name, no Account
Search ID or other personal identifier, and no closing invocation.

English only: no translations are seeded. `_seed_or_refresh()` writes only the 'en' row.
"""
from __future__ import annotations

import datetime as dt
import os

import board_core

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
CREATE UNIQUE INDEX IF NOT EXISTS idx_founder_messages_language
    ON founder_messages(language);
"""

PREVIEW_EN = (
    'This is the story of Qumanity — a story about an idea that started small and grew into something much bigger. All over the world, people often feel unseen: work goes unrecognized, voices go unheard, and the trust between people and the systems meant to serve them keeps quietly breaking down.'
)

FULL_TEXT_EN = """This is the story of Qumanity — a story about an idea that started small and grew into something much bigger. It begins with a simple problem: all over the world, people often feel unseen. Some work goes unrecognized. Some voices never get heard. Some places are forgotten the moment anyone stops paying attention. And underneath all of it, trust between people, communities, and the systems meant to serve them keeps quietly breaking down. Long before Qumanity became what it is today, it started as one small attempt to fix a tiny piece of that much larger problem. It is a problem as old as civilization itself, yet most of the systems built to fix it were never designed to last, or to include everyone equally.

The first idea came in 2011. It was called Teknomealer, and it tried to solve something very specific: how food and service could reach people without interrupting private, personal moments that deserved to be left alone. There was no company behind it, no funding, no office — just an idea, a simple sketch, and the determination to try anyway. That idea was even reviewed by experts in Harvard Business School's early-stage feedback programme. They asked tough, searching questions, and not every answer was ready yet. But that was fine. The goal was never to win a prize. It was to find out whether the idea was strong enough to stand on its own — and it was, just not quite ready yet.

So the idea kept growing. Next came Mozotek, which brought the same thinking into hotels and real estate — service that respected people's privacy instead of interrupting it. Then came ABAUT, which pushed the idea even further: instead of just one room, it worked across an entire building, quietly making sure things arrived exactly where they were needed, like a living nervous system instead of a single gadget. Every version asked the same question, just on a bigger scale: how can a system serve people, instead of making people serve the system?

Then the idea turned to one of the hardest problems of all: the street. e-mealer was built for people who are too often overlooked — unemployed workers, street vendors, people with no steady income and no official record of their work. It was designed with someone very real in mind: a tea seller who has sold tea from the same small cart for fifteen years, with no loan, no shelter from the rain, and no record anywhere that any of that work ever happened. e-mealer tried to give people like this the same fairness and visibility that a five-star hotel guest would expect, because everyone deserves that, not just a few.

But each of these ideas solved only one piece of a much bigger puzzle — one room, one group, one place at a time. They were useful, even meaningful, but none of them, on their own, could fix something as big as a village, a country, or a planet. It became clear that another product would not be enough, however clever or well designed. What was needed was not another app or gadget. It was something far bigger: a foundation that everyone could stand on, together, no matter where they started from.

That is how Qumanity was born in 2016. Not as a company, and not as a product with a launch date and an exit. Qumanity is a living record — a ledger — that keeps track of place, time, and human effort, fairly and permanently. In simple terms: every village gets a real address in a system that actually sees it. Every person's contribution becomes part of a visible, lasting record that cannot be quietly erased. And leadership changes hands naturally over time, instead of staying in one place forever.

The world does not lack good intentions. What it lacks is a way to make those intentions last — a system where fairness is not just a promise that can be broken by whoever is in charge next, but something built into how a place, a community, and the planet keep track of themselves, year after year.

This is what Qumanity is built to do. Where there is inequality, it gives everyone's contribution equal weight — visible to all, erasable by none. Where there is instability, leadership rotates naturally over time instead of being held onto by force. Where there is conflict, there is one shared, honest record that everyone can see, instead of two sides arguing over two different versions of the truth. And where people feel disconnected — from their village, their country, or the planet they share with millions of others — Qumanity gives them something simple but powerful: proof that they belong somewhere real.

None of this solves every problem on its own, and it was never meant to. But it creates a strong foundation — something future generations can build on, instead of starting from zero, the way every generation before them had to. Every small, honest, visible act of fairness adds up over time. This is how trust gets rebuilt: not through one big moment, but through millions of small ones, repeated, generation after generation, until it simply becomes how things work. And slowly, steadily, this is how a whole planet moves toward something bigger: a shared, collective rise in awareness, peace, equality, stability, and genuine care for one another. None of it requires anyone to wait for permission — it only requires enough people deciding, together, that this is the world worth building.

So here is the invitation, simple and honest: register. Claim your place in this growing record. In your very first week, you will see your own village's page for the first time — who is already there, what they care about, and what decisions are already being made, with or without you. Bring your language, your skills, your voice. Teach someone something. Plant something that will outlast you. Stand beside someone who feels alone. This story was never meant to end with the people who started it. It was always meant to continue with everyone who joins."""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _seed_or_refresh(conn)


def _seed_or_refresh(conn) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO founder_messages (title, preview_text, full_text, language, published_at, is_active)
           VALUES (?, ?, ?, 'en', ?, 1)""",
        ("Qumanity Story", PREVIEW_EN, FULL_TEXT_EN, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()


# ---- Empty-village welcome post (2026-10-28, "first impression" upgrade) -----------------------
# A village with nobody posting yet reads as broken, not quiet -- board_core.board_view()'s own
# `empty_prompt` field (computed in board_view(), not here) is what actually fixes that feeling in
# the UI; this function is the separate, permanent half of the same fix: one real board_posts row
# per village, so the village's own record isn't literally empty the first time anyone opens it.
# post_kind='council_update' (board_core.create_council_update()) -- reaction-only, never enters
# the vote/threshold/reward pipeline, exactly like a real council's own announcements.
WELCOME_POST_TEXT = (
    "Welcome to your village's own page. Every post here is voted on by the people who live here "
    "— seven days of votes decide whether it climbs to the Tehsil and beyond, or stays here as "
    "part of your village's own record. Nothing is posted for you. Be the first to propose a "
    "change in your village."
)


def _resolve_author(conn) -> int | None:
    """The one account QM_ADMIN_PRIVATE_IDS actually names (same env var _is_admin() in app.py
    reads, read directly here rather than threading an author_id through every caller) -- None
    when the env var is unset or empty (local dev's placeholder value, or a DB with no matching
    user yet), in which case seed_welcome_post() below is a no-op rather than guessing an author."""
    allowed = [pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()]
    if not allowed:
        return None
    qmarks = ",".join("?" * len(allowed))
    row = conn.execute(f"SELECT id FROM users WHERE private_id_9digit IN ({qmarks}) ORDER BY id LIMIT 1", allowed).fetchone()
    return row["id"] if row else None


def seed_welcome_post(conn, present_location: dict, level: str = "village", now: dt.datetime | None = None) -> int | None:
    """Idempotent (content-keyed, not a new column -- the exact WELCOME_POST_TEXT match at this
    group_id/level is itself the "already seeded" check, so re-calling this on every empty-board
    view is safe and cheap). Village-only: Tehsil and above are paid, elevation-only pages with no
    "be the first" framing to seed (board_core.board_view()'s own empty_prompt is village-only for
    the same reason). Returns the new post's id, or None if nothing was created (no admin resolved,
    no group at this level, or already seeded)."""
    if level != "village":
        return None
    author_id = _resolve_author(conn)
    if author_id is None:
        return None
    chain = board_core.chain_of(present_location)
    g = board_core.group_for(chain, level)
    if not g:
        return None
    already = conn.execute(
        "SELECT 1 FROM board_posts WHERE group_id = ? AND level = ? AND post_kind = 'council_update' AND content = ? LIMIT 1",
        (g["id"], level, WELCOME_POST_TEXT),
    ).fetchone()
    if already:
        return None
    return board_core.create_council_update(conn, author_id, present_location, WELCOME_POST_TEXT, level=level, now=now)


def get_message(conn, language: str = "en") -> dict | None:
    """The active message in the requested language, falling back to English if that language
    hasn't been translated yet (English only, as of 2026-10-15; see module docstring)."""
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
    return dict(row)
