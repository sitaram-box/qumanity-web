"""Collective Board — posts that are voted on and climb from Village to Earth.

Rules (from the Qumanity spec, mirrored in Qumanity_App/docs/DEVELOPMENT_PLAN.md §8):
  * Only present residents of a Village post there; every other level is read + vote (+ comment once voting is over).
  * Each level has its own voting window and elevation score. When the window closes:
        score >= threshold  -> ELEVATE to the next level (a fresh voting window starts there)
        0 < score < threshold -> FREEZE (voting closed, readable, comments open)
        score <= 0           -> REMOVE (the post goes back to the author's Private timeline)
  * Comments are allowed only on frozen / elevated posts.
  * Only people living in a group's location now may vote there; birth-village members read only.
Windows are settled lazily: any read calls settle(), which closes everything that is due.
"""
from __future__ import annotations

import datetime as dt
import json

import cycle_middleware
import qoin_core

LEVELS = ["village", "tehsil", "district", "state", "zone", "country", "continent", "earth"]
LEVEL_LABEL = {"village": "Village", "tehsil": "Tehsil", "district": "District", "state": "State", "zone": "Zone",
               "country": "Country", "continent": "Continent", "earth": "Earth"}
WINDOW_DAYS = {"village": 7, "tehsil": 8, "district": 9, "state": 10, "zone": 11, "country": 12, "continent": 13, "earth": 14}
THRESHOLD = {"village": 10, "tehsil": 100, "district": 1_000, "state": 10_000, "zone": 100_000,
             "country": 1_000_000, "continent": 10_000_000, "earth": 100_000_000}
MIN_RESIDENTS = {"village": 100, "tehsil": 1_000, "district": 10_000, "state": 100_000, "zone": 100_000,
                 "country": 1_000_000, "continent": 1_000_000, "earth": 10_000_000}
MAX_POST_CHARS = 1000
MAX_COMMENT_CHARS = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS board_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    group_id TEXT NOT NULL,
    group_name TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',      -- active | frozen | elevated | removed
    score INTEGER NOT NULL DEFAULT 0,
    voting_start TEXT NOT NULL,
    voting_end TEXT NOT NULL,
    origin_post_id INTEGER,
    elevated_to INTEGER,
    chain_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_board_group ON board_posts(group_id, status);
CREATE TABLE IF NOT EXISTS board_votes (
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    value INTEGER NOT NULL,
    PRIMARY KEY (post_id, user_id)
);
CREATE TABLE IF NOT EXISTS board_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_board_comments ON board_comments(post_id);
"""


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    # subgroups is SUB_SCHEMA's table, not SCHEMA's -- ensure it exists before checking its columns
    # below. Call order used to matter (this only ever worked because every real DB already had
    # subgroups from prior use); ensure_sub_tables() is idempotent, so calling it here makes this
    # function self-sufficient regardless of what's called it, including on a brand-new DB.
    ensure_sub_tables(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(subgroups)")}
    if "admin_label" not in cols:
        conn.execute("ALTER TABLE subgroups ADD COLUMN admin_label TEXT")
    conn.commit()


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _parse(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def chain_of(present_location: dict) -> list[dict]:
    """The user's groups from Village up to Earth (tiers a country doesn't have are skipped)."""
    out = []
    for level in LEVELS[:-1]:
        node = present_location.get(level)
        if node and node.get("id"):
            out.append({"level": level, "id": node["id"], "name": node.get("name") or LEVEL_LABEL[level]})
    out.append({"level": "earth", "id": "EARTH", "name": "Earth"})
    return out


def group_for(chain: list[dict], level: str):
    return next((g for g in chain if g["level"] == level), None)


def _open_window(conn, author_id, chain, idx, content, origin_id, now, post_kind="member", is_demo_post=False):
    """post_kind/is_demo_post are written in THIS SAME INSERT, never by a follow-up UPDATE --
    is_test is computed from post_kind right here in SQL (1 only when post_kind='test'), so the
    invariant is_test == (post_kind == 'test') holds from the instant the row exists; there is no
    window, however small, where a test post could exist without its test flag set (2026-10-17)."""
    g = chain[idx]
    end = now + dt.timedelta(days=WINDOW_DAYS[g["level"]])
    cur = conn.execute(
        """INSERT INTO board_posts (author_id, level, group_id, group_name, content, status, score, voting_start, voting_end,
                                    origin_post_id, chain_json, created_at, cycle_id, post_kind, is_test, is_demo_post)
           VALUES (?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (author_id, g["level"], g["id"], g["name"], content, _iso(now), _iso(end), origin_id, json.dumps(chain), _iso(now),
         cycle_middleware.get_active_cycle_id(conn), post_kind, 1 if post_kind == "test" else 0, 1 if is_demo_post else 0),
    )
    return cur.lastrowid


