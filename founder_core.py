"""The Founder's Message: a long-form personal letter shown on the homepage (preview + "Read Full
Message") and its own page. Stored in the database (not hardcoded in a template) so it can be
updated or replaced later without a code change -- matches the Founder's own "Option B: CMS-driven"
preference, scoped down to what this prototype actually needs (no multi-message admin UI exists
yet, so `is_active` just marks the one current message; `language` lets a future pass add real
translations of the FULL text without a schema change, though only English is seeded for now --
see docs/founders_message_2026_10.md for why the full text isn't translated into all 12 languages
yet, only its homepage preview is).

This text (2026-10-04) was written fresh at the Founder's own request -- the sample they originally
pasted is a REFERENCE for tone/structure, not the published text: "create founder's message on your
own... which i shared with you can be used for reference." It keeps the same closing (जय श्री राम /
Jai Hind / Jai Humanity) and the same 15-years-alone origin story, but is otherwise original
writing, written to center the pain of poor and helpless people, of animals who have no voice in
any of this, and of a damaged Earth -- and to end with a real, working way to actually reach the
Founder (their 12-digit Account Search ID), not just a sentiment. `{founder_account_id}` is
substituted at read time by `get_message()` with the live Account ID of whichever user currently
holds `users.hide_identity = 1` -- see social_core.display_identity() for why that account's name
is never shown here or anywhere else a stranger could find it."""
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
    "I have watched a mother skip her own meal so her child could eat, and a farmer stare at a "
    "drought-cracked field he can no longer afford to sow. I have watched a street dog flinch from "
    "every hand because not one of them has ever been kind. I am not writing to sell you anything. "
    "I am writing because I am done watching."
)

