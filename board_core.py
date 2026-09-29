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


def _open_window(conn, author_id, chain, idx, content, origin_id, now):
    g = chain[idx]
    end = now + dt.timedelta(days=WINDOW_DAYS[g["level"]])
    cur = conn.execute(
        """INSERT INTO board_posts (author_id, level, group_id, group_name, content, status, score, voting_start, voting_end,
                                    origin_post_id, chain_json, created_at)
           VALUES (?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?, ?)""",
        (author_id, g["level"], g["id"], g["name"], content, _iso(now), _iso(end), origin_id, json.dumps(chain), _iso(now)),
    )
    return cur.lastrowid


PAID_LEVELS = ("tehsil", "district", "state", "zone")  # text-only paid posting; Country/Continent/Earth are broadcast + voting only


def create_post(conn, user_id, present_location, content, level="village", now=None):
    """Village posting is free. Tehsil→Zone posting is a paid text-only service (qoin_core.post_price);
    the price is debited from the poster's wallet before the post opens for voting."""
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
    pid = _open_window(conn, user_id, chain, idx, content, None, now)
    conn.commit()
    return pid


def settle(conn, now=None):
    """Close every voting window that is due: elevate, freeze or remove.
    Earth is special: among the posts freezing at Earth in this same pass, whoever has the
    highest score is the "winner" (₹500); every other positive score gets the participant
    reward (100+100)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    due = conn.execute("SELECT * FROM board_posts WHERE status = 'active' AND voting_end <= ?", (_iso(now),)).fetchall()
    earth_frozen = []
    for p in due:
        level, score = p["level"], p["score"]
        chain = json.loads(p["chain_json"])
        idx = next((i for i, g in enumerate(chain) if g["level"] == level), None)
        nxt = idx + 1 if idx is not None and idx + 1 < len(chain) else None
        if score >= THRESHOLD[level] and nxt is not None:
            new_id = _open_window(conn, p["author_id"], chain, nxt, p["content"], p["id"], _parse(p["voting_end"]))
            conn.execute("UPDATE board_posts SET status='elevated', elevated_to=? WHERE id=?", (new_id, p["id"]))
        elif score > 0:
            conn.execute("UPDATE board_posts SET status='frozen' WHERE id=?", (p["id"],))
            if level == "earth":
                earth_frozen.append(p)
            else:
                _reward_author(conn, p, level, score)
        else:
            conn.execute("UPDATE board_posts SET status='removed' WHERE id=?", (p["id"],))
    if earth_frozen:
        winner_score = max(p["score"] for p in earth_frozen)
        for p in earth_frozen:
            _reward_author(conn, p, "earth", p["score"], earth_winner=(p["score"] == winner_score))
    if due:
        conn.commit()
    return len(due)


def _reward_author(conn, post, level, score, earth_winner=False):
    """A post that freezes with a positive score pays its author Qoins by the level it reached
    (qoin_core.post_reward). At Earth, the highest-scoring post in the same settle() pass wins ₹500;
    every other positive-score Earth post gets the 100+100 participant reward."""
    import wallet_core
    amount = sum(qoin_core.post_reward(level, score, earth_winner=earth_winner))
    if amount:
        label = f"Post frozen at Earth ({'winner' if earth_winner else 'participant'}, score {score:+d})" if level == "earth" \
            else f"Post frozen at {LEVEL_LABEL[level]} (score {score:+d})"
        wallet_core._credit(conn, "user", str(post["author_id"]), amount, label)
    _reward_karma(conn, post, level, score)


# Karma is separate from the Qoins above (2026-09-29): a Village-level post freezing positively is
# the author's OWN good work (individual, non-commercial karma); once a post has risen past the
# village it represents that wider group's recognised action, so it credits COLLECTIVE karma to
# the location it froze at, not to the individual author. Reuses qoin_core's own reward scale as a
# simple, already-tuned "bigger reach -> bigger recognition" curve -- these are karma points, never
# Qoins, and karma is never auto-converted to or from Qoins.
def _reward_karma(conn, post, level, score):
    import karma_core

    if level == "village":
        points = qoin_core.FREEZE_REWARD["village"]
        karma_core.add_individual_karma(conn, post["author_id"], "noncommercial", points, f"Post frozen at Village (score {score:+d})")
    elif level == "earth":
        karma_core.bump_collective_karma(conn, "EARTH", "earth", qoin_core.EARTH_PARTICIPANT[0], f"Post frozen at Earth (score {score:+d})")
    else:
        points = qoin_core.FREEZE_REWARD.get(level, 0)
        if points:
            karma_core.bump_collective_karma(conn, post["group_id"], level, points, f"Post frozen at {LEVEL_LABEL[level]} (score {score:+d})")


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
    if post["status"] != "active" or _parse(post["voting_end"]) <= now:
        raise PermissionError("Voting has closed on this post")
    if not _is_resident(chain_of(present_location), post):
        raise PermissionError("Only people living in this group can vote")
    old = conn.execute("SELECT value FROM board_votes WHERE post_id=? AND user_id=?", (post_id, user_id)).fetchone()
    conn.execute("INSERT OR REPLACE INTO board_votes (post_id, user_id, value) VALUES (?, ?, ?)", (post_id, user_id, value))
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
    conn.execute("INSERT INTO board_comments (post_id, user_id, text, created_at) VALUES (?, ?, ?, ?)", (post_id, user_id, text, _iso(now)))
    conn.commit()


def board_view(conn, user_id, present_location, level, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    settle(conn, now)
    chain = chain_of(present_location)
    g = group_for(chain, level)
    if not g:
        return None
    if level == "earth":
        member_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    else:
        member_count = conn.execute(
            f"SELECT COUNT(*) FROM users WHERE json_extract(present_location_json, '$.{level}.id') = ?", (g["id"],)
        ).fetchone()[0]
    import wallet_core
    qoins = wallet_core.wallet_balance(conn, level, g["id"])
    rows = conn.execute(
        """SELECT p.*, u.name AS author_name, v.value AS my_vote FROM board_posts p
           JOIN users u ON u.id = p.author_id
           LEFT JOIN board_votes v ON v.post_id = p.id AND v.user_id = ?
           WHERE p.group_id = ? AND p.level = ? AND p.status != 'removed' ORDER BY p.created_at DESC, p.id DESC LIMIT 100""",
        (user_id, g["id"], level),
    ).fetchall()
    posts = []
    for p in rows:
        active = p["status"] == "active"
        comments = []
        if not active:
            comments = [{"who": c["name"], "text": c["text"], "at": c["created_at"]} for c in conn.execute(
                "SELECT c.text, c.created_at, u.name FROM board_comments c JOIN users u ON u.id = c.user_id WHERE c.post_id=? ORDER BY c.id LIMIT 50", (p["id"],))]
        origin = None
        if p["origin_post_id"]:
            o = conn.execute("SELECT level, score FROM board_posts WHERE id=?", (p["origin_post_id"],)).fetchone()
            origin = {"level": LEVEL_LABEL[o["level"]], "score": o["score"]} if o else None
        nxt = None
        if p["elevated_to"]:
            e = conn.execute("SELECT level FROM board_posts WHERE id=?", (p["elevated_to"],)).fetchone()
            nxt = LEVEL_LABEL[e["level"]] if e else None
        posts.append({
            "id": p["id"], "author": p["author_name"], "mine": p["author_id"] == user_id, "content": p["content"], "status": p["status"],
            "score": p["score"], "my_vote": p["my_vote"], "created_at": p["created_at"], "voting_end": p["voting_end"],
            "threshold": THRESHOLD[level], "window_days": WINDOW_DAYS[level], "origin": origin, "elevated_to": nxt, "comments": comments,
            "can_vote": active, "can_comment": not active,
        })
    post_price = None if level not in PAID_LEVELS else qoin_core.post_price(level, "text")
    currency_code, currency_symbol, currency_name = qoin_core.currency_for((present_location.get("country") or {}).get("code"))
    return {
        "level": level, "label": LEVEL_LABEL[level], "group": g["name"], "group_id": g["id"],
        "members": member_count, "qoins": qoins,
        "can_post": level == "village", "can_pay_post": level in PAID_LEVELS,
        # A paid post is priced in local currency and paid in the Qoins that make it up (qoin_core.to_qoins) --
        # the price shown to the user must always name BOTH, never a bare Qoin count (docs/qoins_wallet_system.md).
        "post_price": post_price,
        "post_price_qoins": None if post_price is None else qoin_core.to_qoins(post_price),
        "currency": currency_code, "currency_symbol": currency_symbol, "currency_name": currency_name,
        "threshold": THRESHOLD[level], "window_days": WINDOW_DAYS[level], "posts": posts,
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
    cur = conn.execute("INSERT INTO subgroups (village_id, name, description, admin_label, created_by, created_at) VALUES (?,?,?,?,?,?)",
                       (village_id, name, (description or "").strip()[:200], label, admin_id, _now_iso()))
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
    conn.execute("INSERT INTO subgroup_members VALUES (?,?,?,?)", (sg_id, user_id, "pending", _now_iso()))
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
        "SELECT m.id, m.text, m.created_at, m.user_id, u.name, u.account_id FROM board_messages m JOIN users u ON u.id=m.user_id "
        "WHERE m.subgroup_id=? ORDER BY m.id DESC LIMIT 100", (sg_id,)).fetchall()))
    member_count = conn.execute("SELECT COUNT(*) FROM subgroup_members WHERE subgroup_id=? AND status='approved'", (sg_id,)).fetchone()[0] + 1  # +owner
    reactions = reactions_core.counts_for(conn, "subgroup", [r["id"] for r in rows], user_id)
    return {"id": g["id"], "name": g["name"], "admin_label": g["admin_label"] or "Village Council", "members": member_count,
            "messages": [{"id": r["id"], "who": r["name"], "account_id": r["account_id"], "mine": r["user_id"] == user_id,
                         "text": r["text"], "at": r["created_at"], "reactions": reactions[r["id"]]} for r in rows]}


def send_message(conn, user_id, sg_id, text, is_admin):
    _subgroup(conn, sg_id)
    if not _can_chat(conn, user_id, sg_id, is_admin):
        raise PermissionError("Ask the council to add you to this group")
    text = (text or "").strip()
    if not text or len(text) > 1000:
        raise ValueError("Write a message (up to 1000 characters)")
    conn.execute("INSERT INTO board_messages (subgroup_id, user_id, text, created_at) VALUES (?,?,?,?)", (sg_id, user_id, text, _now_iso()))
    conn.commit()


def register_volunteer(conn, user_id, present_location, skill):
    v = present_location.get("village")
    if not v or not v.get("id"):
        raise ValueError("Volunteering is open to people living in a village")
    skill = (skill or "").strip()
    if not 2 <= len(skill) <= 80:
        raise ValueError("Tell us what you do (2–80 characters), e.g. vegetable seller, electrician")
    conn.execute("INSERT OR REPLACE INTO volunteers VALUES (?,?,?,?,?,?)", (user_id, "village", v["id"], "volunteer", skill, _now_iso()))
    conn.commit()


# ---- Referrers: village volunteers who hold a referral code, approved by a council member ----

def apply_as_referrer(conn, user_id, note):
    if conn.execute("SELECT 1 FROM referrer_applications WHERE user_id=? AND status='pending'", (user_id,)).fetchone():
        raise ValueError("You already have an application waiting for review")
    if conn.execute("SELECT 1 FROM referrers WHERE user_id=?", (user_id,)).fetchone():
        raise ValueError("You already hold a referral code")
    conn.execute("INSERT INTO referrer_applications (user_id, note, created_at) VALUES (?,?,?)", (user_id, (note or "").strip()[:300], _now_iso()))
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