PAID_LEVELS = ("tehsil", "district", "state", "zone")  # text-only paid posting; Country/Continent/Earth are broadcast + voting only


def create_post(conn, user_id, present_location, content, level="village", now=None, post_kind="member", is_demo_post=False):
    """Village posting is free. Tehsil→Zone posting is a paid text-only service (qoin_core.post_price);
    the price is debited from the poster's wallet before the post opens for voting.

    post_kind/is_demo_post (2026-10-17): 'member' (default, every existing caller) | 'test'
    (Admin-tagged or scheduler-created -- see test_cycle_scheduler.py and the tagging route in
    app.py). A real member never passes these; only the Admin's tagging route and the test-cycle
    scheduler ever pass post_kind='test'."""
    import wallet_core
    now = now or dt.datetime.now(dt.timezone.utc)
    content = (content or "").strip()
    if not content:
        raise ValueError("Write something to post")
    if len(content) > MAX_POST_CHARS:
        raise ValueError(f"Posts can be at most {MAX_POST_CHARS} characters")
    chain = chain_of(present_location)
    if level == "village":
        if chain[0]["level"] != "village":
            raise ValueError("Add your present village to your profile to post")
        idx = 0
    else:
        if level not in PAID_LEVELS:
            raise ValueError("Posts cannot be made on this page")
        idx = next((i for i, g in enumerate(chain) if g["level"] == level), None)
        if idx is None:
            raise ValueError("You have no group at this level")
        price = qoin_core.post_price(level, "text")
        balance = wallet_core.wallet_balance(conn, "user", str(user_id))
        if balance < price:
            raise ValueError(f"Posting here costs {price} Qoins and your wallet has {balance}")
        wallet_core._credit(conn, "user", str(user_id), -price, f"Paid post at {LEVEL_LABEL[level]}")
    pid = _open_window(conn, user_id, chain, idx, content, None, now, post_kind=post_kind, is_demo_post=is_demo_post)
    conn.commit()
    return pid


def create_council_update(conn, user_id, present_location, content, level="village", now=None):
    """A council update (2026-10-17, Path 2: independent of announcements_core.py) is never a
    proposal -- no voting window is opened at all. status='published', a value settle()'s own
    `WHERE status = 'active'` query never matches, so a council update is never picked up by
    settle(), never freezes, never elevates, never gets a reward or a recognition star.
    voting_start/voting_end are NOT NULL columns on board_posts with no meaning for this
    post_kind -- set to `now` itself and never read for a council update."""
    now = now or dt.datetime.now(dt.timezone.utc)
    content = (content or "").strip()
    if not content:
        raise ValueError("Write something to post")
    if len(content) > MAX_POST_CHARS:
        raise ValueError(f"Posts can be at most {MAX_POST_CHARS} characters")
    chain = chain_of(present_location)
    g = group_for(chain, level)
    if not g:
        raise ValueError("You have no group at this level")
    cur = conn.execute(
        """INSERT INTO board_posts (author_id, level, group_id, group_name, content, status, score, voting_start, voting_end,
                                    origin_post_id, chain_json, created_at, cycle_id, post_kind, is_test, is_demo_post)
           VALUES (?, ?, ?, ?, ?, 'published', 0, ?, ?, NULL, ?, ?, ?, 'council_update', 0, 0)""",
        (user_id, g["level"], g["id"], g["name"], content, _iso(now), _iso(now), json.dumps(chain), _iso(now),
         cycle_middleware.get_active_cycle_id(conn)),
    )
    conn.commit()
    return cur.lastrowid