FULL_TEXT_EN = """## For Every Human Being on Earth, and Every Creature Who Cannot Speak

## A Message from the Founder

I am not going to introduce myself. My name does not matter here — you will see why, and you will see how you can still reach me directly, by the end of this letter.
What matters is what I have seen, and what I can no longer stay silent about.

I have watched a mother quietly serve everyone else first, and call her own empty plate "not hungry."
I have watched a farmer, whose grain feeds a hundred strangers, stand in a bank queue to beg for a loan he will spend the rest of his life repaying.
I have watched an old man sit alone in a house his own children paid for, but never found time to visit.
I have watched a child walk two hours to a school with no roof, while men in air-conditioned rooms decide, without ever meeting that child, that there is "no budget."
And I have watched a dog — hungry, limping, harmless — flinch at a raised hand, because every hand it has ever known has hurt it, not fed it.

I am writing this not as a company, not as a government, not as a religion. One human being, to another. This message was written by a human mind, with a human's grief and a human's stubborn hope — not generated, not outsourced, not delegated. I needed you to know that before you read one more line.

## The World We Were Handed

None of us chose this world. We were simply born into it — already unequal, already unkind, already on fire in ways no one was putting out.

We inherited a world where a river can be poisoned in an afternoon by one factory, and take forty years and a thousand lawsuits to begin to heal.
A world where a forest older than every government on Earth can be cleared in a week for a parking lot.
A world where the animals who shaped our oldest stories — the cow, the elephant, the tiger, the sparrow that no longer visits our windows — are being pushed out of the only home they have ever had, by a species that calls itself civilized.
A world where "developed" and "developing" are just polite words for who gets to pollute first and who is told to wait.
A world where a handful of people, who will never meet the billions their decisions touch, hold more power than kings ever did — without a king's accountability to anyone.
A world where corruption is not the exception that proves the system works. It IS the system, running exactly as designed, just not as advertised.

This is not cynicism. I wish it were. I would rather be wrong about all of this than right.

## The Fire That Would Not Let Me Rest

For fifteen years, one question has sat in my chest like a coal that never cools: why does every system that promises to save us eventually learn to feed on us instead?

Monarchy promised order, and became tyranny.
Democracy promised a voice for every citizen, and became an auction for whoever can buy the most attention.
Capitalism promised that effort would be rewarded, and became a machine that rewards whoever already has the most.
Every revolution, every ideology, every sacred text turned into law — all of them began with someone's genuine love for people, and all of them, eventually, were captured by someone's love of power instead.

I do not say this to despair. I say it because I had to understand WHY, before I could build something that would not repeat it.

And here is what I found: every one of those systems was built for a slower world — a world of paper, of distance, of trust you could only extend to people you had actually met. We do not live in that world anymore. We live in a world where information moves at the speed of light, where a line of code can move more wealth in a second than a village sees in a lifetime, and where our oldest institutions are still trying to govern this new world with tools built for the old one.

That gap — between how fast the world now moves, and how slowly our systems of trust have kept up — is where the suffering lives. It is where the farmer's debt lives. It is where the stray dog's hunger lives. It is where the river's poison lives. It is where a corrupt official's untouchable comfort lives.

I could not close that gap by shouting about it. So, in silence, with no funding, no team, and no one asking me to, I started trying to build something that could.

## What I Built, Alone, in the Dark

For fifteen years I worked without an audience. No investors to impress, no team to manage, no stage to perform on — just a quiet, sometimes exhausting, sometimes joyful argument with myself about what a fair system would actually have to look like if we were honest about building one from zero.

What came out of those years is Qumanity.

It is not an app you scroll through and forget. It is not a platform designed to hold your attention hostage and sell what it learns about you. It is not a company with shareholders whose only loyalty is to a quarterly number.

It is a living system — an attempt, imperfect and still growing, to replace the broken architecture underneath our civilization with one that actually answers to the people living inside it.

## What Qumanity Actually Is

Qumanity treats governance the way physics treats reality — as something nested, something that must be consistent at every scale, from the smallest village council to the whole Earth.

It is transparent by construction: every action, every transaction, every decision leaves a permanent, visible trace — not because people are assumed to be criminals, but because sunlight is the one disinfectant that corruption has never found a way around.

It is karma-based, not just currency-based: planting a tree, teaching a child, caring for an elder, serving honestly on a council — these build a real, visible, social credit score, separate from money, because a civilization that only rewards what can be bought will only ever produce people who only value what can be sold.

It is offline-first and village-first: built for the farmer with a cracked phone screen and patchy signal, not only for the person with fibre broadband and the newest device — because a system that only works for the already-connected is not a system for humanity, it is a system for a comfortable fraction of it.

It is nested from Village to Earth: power is meant to rise from where people actually live, not descend from where power already sits.

It is an alternative built by and for the people it serves — not another platform quietly harvesting our conversations, our relationships and our habits to sell back to us as advertising.

## The World Today, and the World We Are Building

Today: corruption hides in plain sight, because no one is watching closely enough, consistently enough, for long enough. Power sits far away from the people it governs. Poverty is treated as weather — unfortunate, but normal. A forest is a resource. A river is a drain. An animal is, at best, an afterthought in someone else's plan.

The world Qumanity is built to make possible: every transaction leaves a trail anyone can follow. Power begins at the village and only rises if it earns the right to. Every honest contribution — to a person, to a community, to the land, to a creature who cannot vote for itself — builds real, visible worth. Nature is not a resource to be extracted; it is a member of the community, owed the same protection as any citizen. We stop being billions of strangers competing for scraps, and start being one family, keeping the same ledger.

This is not a dream I am asking you to believe in blindly. It is a design, already running, that you can go and look at yourself.

## Why I Cannot Stop

I am not building this for money. There are faster, easier ways to make money than fifteen years of unpaid, unglamorous work.
I am not building this for recognition. My name is not even on this message.

I am building it because I have personally watched what happens when our systems fail the people who trusted them: a mother who goes without so her child doesn't have to. A farmer who sees no way out but the one no parent should ever choose. A young person who looks at the world being handed to them and quietly decides that hoping for better is naive.

I am building it because I believe every human being is owed dignity as a birthright, not as a favour from whoever currently holds power.
I am building it because I believe every living creature on this Earth — not only the human ones — deserves to exist without fear, without cruelty, without being erased so someone's balance sheet can grow.
I am building it because I believe peace is not the absence of conflict bought with silence; it is the presence of fairness, loud enough that no one needs to fight for it.
I am building it because I believe love, not cleverness, is the highest form of intelligence — and that any technology worth building should be judged by whether it makes love easier to practice, not harder.

That belief is the fire. Some days it is the only thing that gets the work done.

## The Call

I cannot finish this alone, and honestly, I was never supposed to. Fifteen years of solitary work was never the plan — it was simply what was available to me, and I used it rather than waiting for permission.

Qumanity does not belong to me. It belongs to the farmer who wants to be paid what their harvest is actually worth. It belongs to the mother staying up late, worrying about a future she cannot yet see clearly. It belongs to the child who deserves a school with a roof, and the stray dog who deserves one kind hand out of a hundred. It belongs to the young person who is tired of being told to adjust to a broken world, and wants, instead, to help build a working one.

It belongs to you — whoever you are, wherever on this Earth you are reading this.

## What I Am Actually Asking of You

Read this. Sit with it. Argue with it if you need to — I would rather be challenged honestly than agreed with lazily.
Share it with one person who has also quietly stopped believing things can change.
Register on Qumanity. Walk through your own village's page. Look at what is already working, and what is still only half-built — because a lot of it still is, and I am not going to pretend otherwise.
Plant something. Teach someone. Show up for an elder who is lonely. Be gentle with an animal that has no way to ask you to be.
And if any part of you — even a small, cautious, "let's see" part — believes a fairer world is possible, then join. Not as a follower waiting for instructions, but as a co-creator who makes this stronger just by showing up honestly.

## The Vision I Am Holding

I imagine a village where every voice actually reaches the people who can act on it.
A village where a council is chosen by its own people, serves on a fixed term, and cannot quietly become permanent.
A nation where corruption has nowhere left to hide, not because everyone became virtuous overnight, but because the system no longer has blind spots for it to hide in.
A world where power is earned through service, not inherited through birth or bought through influence.
A world where a human being's dignity never depends on their caste, their gender, their income, or their species.

I am not asking you to imagine a utopia. I have no interest in utopias — they are usually just excuses to avoid doing the actual work. I am asking you to imagine something built, tested, and already standing, however imperfectly. That is the difference between a dream and a design.

## A Closing Word

The world is not broken beyond repair. It is only broken beyond the systems we built to run it — and systems, unlike people, we are entirely free to replace.

I have built one version of what a replacement could look like. It is not finished. It will never be "finished" in the way a product launch is finished — it will keep growing the way a living thing grows, which means it needs more hands than mine.

The question was never really whether Qumanity can work. Small, honest, transparent systems have always worked, at the scale of a village, a family, a trusted circle. The real question is whether we — as a species capable of both unimaginable cruelty and unimaginable tenderness — are finally ready to choose the second one, on purpose, at scale.

I believe we are. I have staked fifteen years on that belief, and I am not finished yet.

## How to Reach Me

I keep my own name private on Qumanity — not from shame, and not from fear, but because this was never meant to be about one person. On this platform, like every member, I am reachable by my 12-digit Account Search ID rather than by name. You will not find my village, my family, or my face by searching for me — only my gender, age-group and elemental sign, same as anyone else who chooses privacy here. That is not a wall. It is an open door that simply asks you to knock with purpose.

Qumanity Account Search ID: {founder_account_id}

Search this ID on Qumanity to send a message, share feedback, propose a partnership, or simply tell me what is and is not working. I read what reaches me. I cannot promise a fast reply — I am still mostly one person — but I promise an honest one.

जय श्री राम
Jai Hind
Jai Humanity"""


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