def settle(conn, now=None):
    """Close every voting window that is due: elevate, freeze or remove -- then, independently of
    that, pay every POSITIVE-score post its rank-based reward for the level it just cleared
    (2026-10-17 design). The two are separate questions: elevation depends on whether score
    cleared THRESHOLD[level]; the reward depends only on the post's RANK among its positive peers
    at the same (level, cycle) -- so a positive post that falls short of the elevation threshold
    still earns a reward (somewhere between that level's min and max), it just doesn't climb
    further. A post that elevates earns this level's reward too, then -- if it later clears a
    higher level as well -- earns THAT level's reward separately when ITS window closes; rewards
    are cumulative across levels, one wallet_transactions row per level actually cleared.

    Ranking is done among whichever positive posts at a given (level, cycle_id) happen to be
    `due` in this SAME settle() call -- posts at the same level/cycle created on different days
    have different voting_end dates (WINDOW_DAYS is fixed per level, counted from each post's own
    creation), so a post can in principle be ranked only against whichever peers' windows close
    at the same moment, not necessarily every positive post that cycle will ever produce at that
    level. This matches how settle() already runs today (opportunistically, on any read, plus the
    daily cron tick) rather than at a true per-cycle-per-level boundary event; a stricter
    cycle-complete batching would need a new scheduled trigger per level, out of this task's scope.

    Earth is no longer special-cased: REWARD_RANGE_INR gives it the highest range, like every
    other level, instead of a separate winner/participant split."""
    import karma_core
    import wallet_core

    now = now or dt.datetime.now(dt.timezone.utc)
    due = conn.execute("SELECT * FROM board_posts WHERE status = 'active' AND voting_end <= ?", (_iso(now),)).fetchall()

    groups: dict[tuple, list] = {}
    for p in due:
        groups.setdefault((p["level"], p["cycle_id"]), []).append(p)

    for (level, cycle_id), posts in groups.items():
        for p in posts:
            if p["score"] < 0:
                conn.execute("UPDATE board_posts SET status='removed' WHERE id=?", (p["id"],))
                if p["post_kind"] != "test":
                    _penalty_karma(conn, p, level)
            elif p["score"] == 0:
                # Zero-score posts freeze (2026-10-17 change, was 'removed'): a neutral, visible,
                # permanent record -- no reward, no recognition star, no karma either way.
                conn.execute("UPDATE board_posts SET status='frozen' WHERE id=?", (p["id"],))

        positive = sorted((p for p in posts if p["score"] > 0), key=lambda p: p["score"], reverse=True)
        n = len(positive)
        for i, p in enumerate(positive):
            rank = i + 1
            reward_inr = qoin_core.rank_reward_inr(rank, n, level)
            label = f"Post cleared {LEVEL_LABEL[level]} (rank {rank}/{n}, score {p['score']:+d})"
            if p["post_kind"] == "test":
                # Decision 2 (2026-10-17, docs/test_cycle_design.md): a test post's reward is
                # computed and displayed (the frozen test record in board.js), but the real
                # wallet is never credited, no karma is written, and no recognition star is
                # written. Stored directly on the post -- there is no wallet_transactions row
                # for a test post to look the reward back up from (no credit_qoins() call means
                # no row at all).
                conn.execute("UPDATE board_posts SET test_reward_inr = ? WHERE id = ?", (reward_inr, p["id"]))
            else:
                wallet_core.credit_qoins(
                    conn, "user", str(p["author_id"]), reward_inr, label,
                    rupee_value=reward_inr, related_post_id=p["id"],
                )
                if level == "village":
                    karma_core.add_individual_karma(conn, p["author_id"], "noncommercial", reward_inr, label)
                else:
                    karma_core.bump_collective_karma(conn, p["group_id"], level, reward_inr, label)
                conn.execute(
                    """INSERT INTO recognition_stars (post_id, author_id, level, location_id, score, created_at, cycle_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (p["id"], p["author_id"], level, p["group_id"], p["score"], _iso(now), cycle_id),
                )

            chain = json.loads(p["chain_json"])
            idx = next((j for j, g in enumerate(chain) if g["level"] == level), None)
            nxt = idx + 1 if idx is not None and idx + 1 < len(chain) else None
            if p["score"] >= THRESHOLD[level] and nxt is not None:
                # post_kind/is_demo_post MUST travel with the post as it elevates (2026-10-17) --
                # without this, a test post's next-level post silently reverts to post_kind=
                # 'member' (the default), immediately visible to real members, votable by
                # anyone, and real-rewarded, defeating the entire point of testing elevation.
                new_id = _open_window(conn, p["author_id"], chain, nxt, p["content"], p["id"], _parse(p["voting_end"]),
                                       post_kind=p["post_kind"], is_demo_post=bool(p["is_demo_post"]))
                conn.execute("UPDATE board_posts SET status='elevated', elevated_to=? WHERE id=?", (new_id, p["id"]))
            else:
                conn.execute("UPDATE board_posts SET status='frozen' WHERE id=?", (p["id"],))

    if due:
        conn.commit()
    return len(due)


# Karma is separate from the Qoins above (2026-09-29), and the penalty below is new (2026-10-17):
# a positive post's reward and karma both scale with its RANK-based reward_inr -- Village credits
# the author's own INDIVIDUAL karma (it's their own work); every other level credits COLLECTIVE
# karma to the location it cleared (it now represents that wider group's recognised action). A
# negative-score post, wherever it happens, costs the AUTHOR individual "penalty" karma -- always
# individual, regardless of level, since it's a personal accountability signal, not a location's.
# The penalty magnitude (-1) is a placeholder pending a real spec for how harshly to weigh it;
# flagged for the user to adjust.
PENALTY_KARMA_POINTS = -1


def _penalty_karma(conn, post, level):
    import karma_core
    karma_core.add_individual_karma(
        conn, post["author_id"], "penalty", PENALTY_KARMA_POINTS,
        f"Post removed at {LEVEL_LABEL[level]} (score {post['score']:+d})",
    )


def _is_resident(chain, post):
    return any(g["id"] == post["group_id"] and g["level"] == post["level"] for g in chain)


def cast_vote(conn, user_id, present_location, post_id, value, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if value not in (-1, 0, 1):
        raise ValueError("A vote is +1, 0 or -1")
    settle(conn, now)
    post = conn.execute("SELECT * FROM board_posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        raise LookupError("Post not found")
    # Server-side, not just the UI hiding vote buttons (2026-10-17): a council update is never a
    # proposal, so it is never open for voting, regardless of its status. 'test' posts are NOT
    # rejected here -- they are voted on by demo users (and optionally the Admin) exactly like a
    # member post; only council_update is excluded. Checked BEFORE the status/voting_end check
    # below so the error is specific ("not open for voting"), not the generic "voting has closed"
    # a real member post gets once its own window ends.
    if post["post_kind"] == "council_update":
        raise ValueError("This post is not open for voting")
    if post["status"] != "active" or _parse(post["voting_end"]) <= now:
        raise PermissionError("Voting has closed on this post")
    if not _is_resident(chain_of(present_location), post):
        raise PermissionError("Only people living in this group can vote")
    # 2026-10-27: nobody votes on their own post -- was never actually enforced here (only
    # board_view()'s can_vote flag tried to hide the buttons client-side, and that flag had its
    # own bug -- see board_view()'s own note). Enforced server-side now, not just by hiding UI.
    if post["author_id"] == user_id:
        raise PermissionError("You cannot vote on your own post")
    old = conn.execute("SELECT value FROM board_votes WHERE post_id=? AND user_id=?", (post_id, user_id)).fetchone()
    conn.execute(
        "INSERT OR REPLACE INTO board_votes (post_id, user_id, value, cycle_id, voted_at) VALUES (?, ?, ?, ?, ?)",
        (post_id, user_id, value, cycle_middleware.get_active_cycle_id(conn), _iso(now)),
    )
    conn.execute("UPDATE board_posts SET score = score + ? WHERE id = ?", (value - (old["value"] if old else 0), post_id))
    conn.commit()
    return conn.execute("SELECT score FROM board_posts WHERE id=?", (post_id,)).fetchone()["score"]


def add_comment(conn, user_id, present_location, post_id, text, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    text = (text or "").strip()
    if not text:
        raise ValueError("Write a comment first")
    if len(text) > MAX_COMMENT_CHARS:
        raise ValueError(f"Comments can be at most {MAX_COMMENT_CHARS} characters")
    settle(conn, now)
    post = conn.execute("SELECT * FROM board_posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        raise LookupError("Post not found")
    if post["status"] not in ("frozen", "elevated"):
        raise PermissionError("Comments open once voting has finished")
    if not _is_resident(chain_of(present_location), post):
        raise PermissionError("Only people living in this group can comment")
    conn.execute("INSERT INTO board_comments (post_id, user_id, text, created_at, cycle_id) VALUES (?, ?, ?, ?, ?)",
                (post_id, user_id, text, _iso(now), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def board_view(conn, user_id, present_location, level, now=None, is_admin=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    settle(conn, now)
    chain = chain_of(present_location)
    g = group_for(chain, level)
    if not g:
        return None
    if level == "earth":
        member_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_demo = 0 AND is_removed = 0").fetchone()[0]
    else:
        member_count = conn.execute(
            f"SELECT COUNT(*) FROM users WHERE json_extract(present_location_json, '$.{level}.id') = ? "
            "AND is_demo = 0 AND is_removed = 0", (g["id"],)
        ).fetchone()[0]
    import wallet_core
    # Visibility rule (2026-10-17): a board's own header shows this location's COLLECTIVE wallet
    # to every viewer, so it must be the public qoin_count, never the private rupee balance --
    # that stays behind /api/wallet/balance/<level>/<id>, gated to council/admin in app.py.
    qoins = wallet_core.public_wallet_view(conn, level, g["id"])["qoin_count"]
    stars = [
        {"post_id": s["post_id"], "author": s["author_name"], "user_id": s["author_id"], "gender": s["gender"],
         "profile_picture_url": f"/api/users/{s['author_id']}/profile-picture" if s["has_picture"] else None,
         "score": s["score"], "at": s["created_at"]}
        for s in conn.execute(
            """SELECT rs.post_id, rs.score, rs.created_at, u.id AS author_id, u.name AS author_name, u.gender,
                      u.profile_picture IS NOT NULL AS has_picture
               FROM recognition_stars rs JOIN users u ON u.id = rs.author_id
               WHERE rs.location_id = ? AND rs.level = ? ORDER BY rs.id DESC LIMIT 25""",
            (g["id"], level),
        )
    ]
    # Visibility rule (2026-10-17, design doc Section 7): hide an is_test=1 post from everyone
    # except the Admin and demo viewers WHILE it's active; once it's frozen/elevated, p.status !=
    # 'active' alone makes it visible to everyone, same query, no second query needed.
    is_demo_viewer = bool(conn.execute("SELECT is_demo FROM users WHERE id = ?", (user_id,)).fetchone()[0])
    rows = conn.execute(
        """SELECT p.*, u.name AS author_name, u.gender AS author_gender,
                  u.profile_picture IS NOT NULL AS author_has_picture, v.value AS my_vote
           FROM board_posts p
           JOIN users u ON u.id = p.author_id
           LEFT JOIN board_votes v ON v.post_id = p.id AND v.user_id = ?
           WHERE p.group_id = ? AND p.level = ? AND p.status != 'removed'
             AND (p.is_test = 0 OR p.status != 'active' OR ? = 1 OR ? = 1)
           ORDER BY p.created_at DESC, p.id DESC LIMIT 100""",
        (user_id, g["id"], level, int(is_admin), int(is_demo_viewer)),
    ).fetchall()
    # reaction_counts batch-fetched once for every council_update post in this result set --
    # reactions_core.counts_for() is already batch-shaped, same call board_core.py's own
    # chat_messages() uses for message reactions.
    import reactions_core
    council_update_ids = [p["id"] for p in rows if p["post_kind"] == "council_update"]
    reaction_counts = reactions_core.counts_for(conn, "board_post", council_update_ids, user_id) if council_update_ids else {}
    # Demo-voter counts for every test post in this result set, batch-fetched once (design doc
    # Section 2c equivalent: the frozen test record's "voted by N demo users" note). Counted LIVE
    # from board_votes, never a frozen snapshot -- Decision 3 (retire_demo_voters.py never
    # touches board_votes) already guarantees this stays correct even after demo voters retire.
    test_ids = [p["id"] for p in rows if p["post_kind"] == "test"]
    demo_voter_counts: dict[int, int] = {}
    if test_ids:
        qmarks = ",".join("?" * len(test_ids))
        for r in conn.execute(
            f"""SELECT v.post_id, COUNT(*) AS n FROM board_votes v JOIN users u ON u.id = v.user_id
                WHERE v.post_id IN ({qmarks}) AND u.is_demo = 1 GROUP BY v.post_id""",
            test_ids,
        ):
            demo_voter_counts[r["post_id"]] = r["n"]
    # 2026-10-27 (Frozen Posts: the missing reward amount): a REAL (non-test) post's reward is
    # never stored on the post row itself -- settle() just calls wallet_core.credit_qoins(),
    # which writes it to wallet_transactions (related_post_id = this exact post's own id, one row
    # per level a post actually cleared, since elevation creates a NEW post row per level -- see
    # settle()'s own docstring). Batch-fetched once here, same shape as demo_voter_counts above,
    # rather than a per-post query.
    settled_ids = [p["id"] for p in rows if p["post_kind"] != "test" and p["status"] in ("frozen", "elevated") and p["score"] > 0]
    reward_by_post: dict[int, dict] = {}
    if settled_ids:
        qmarks = ",".join("?" * len(settled_ids))
        for r in conn.execute(
            f"SELECT related_post_id, amount_qoins, rupee_value FROM wallet_transactions WHERE related_post_id IN ({qmarks})",
            settled_ids,
        ):
            reward_by_post[r["related_post_id"]] = {"qoins": r["amount_qoins"], "inr": r["rupee_value"]}
    posts = []
    for p in rows:
        active = p["status"] == "active"
        comments = []
        if not active:
            comments = [{"who": c["name"], "user_id": c["user_id"], "gender": c["gender"],
                         "profile_picture_url": f"/api/users/{c['user_id']}/profile-picture" if c["has_picture"] else None,
                         "text": c["text"], "at": c["created_at"]} for c in conn.execute(
                """SELECT c.text, c.created_at, c.user_id, u.name, u.gender, u.profile_picture IS NOT NULL AS has_picture
                   FROM board_comments c JOIN users u ON u.id = c.user_id WHERE c.post_id=? ORDER BY c.id LIMIT 50""", (p["id"],))]
        origin = None
        if p["origin_post_id"]:
            o = conn.execute("SELECT level, score FROM board_posts WHERE id=?", (p["origin_post_id"],)).fetchone()
            # "from_level"/"to_level" (2026-10-27): the raw level codes, not just the display
            # label, so the frontend can render "Escalated from Village to Tehsil" -- the CURRENT
            # level (this view's own `level`) without a second lookup.
            origin = {"level": LEVEL_LABEL[o["level"]], "score": o["score"],
                      "from_level": LEVEL_LABEL[o["level"]], "to_level": LEVEL_LABEL[level]} if o else None
        nxt = None
        if p["elevated_to"]:
            e = conn.execute("SELECT level FROM board_posts WHERE id=?", (p["elevated_to"],)).fetchone()
            nxt = LEVEL_LABEL[e["level"]] if e else None
        post_dict = {
            "id": p["id"], "author": p["author_name"], "author_id": p["author_id"], "author_gender": p["author_gender"],
            "author_profile_picture_url": f"/api/users/{p['author_id']}/profile-picture" if p["author_has_picture"] else None,
            "mine": p["author_id"] == user_id, "content": p["content"], "status": p["status"],
            "score": p["score"], "my_vote": p["my_vote"], "created_at": p["created_at"], "voting_end": p["voting_end"],
            "threshold": THRESHOLD[level], "window_days": WINDOW_DAYS[level], "origin": origin, "elevated_to": nxt, "comments": comments,
            # 2026-10-27: test posts are votable too (cast_vote() already allowed this -- this
            # flag just never matched it, which is exactly why an escalated test post couldn't be
            # voted on at its new level: the vote buttons were hidden client-side even though the
            # backend would have accepted the vote). Also now excludes the post's own author.
            "can_vote": active and p["post_kind"] in ("member", "test") and p["author_id"] != user_id,
            "can_comment": not active, "post_kind": p["post_kind"],
            "is_demo_post": bool(p["is_demo_post"]),
        }
        if p["post_kind"] == "council_update":
            post_dict["reactions"] = reaction_counts.get(p["id"])
        elif p["post_kind"] == "test" and p["status"] in ("frozen", "elevated"):
            # The frozen test record (design doc Section 3 / Section 8's "test -- not credited"
            # note) -- only once voting has actually closed; an active test post has no final
            # score or reward to show yet.
            post_dict["test_record"] = {
                "voting_start": p["created_at"], "voting_end": p["voting_end"], "final_score": p["score"],
                "reward_inr": p["test_reward_inr"], "demo_voter_count": demo_voter_counts.get(p["id"], 0),
            }
        elif p["id"] in reward_by_post:
            # 2026-10-27 (Frozen Posts: the missing reward amount) -- the real, credited
            # equivalent of test_record above, for an ordinary member post that actually earned
            # Qoins when its own voting window closed.
            post_dict["reward"] = reward_by_post[p["id"]]
        posts.append(post_dict)
    post_price = None if level not in PAID_LEVELS else qoin_core.post_price(level, "text")
    currency_code, currency_symbol, currency_name = qoin_core.currency_for((present_location.get("country") or {}).get("code"))
    # 2026-10-28 ("first impression" upgrade, empty-state problem): a village with nobody posting
    # yet reads as broken, not quiet. Village-only (Tehsil+ is paid/elevation-only -- "be the
    # first" doesn't fit a page nobody free-posts to) and keyed on the same `active` set board.js
    # itself already renders as "live voting" -- a frozen/elevated/removed post, or a reaction-only
    # council_update (the seeded Founder post among them, see founder_core.seed_welcome_post()),
    # doesn't count as "something is happening here" for this purpose.
    empty_prompt = None
    if level == "village" and not any(p["status"] == "active" for p in rows):
        empty_prompt = {
            "headline": "This village hasn't spoken yet.",
            "body": "“Every voice starts somewhere. Yours could be the first.” — The Founder",
            "cta": "Be the first to propose a change in your village",
        }
    return {
        "level": level, "label": LEVEL_LABEL[level], "group": g["name"], "group_id": g["id"],
        "members": member_count, "qoins": qoins, "empty_prompt": empty_prompt,
        "can_post": level == "village", "can_pay_post": level in PAID_LEVELS,
        # A paid post is priced in local currency and paid in the Qoins that make it up (qoin_core.to_qoins) --
        # the price shown to the user must always name BOTH, never a bare Qoin count (docs/qoins_wallet_system.md).
        "post_price": post_price,
        "post_price_qoins": None if post_price is None else qoin_core.to_qoins(post_price),
        "currency": currency_code, "currency_symbol": currency_symbol, "currency_name": currency_name,
        "threshold": THRESHOLD[level], "window_days": WINDOW_DAYS[level], "posts": posts, "stars": stars,
        "next": next((LEVEL_LABEL[c["level"]] for c in chain[chain.index(g) + 1: chain.index(g) + 2]), None),
    }


def removed_posts(conn, user_id):
    return [{"id": r["id"], "level": LEVEL_LABEL[r["level"]], "group": r["group_name"], "content": r["content"], "score": r["score"], "at": r["voting_end"]}
            for r in conn.execute("SELECT * FROM board_posts WHERE author_id=? AND status='removed' ORDER BY id DESC LIMIT 50", (user_id,))]


# ---- Village sub-groups (societies / RWAs), group chat, volunteers ----
SUB_SCHEMA = """
CREATE TABLE IF NOT EXISTS subgroups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, village_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
    admin_label TEXT, created_by INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subgroup_members (
    subgroup_id INTEGER NOT NULL, user_id INTEGER NOT NULL, status TEXT NOT NULL, requested_at TEXT NOT NULL,
    PRIMARY KEY (subgroup_id, user_id)
);
CREATE TABLE IF NOT EXISTS board_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, subgroup_id INTEGER NOT NULL, user_id INTEGER NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msgs ON board_messages(subgroup_id, id);
CREATE TABLE IF NOT EXISTS volunteers (
    user_id INTEGER NOT NULL, level TEXT NOT NULL, group_id TEXT NOT NULL, kind TEXT NOT NULL, skill TEXT, created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, level, group_id, kind)
);
CREATE TABLE IF NOT EXISTS referrer_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, note TEXT, status TEXT NOT NULL DEFAULT 'pending',
    decided_by INTEGER, decided_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS referrers (
    user_id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, approved_by INTEGER, created_at TEXT NOT NULL, uses INTEGER NOT NULL DEFAULT 0
);
"""


def ensure_sub_tables(conn):
    conn.executescript(SUB_SCHEMA)
    conn.commit()


def _now_iso():
    return _iso(dt.datetime.now(dt.timezone.utc))


def list_subgroups(conn, user_id, village_id, is_admin):
    out = []
    for g in conn.execute("SELECT * FROM subgroups WHERE village_id=? ORDER BY name", (village_id,)):
        mine = conn.execute("SELECT status FROM subgroup_members WHERE subgroup_id=? AND user_id=?", (g["id"], user_id)).fetchone()
        item = {"id": g["id"], "name": g["name"], "description": g["description"] or "", "my_status": mine["status"] if mine else None,
                "admin_label": g["admin_label"] or "Village Council",
                "members": conn.execute("SELECT COUNT(*) FROM subgroup_members WHERE subgroup_id=? AND status='approved'", (g["id"],)).fetchone()[0]}
        if is_admin:
            item["pending"] = [{"user_id": r["user_id"], "name": r["name"]} for r in conn.execute(
                "SELECT m.user_id, u.name FROM subgroup_members m JOIN users u ON u.id=m.user_id WHERE m.subgroup_id=? AND m.status='pending'", (g["id"],))]
        out.append(item)
    return out


def create_subgroup(conn, admin_id, village_id, name, description, admin_label=None):
    name = (name or "").strip()
    if not 2 <= len(name) <= 60:
        raise ValueError("Give the sub-group a name (2–60 characters)")
    label = (admin_label or "").strip()[:80] or "Village Council"  # e.g. "RWA Committee" (urban) or "Panchayat" (rural) -- the creator names their own local body
    cur = conn.execute("INSERT INTO subgroups (village_id, name, description, admin_label, created_by, created_at, cycle_id) VALUES (?,?,?,?,?,?,?)",
                       (village_id, name, (description or "").strip()[:200], label, admin_id, _now_iso(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()
    return cur.lastrowid


def _subgroup(conn, sg_id):
    g = conn.execute("SELECT * FROM subgroups WHERE id=?", (sg_id,)).fetchone()
    if not g:
        raise LookupError("Sub-group not found")
    return g


def request_join(conn, user_id, present_location, sg_id):
    g = _subgroup(conn, sg_id)
    if (present_location.get("village") or {}).get("id") != g["village_id"]:
        raise PermissionError("Only people living in this village can ask to join")
    if conn.execute("SELECT 1 FROM subgroup_members WHERE subgroup_id=? AND user_id=?", (sg_id, user_id)).fetchone():
        raise ValueError("You have already asked to join")
    if conn.execute("""SELECT 1 FROM subgroup_members m JOIN subgroups g ON g.id = m.subgroup_id
                       WHERE m.user_id = ? AND g.village_id = ?""", (user_id, g["village_id"])).fetchone():
        raise ValueError("You can be a member of only one village group")
    conn.execute("INSERT INTO subgroup_members (subgroup_id, user_id, status, requested_at, cycle_id) VALUES (?,?,?,?,?)",
                (sg_id, user_id, "pending", _now_iso(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def decide_join(conn, sg_id, user_id, approve):
    _subgroup(conn, sg_id)
    if approve:
        conn.execute("UPDATE subgroup_members SET status='approved' WHERE subgroup_id=? AND user_id=?", (sg_id, user_id))
    else:
        conn.execute("DELETE FROM subgroup_members WHERE subgroup_id=? AND user_id=?", (sg_id, user_id))
    conn.commit()


def _can_chat(conn, user_id, sg_id, is_admin):
    if is_admin:
        return True
    r = conn.execute("SELECT status FROM subgroup_members WHERE subgroup_id=? AND user_id=?", (sg_id, user_id)).fetchone()
    return bool(r and r["status"] == "approved")


def chat_messages(conn, user_id, sg_id, is_admin):
    import reactions_core
    g = _subgroup(conn, sg_id)
    if not _can_chat(conn, user_id, sg_id, is_admin):
        raise PermissionError("Ask the council to add you to this group")
    rows = list(reversed(conn.execute(
        "SELECT m.id, m.text, m.created_at, m.user_id, u.name, u.gender, u.account_id, "
        "u.profile_picture IS NOT NULL AS has_picture FROM board_messages m JOIN users u ON u.id=m.user_id "
        "WHERE m.subgroup_id=? ORDER BY m.id DESC LIMIT 100", (sg_id,)).fetchall()))
    member_count = conn.execute("SELECT COUNT(*) FROM subgroup_members WHERE subgroup_id=? AND status='approved'", (sg_id,)).fetchone()[0] + 1  # +owner
    reactions = reactions_core.counts_for(conn, "subgroup", [r["id"] for r in rows], user_id)
    return {"id": g["id"], "name": g["name"], "admin_label": g["admin_label"] or "Village Council", "members": member_count,
            "messages": [{"id": r["id"], "who": r["name"], "user_id": r["user_id"], "gender": r["gender"],
                         "profile_picture_url": f"/api/users/{r['user_id']}/profile-picture" if r["has_picture"] else None,
                         "account_id": r["account_id"], "mine": r["user_id"] == user_id,
                         "text": r["text"], "at": r["created_at"], "reactions": reactions[r["id"]]} for r in rows]}


def send_message(conn, user_id, sg_id, text, is_admin):
    _subgroup(conn, sg_id)
    if not _can_chat(conn, user_id, sg_id, is_admin):
        raise PermissionError("Ask the council to add you to this group")
    text = (text or "").strip()
    if not text or len(text) > 1000:
        raise ValueError("Write a message (up to 1000 characters)")
    conn.execute("INSERT INTO board_messages (subgroup_id, user_id, text, created_at, cycle_id) VALUES (?,?,?,?,?)",
                (sg_id, user_id, text, _now_iso(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def register_volunteer(conn, user_id, present_location, skill):
    v = present_location.get("village")
    if not v or not v.get("id"):
        raise ValueError("Volunteering is open to people living in a village")
    skill = (skill or "").strip()
    if not 2 <= len(skill) <= 80:
        raise ValueError("Tell us what you do (2–80 characters), e.g. vegetable seller, electrician")
    conn.execute("INSERT OR REPLACE INTO volunteers (user_id, level, group_id, kind, skill, created_at, cycle_id) VALUES (?,?,?,?,?,?,?)",
                (user_id, "village", v["id"], "volunteer", skill, _now_iso(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


# ---- Referrers: village volunteers who hold a referral code, approved by a council member ----

def apply_as_referrer(conn, user_id, note):
    if conn.execute("SELECT 1 FROM referrer_applications WHERE user_id=? AND status='pending'", (user_id,)).fetchone():
        raise ValueError("You already have an application waiting for review")
    if conn.execute("SELECT 1 FROM referrers WHERE user_id=?", (user_id,)).fetchone():
        raise ValueError("You already hold a referral code")
    conn.execute("INSERT INTO referrer_applications (user_id, note, created_at, cycle_id) VALUES (?,?,?,?)",
                (user_id, (note or "").strip()[:300], _now_iso(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def list_referrer_applications(conn):
    return [dict(r) for r in conn.execute(
        "SELECT a.id, a.user_id, a.note, a.created_at, u.name FROM referrer_applications a JOIN users u ON u.id=a.user_id WHERE a.status='pending' ORDER BY a.id")]


def _new_referral_code(conn):
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(50):
        code = "REF-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not conn.execute("SELECT 1 FROM referrers WHERE code=?", (code,)).fetchone():
            return code
    raise RuntimeError("Could not generate a referral code")


def decide_referrer_application(conn, admin_id, application_id, approve):
    app_row = conn.execute("SELECT * FROM referrer_applications WHERE id=? AND status='pending'", (application_id,)).fetchone()
    if not app_row:
        raise LookupError("Application not found")
    conn.execute("UPDATE referrer_applications SET status=?, decided_by=?, decided_at=? WHERE id=?",
                 ("approved" if approve else "rejected", admin_id, _now_iso(), application_id))
    code = None
    if approve:
        code = _new_referral_code(conn)
        conn.execute("INSERT INTO referrers (user_id, code, approved_by, created_at) VALUES (?,?,?,?)", (app_row["user_id"], code, admin_id, _now_iso()))
    conn.commit()
    return code


def referrer_for_code(conn, code):
    row = conn.execute("SELECT user_id FROM referrers WHERE code=?", ((code or "").strip().upper(),)).fetchone()
    return row["user_id"] if row else None


def my_referrer_code(conn, user_id):
    row = conn.execute("SELECT code, uses FROM referrers WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def record_referral_use(conn, code):
    conn.execute("UPDATE referrers SET uses = uses + 1 WHERE code=?", (code.strip().upper(),))
    conn.commit()
