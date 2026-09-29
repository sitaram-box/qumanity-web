"""Qumanity — Global Timeline standalone prototype.

Serves the homepage (rotating Earth, India highlighted, Global Timeline
overlay) and a small JSON API backed by static/data/global.json for now.

This is intentionally disconnected from the main Qumanity platform
(identity_core.py / global_core.py / app.py) so the visual flow can be
iterated on quickly. It uses the same location-path and ID conventions
(Zone.State.District.Tehsil.Village, e.g. CS.DL.5.4.1E) so the sample
data can be swapped for the real backend later without changing the
frontend contract.
"""

import datetime as dt
import functools
import json
import os
import re
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import election_core
import elemental_core
import folder_connector
import folder_sync
import id_generator
import lunar_core
import board_core
import karma_core
import notify_core
import perception_core
import qoin_core
import reactions_core
import recovery_core
import review_core
import social_core
import timebox_core
import wallet_core
import zodiac_core
from db import get_db

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "static" / "data" / "global.json"
WORLD_DATA_FILE = BASE_DIR / "static" / "data" / "global_countries.json"
INDIA_STATES_FILE = BASE_DIR / "static" / "data" / "india_states.json"
INDIA_DISTRICTS_FILE = BASE_DIR / "static" / "data" / "india_districts_tehsils.json"
# Real 2011-census district polygons (760 features, grouped by state name) --
# the exact source build_india_states_geojson.py dissolved states from. Used
# only for the registration wizard's decorative "selected state" overlay map;
# NOT the same district taxonomy as INDIA_DISTRICTS_FILE (that's SITAXML-
# derived), so this is never used to resolve or validate a district selection.
INDIA_DISTRICT_SHAPES_FILE = BASE_DIR / "scripts" / "_india_districts_source.geojson"
# Mother-tongue choices offered at registration: English (common to all), 12 Indian
# languages and 10 other Indian Sub-continent languages.
LANGUAGES_FILE = BASE_DIR / "static" / "data" / "languages.json"


def _language_names():
    data = _load_json(LANGUAGES_FILE)
    return {l["name"] for g in ("common", "indian", "subcontinent") for l in data[g]}


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _language_table():
    """{english name: {code, name, native}} for every selectable language."""
    data = _load_json(LANGUAGES_FILE)
    return {l["name"]: l for g in ("common", "indian", "subcontinent") for l in data[g]}


def _ensure_user_columns():
    """Small in-place migrations for columns added after the first schema."""
    conn = get_db()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "daily_language" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN daily_language TEXT")
    for col, ddl in (
        ("private_id_9digit", "TEXT"), ("pin_hash", "TEXT"), ("pin_fails", "INTEGER DEFAULT 0"), ("pin_locked_until", "TEXT"),
        # Relationship status + work profile (Private account, 2026-09-28): self-service, no council
        # approval needed -- they don't touch kundali/zodiac/location like the FOUNDATIONAL_FIELDS do.
        ("relationship_status", "TEXT"), ("has_children", "INTEGER"), ("sons_count", "INTEGER DEFAULT 0"), ("daughters_count", "INTEGER DEFAULT 0"),
        ("work_profile", "TEXT"), ("work_profile_other", "TEXT"),
        # "Register a new member": who registered this person (their referrer), 2026-09-29.
        ("referred_by_user_id", "INTEGER"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code ON users(private_id_9digit)")
    conn.commit()
    conn.close()


def _user_languages(user):
    """A user's language list, at most 3: mother tongue, English (everyone), optional daily-use language."""
    table = _language_table()
    out, seen = [], set()
    for kind, name in (("mother", user["language"]), ("english", "English"), ("daily", user["daily_language"])):
        if name and name in table and name not in seen:
            seen.add(name)
            out.append({"kind": kind, "name": name, "code": table[name]["code"], "native": table[name]["native"]})
    return out


app = Flask(__name__)
# Prototype-only secret key — override via QM_SECRET_KEY for any real deployment.
app.secret_key = os.environ.get("QM_SECRET_KEY", "dev-insecure-secret-change-me")


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ---- Phone app (Desktop/Qumanity_App) sign-in ----
# The app sends "Authorization: Bearer <token>" instead of a browser cookie. A valid
# token signs the request in exactly like a website session, so every /api route
# serves the app unchanged. Changing the PIN invalidates the person's old tokens.
APP_TOKEN_DAYS = 30


def _token_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="qm-app-token")


def _pin_fingerprint(pin_hash):
    return (pin_hash or "")[-16:]


def _issue_app_token(user_id, pin_hash):
    return _token_serializer().dumps({"uid": user_id, "pv": _pin_fingerprint(pin_hash)})


@app.before_request
def _app_token_auth():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        data = _token_serializer().loads(header[7:], max_age=APP_TOKEN_DAYS * 86400)
    except BadSignature:  # also covers expired tokens
        return jsonify({"error": "Please sign in again"}), 401
    conn = get_db()
    row = conn.execute("SELECT pin_hash FROM users WHERE id = ?", (data.get("uid"),)).fetchone()
    conn.close()
    if not row or _pin_fingerprint(row["pin_hash"]) != data.get("pv"):
        return jsonify({"error": "Please sign in again"}), 401
    session["user_id"] = data["uid"]
    return None


@app.route("/")
def index():
    return render_template("home.html")


@app.route("/register")
def register():
    """Registration wizard: Step 1 (Private Account: personal details,
    contact info, password) -> Step 2 (Global Account: birth + present
    location, Continent -> Country; birth anywhere on Earth, present in one
    of the 10 Indian Sub-continent countries) -> Step 3 (Public Account:
    Zone/State/District/Tehsil/Village for India, each country's own tiers
    for the rest) -> Step 4 (Review & Submit). Kundali
    is not shown here -- see /dashboard after login."""
    return render_template("register.html", languages=_load_json(LANGUAGES_FILE),
                           test_pin=os.environ.get("QM_TEST_PIN", ""))


@app.route("/about")
def about():
    """About Qumanity (Quantum + Humanity): vision, architecture, identity,
    timelines, Qoins, Quantum Punch governance, status and roadmap -- written
    from the SITA Foundation manuscripts and briefs."""
    return render_template("about.html")


@app.route("/elements")
def elements_dashboard():
    """Elemental Dashboard: location-level selector over the Fire/Earth/
    Air/Water distribution of registered users, plus the lunar timeline."""
    return render_template("elements.html")


@app.route("/india-map")
def india_map_demo():
    """Standalone demo of the India Zone/State map component (Part 3 of
    the Public Location Selection Tool brief) — the same component is
    also embedded in the registration wizard's India location sub-flow."""
    return render_template("india_map.html")


@app.route("/location-select")
def location_select_demo():
    """Standalone demo of the full Location Selection Tool: India map ->
    Zone/State/District/Tehsil nested tabs with clear buttons (Part 4)."""
    return render_template("location_select.html")


@app.route("/kundali/<int:user_id>")
def kundali_view(user_id):
    """A user's private kundali view — revisitable after registration,
    since there's no login/session system yet to land on a dashboard."""
    conn = get_db()
    user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return render_template("kundali_not_found.html", user_id=user_id), 404
    return render_template("kundali_view.html", user_id=user_id, name=user["name"])


PIN_MAX_TRIES = 5
PIN_LOCK_MINUTES = 15


@app.route("/login", methods=["GET", "POST"])
def login():
    """Sign in with the 9-digit Private ID and a 5-digit PIN. Five wrong PINs lock that ID for 15 minutes."""
    if request.method == "GET":
        return render_template("login.html")

    data = request.get_json(silent=True) or request.form
    code = re.sub(r"\D", "", data.get("private_id") or "")
    pin = (data.get("pin") or "").strip()
    generic = jsonify({"error": "Invalid Private ID or PIN"}), 401
    if not re.fullmatch(r"\d{9}", code) or not re.fullmatch(r"\d{5}", pin):
        return generic
    conn = get_db()
    user = conn.execute("SELECT id, pin_hash, pin_fails, pin_locked_until FROM users WHERE private_id_9digit = ?", (code,)).fetchone()
    now = dt.datetime.now(dt.timezone.utc)
    if user and user["pin_locked_until"] and dt.datetime.fromisoformat(user["pin_locked_until"]) > now:
        conn.close()
        return jsonify({"error": "Too many wrong PINs. Try again in a few minutes."}), 429
    if not user or not user["pin_hash"] or not check_password_hash(user["pin_hash"], pin):
        if user:
            fails = (user["pin_fails"] or 0) + 1
            lock = (now + dt.timedelta(minutes=PIN_LOCK_MINUTES)).isoformat() if fails >= PIN_MAX_TRIES else None
            conn.execute("UPDATE users SET pin_fails = ?, pin_locked_until = ? WHERE id = ?", (0 if lock else fails, lock, user["id"]))
            conn.commit()
        conn.close()
        return generic
    conn.execute("UPDATE users SET pin_fails = 0, pin_locked_until = NULL WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()
    session["user_id"] = user["id"]
    body = {"status": "success", "redirect": url_for("dashboard")}
    if data.get("client") == "app":
        body["token"] = _issue_app_token(user["id"], user["pin_hash"])
    return jsonify(body)


@app.route("/forgot-pin")
def forgot_pin_page():
    return render_template("forgot_pin.html")


@app.route("/recover-id")
def recover_id_page():
    return render_template("recover_id.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


def _location_display(location: dict) -> str:
    parts = []
    for key in ("continent", "country", "state", "district", "tehsil", "village"):
        node = location.get(key)
        if node and node.get("name"):
            parts.append(node["name"])
    return " › ".join(parts) if parts else "—"


SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
NAKSHATRAS = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha", "Magha",
              "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula",
              "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]
NAKSHATRA_LORDS = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"] * 3


def _nakshatra_of(sign, degree):
    lon = SIGNS.index(sign) * 30 + float(degree)
    i = int(lon // (360 / 27)) % 27
    return NAKSHATRAS[i], NAKSHATRA_LORDS[i], int((lon % (360 / 27)) // (360 / 108)) + 1


def _kundali_view(kundali):
    """Rows for the Kundali table + the 12 houses, from the stored chart JSON."""
    if not kundali:
        return None
    rows = []
    def row(name, d, nak=None):
        n = nak or _nakshatra_of(d["sign"], d["degree"])[0]
        _, lord, pada = _nakshatra_of(d["sign"], d["degree"])
        d_int = int(d["degree"]); minutes = int(round((d["degree"] - d_int) * 60))
        rows.append({"planet": name, "sign": d["sign"], "degree": f"{d_int}°{minutes:02d}′", "nakshatra": n, "lord": lord, "pada": pada})
    row("Ascendant", kundali["ascendant"]); row("Sun", kundali["sun"]); row("Moon", kundali["moon"])
    for name, d in kundali["planets"].items():
        row(name, d)
    houses = [{"n": int(n), "sign": h["sign"], "planets": [x.strip() for x in h["planet"].split(",") if x.strip()]}
              for n, h in sorted(kundali["houses"].items(), key=lambda kv: int(kv[0]))]
    return {"rows": rows, "houses": houses}


@app.route("/api/timebox")
@login_required
def api_timebox():
    conn = get_db()
    user = _current_user_row(conn)
    conn.close()
    return jsonify(timebox_core.timebox(json.loads(user["present_location_json"])))


# ---- Collective Board (posts voted up from Village to Earth) and Q-Punch council ----

def _board_user():
    conn = get_db()
    board_core.ensure_tables(conn)
    board_core.ensure_sub_tables(conn)
    user = _current_user_row(conn)
    return conn, user, json.loads(user["present_location_json"])


def _board_error(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
    return wrapper


@app.route("/api/board/<level>")
@login_required
@_board_error
def api_board(level):
    if level not in board_core.LEVELS:
        return jsonify({"error": "Unknown level"}), 404
    conn, user, loc = _board_user()
    view = board_core.board_view(conn, user["id"], loc, level)
    conn.close()
    if view is None:
        return jsonify({"error": "You have no group at this level"}), 404
    return jsonify(view)


@app.route("/api/board/post", methods=["POST"])
@login_required
@_board_error
def api_board_post():
    data = request.get_json(silent=True) or {}
    conn, user, loc = _board_user()
    pid = board_core.create_post(conn, user["id"], loc, data.get("content"), data.get("level", "village"))
    conn.close()
    return jsonify({"id": pid}), 201


@app.route("/api/board/vote", methods=["POST"])
@login_required
@_board_error
def api_board_vote():
    data = request.get_json(silent=True) or {}
    conn, user, loc = _board_user()
    try:
        score = board_core.cast_vote(conn, user["id"], loc, int(data.get("post_id", 0)), int(data.get("value", 9)))
    finally:
        conn.close()
    return jsonify({"score": score})


@app.route("/api/board/comment", methods=["POST"])
@login_required
@_board_error
def api_board_comment():
    data = request.get_json(silent=True) or {}
    conn, user, loc = _board_user()
    try:
        board_core.add_comment(conn, user["id"], loc, int(data.get("post_id", 0)), data.get("text"))
    finally:
        conn.close()
    return jsonify({"status": "ok"}), 201


@app.route("/api/board/removed")
@login_required
def api_board_removed():
    conn, user, _loc = _board_user()
    posts = board_core.removed_posts(conn, user["id"])
    conn.close()
    return jsonify({"posts": posts})


def _village_id(loc):
    return (loc.get("village") or {}).get("id")


@app.route("/api/subgroups")
@login_required
def api_subgroups():
    conn, user, loc = _board_user()
    vid = _village_id(loc)
    admin = _is_admin()
    groups = board_core.list_subgroups(conn, user["id"], vid, admin) if vid else []
    conn.close()
    return jsonify({"village": (loc.get("village") or {}).get("name"), "is_admin": admin, "groups": groups})


@app.route("/api/subgroups", methods=["POST"])
@login_required
@_board_error
def api_subgroup_create():
    if not _is_admin():
        return jsonify({"error": "Only council members can create sub-groups"}), 403
    data = request.get_json(silent=True) or {}
    conn, user, loc = _board_user()
    try:
        sid = board_core.create_subgroup(conn, user["id"], _village_id(loc), data.get("name"), data.get("description"), data.get("admin_label"))
    finally:
        conn.close()
    return jsonify({"id": sid}), 201


@app.route("/api/subgroups/<int:sg_id>/join", methods=["POST"])
@login_required
@_board_error
def api_subgroup_join(sg_id):
    conn, user, loc = _board_user()
    try:
        board_core.request_join(conn, user["id"], loc, sg_id)
    finally:
        conn.close()
    return jsonify({"status": "pending"}), 201


@app.route("/api/subgroups/<int:sg_id>/decide", methods=["POST"])
@login_required
@_board_error
def api_subgroup_decide(sg_id):
    if not _is_admin():
        return jsonify({"error": "Only council members can approve"}), 403
    data = request.get_json(silent=True) or {}
    conn, _user, _loc = _board_user()
    try:
        board_core.decide_join(conn, sg_id, int(data.get("user_id", 0)), bool(data.get("approve")))
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/chat/<int:sg_id>", methods=["GET", "POST"])
@login_required
@_board_error
def api_subgroup_chat(sg_id):
    conn, user, _loc = _board_user()
    try:
        if request.method == "POST":
            board_core.send_message(conn, user["id"], sg_id, (request.get_json(silent=True) or {}).get("text"), _is_admin())
            return jsonify({"status": "ok"}), 201
        return jsonify(board_core.chat_messages(conn, user["id"], sg_id, _is_admin()))
    finally:
        conn.close()


@app.route("/api/registration/donation-preview")
def api_donation_preview():
    """?amount=&referrer=1 -> the live distribution shown on the registration donation panel."""
    try:
        amount = int(request.args.get("amount", "0"))
    except ValueError:
        return jsonify({"error": "amount must be a whole number"}), 400
    amount = max(0, min(amount, qoin_core.MAX_DONATION))
    has_referrer = request.args.get("referrer") in ("1", "true", "yes")
    if amount == 0:
        share = 10
        rows = [("earth", share), ("continent", share), ("country", share), ("zone", share), ("state", share),
                ("district", share), ("tehsil", share), ("village", share),
                ("referrer", share if has_referrer else 0), ("new_user", share + (0 if has_referrer else share))]
        return jsonify({"amount": 0, "unit": "paisa", "rows": rows, "note": "A free account still mints ₹1 of Qoins, shared 10 paise at a time."})
    if has_referrer:
        split = wallet_core.calculate_donation_distribution(amount, True)
        rows = [(t, split["location_share_per_tier"]) for t in wallet_core.LOCATION_TIERS] + \
               [("referrer", split["referrer_share"]), ("new_user", split["self_share"])]
        return jsonify({"amount": amount, "unit": "rupees", "rows": rows})
    topup = qoin_core.topup_split(amount)
    return jsonify({"amount": amount, "unit": "rupees", "rows": [("new_user", topup["own"]), ("village", topup["village"])],
                    "qoins": {"new_user": topup["own_qoins"], "village": topup["village_qoins"]}})


@app.route("/api/referrer/apply", methods=["POST"])
@login_required
@_board_error
def api_referrer_apply():
    conn, user, _loc = _board_user()
    try:
        board_core.apply_as_referrer(conn, user["id"], (request.get_json(silent=True) or {}).get("note"))
    finally:
        conn.close()
    return jsonify({"status": "pending"}), 201


@app.route("/api/referrer/me")
@login_required
def api_referrer_me():
    conn = get_db()
    board_core.ensure_sub_tables(conn)
    code = board_core.my_referrer_code(conn, session["user_id"])
    pending = conn.execute("SELECT 1 FROM referrer_applications WHERE user_id=? AND status='pending'", (session["user_id"],)).fetchone()
    conn.close()
    return jsonify({"code": code, "pending": bool(pending)})


@app.route("/api/referrer/applications")
@login_required
def api_referrer_applications():
    if not _is_admin():
        return jsonify({"error": "Only council members can review applications"}), 403
    conn = get_db()
    board_core.ensure_sub_tables(conn)
    apps = board_core.list_referrer_applications(conn)
    conn.close()
    return jsonify({"applications": apps})


@app.route("/api/referrer/applications/<int:app_id>/decide", methods=["POST"])
@login_required
@_board_error
def api_referrer_decide(app_id):
    if not _is_admin():
        return jsonify({"error": "Only council members can review applications"}), 403
    approve = bool((request.get_json(silent=True) or {}).get("approve"))
    conn = get_db()
    board_core.ensure_sub_tables(conn)
    try:
        code = board_core.decide_referrer_application(conn, session["user_id"], app_id, approve)
    finally:
        conn.close()
    return jsonify({"status": "ok", "code": code})


@app.route("/api/reactions/<scope>/<int:message_id>", methods=["POST"])
@login_required
@_board_error
def api_set_reaction(scope, message_id):
    if scope not in ("subgroup", "personal"):
        return jsonify({"error": "Unknown scope"}), 404
    conn = get_db()
    try:
        reactions_core.set_reaction(conn, scope, message_id, session["user_id"], (request.get_json(silent=True) or {}).get("reaction"))
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/qpunch/volunteer", methods=["POST"])
@login_required
@_board_error
def api_qpunch_volunteer():
    conn, user, loc = _board_user()
    try:
        board_core.register_volunteer(conn, user["id"], loc, (request.get_json(silent=True) or {}).get("skill"))
    finally:
        conn.close()
    return jsonify({"status": "ok"}), 201


@app.route("/api/qpunch/<level>")
@login_required
def api_qpunch(level):
    """The 5 Quantum Punch council seats of the user's group at this level."""
    if level not in board_core.LEVELS:
        return jsonify({"error": "Unknown level"}), 404
    conn, user, loc = _board_user()
    g = board_core.group_for(board_core.chain_of(loc), level)
    if not g:
        conn.close()
        return jsonify({"error": "You have no group at this level"}), 404
    if level == "earth":
        residents = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    else:
        residents = conn.execute(f"SELECT COUNT(*) FROM users WHERE json_extract(present_location_json, '$.{level}.id') = ?", (g["id"],)).fetchone()[0]
    vols = conn.execute("SELECT COUNT(*) FROM volunteers WHERE level = ? AND group_id = ? AND kind = 'volunteer'", (level, g["id"])).fetchone()[0]
    agents = conn.execute("SELECT COUNT(*) FROM volunteers WHERE level = ? AND group_id = ? AND kind = 'agent'", (level, g["id"])).fetchone()[0]
    mine = conn.execute("SELECT 1 FROM volunteers WHERE user_id = ? AND level = ? AND group_id = ? AND kind = 'volunteer'", (user["id"], level, g["id"])).fetchone()
    # The monthly 4-week election (piloted in one village): timeline, candidates, winners, and what
    # THIS member should do this month.
    election = guide = None
    if level == "village" and g["id"] == election_core.PILOT_VILLAGE_ID:
        election = election_core.election_summary(conn, g["id"])
        cycle = election_core.current_cycle_for_village(conn, g["id"])
        guide = election_core.member_guide(conn, user, cycle)
    conn.close()

    today = zodiac_core.get_zodiac_sign(dt.date.today())
    village = level == "village"
    lead = today["sign"] if village else today["element"]
    lead_kind = "sun-sign" if village else "element"
    return jsonify({
        "level": level, "label": board_core.LEVEL_LABEL[level], "group": g["name"], "group_id": g["id"], "residents": residents,
        "election_min": board_core.MIN_RESIDENTS[level], "election_open": residents >= board_core.MIN_RESIDENTS[level],
        "cycle": {"sign": today["sign"], "element": today["element"], "lead": lead, "kind": lead_kind},
        "volunteers": vols, "agents": agents, "can_volunteer": village and not mine, "is_volunteer": bool(mine),
        "is_admin": _is_admin(),
        "election": election, "guide": guide,
        "seats": [
            {"seat": 1, "title": "Founder / Admin", "filled": True, "name": None,
             "text": "Guides and safeguards every group from Village to Earth. The Founder's personal identity is kept private."},
            {"seat": 2, "title": f"{lead} Male Leader", "filled": False,
             "text": (f"This month is the {today['sign']} cycle: the man elected for {today['sign']} leads the village. " if village else
                      f"This month runs on {today['element']}: the man elected for {today['element']} leads this group. ")
                     + "He serves only during this month and is then released. Next year he can stand again, or stand for the next council up."},
            {"seat": 3, "title": f"{lead} Female Leader", "filled": False,
             "text": (f"The woman elected for {today['sign']} leads alongside for the same month." if village else
                      f"The woman elected for {today['element']} leads alongside for the same month.")
                     + " Voters read each candidate's record, behaviour and promises first."},
            {"seat": 4, "title": "Managers", "filled": False,
             "text": "A team hired by the council to run every service of this group, from village to Earth. There can be many managers in this one seat."},
            {"seat": 5, "title": "Agents & Volunteers", "filled": False,
             "text": ("Volunteers are local people who serve and earn: vegetable sellers, skilled workers, the unemployed — anyone can register. "
                      if village else "") + "Agents are hired for professional services; they act on requests, approve permissions and resolve citizens' matters directly."},
        ],
    })


@app.route("/api/user/private-code", methods=["POST"])
@login_required
def api_private_code():
    """Reveal the user's own 9-digit Private ID, but only after they type their PIN again."""
    pin = str((request.get_json(silent=True) or {}).get("pin", ""))
    conn = get_db()
    user = _current_user_row(conn)
    conn.close()
    if not user["pin_hash"] or not check_password_hash(user["pin_hash"], pin):
        return jsonify({"error": "That PIN is not correct"}), 403
    return jsonify({"private_code": user["private_id_9digit"]})


# ---- Personal timeline: Family / Friends / Business / Custom groups, private chats, search ----

def _social(conn):
    social_core.ensure_tables(conn)
    return conn


@app.route("/api/people/search")
@login_required
def api_people_search():
    conn = _social(get_db())
    person = social_core.find_person(conn, request.args.get("q", ""))
    conn.close()
    if not person:
        return jsonify({"error": "No one found with that ID"}), 404
    if person["user_id"] == session["user_id"]:
        return jsonify({"error": "That's you!"}), 400
    return jsonify(person)


@app.route("/api/people/account-ids/switch", methods=["POST"])
@login_required
@_board_error
def api_switch_account():
    row_id = int((request.get_json(silent=True) or {}).get("row_id", 0))
    conn = _social(get_db())
    try:
        social_core.switch_account(conn, session["user_id"], row_id)
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/people/account-ids/request", methods=["POST"])
@login_required
@_board_error
def api_request_account():
    present = (request.get_json(silent=True) or {}).get("present_location") or {}
    conn = _social(get_db())
    try:
        social_core.request_new_account(conn, session["user_id"], present)
    finally:
        conn.close()
    return jsonify({"status": "pending"}), 201


@app.route("/api/admin/account-ids")
@login_required
def api_admin_account_requests():
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = _social(get_db())
    items = social_core.list_account_requests(conn)
    conn.close()
    return jsonify({"requests": items})


@app.route("/api/admin/account-ids/<int:request_id>/decide", methods=["POST"])
@login_required
@_board_error
def api_admin_account_decide(request_id):
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    approve = bool((request.get_json(silent=True) or {}).get("approve"))
    conn = _social(get_db())
    try:
        social_core.decide_account_request(conn, session["user_id"], request_id, approve)
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/people/me")
@login_required
def api_people_me():
    conn = _social(get_db())
    code = social_core.my_search_code(conn, session["user_id"])
    history = social_core.my_account_history(conn, session["user_id"])
    requests = social_core.my_account_requests(conn, session["user_id"])
    conn.close()
    return jsonify({"search_code": code, "account_history": history, "account_requests": requests})


@app.route("/api/people/groups")
@login_required
def api_people_groups():
    conn = _social(get_db())
    groups = social_core.my_groups(conn, session["user_id"], _is_admin())
    conn.close()
    return jsonify(groups)


@app.route("/api/people/groups/create", methods=["POST"])
@login_required
@_board_error
def api_people_group_create():
    data = request.get_json(silent=True) or {}
    conn = _social(get_db())
    try:
        gid = social_core.create_group(conn, session["user_id"], data.get("category"), data.get("name"))
    finally:
        conn.close()
    return jsonify({"id": gid}), 201


@app.route("/api/people/groups/<int:group_id>/move", methods=["POST"])
@login_required
@_board_error
def api_people_group_move(group_id):
    data = request.get_json(silent=True) or {}
    conn = _social(get_db())
    try:
        social_core.move_group(conn, session["user_id"], group_id, data.get("category"))
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/people/groups/<int:group_id>/business", methods=["POST"])
@login_required
@_board_error
def api_people_business(group_id):
    data = request.get_json(silent=True) or {}
    conn = _social(get_db())
    try:
        social_core.set_business_profile(conn, session["user_id"], group_id, data.get("name"), data.get("sector"), data.get("services"))
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/people/groups/<int:group_id>/rate", methods=["GET", "POST"])
@login_required
@_board_error
def api_people_business_rate(group_id):
    """Commercial karma (docs/karma.md): rate a business in your own present village. GET returns
    every rating left on it (public, like a reviews list); POST casts or updates the caller's own."""
    conn = get_db()
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            result = karma_core.rate_business(conn, session["user_id"], group_id, data.get("stars"), data.get("comment"))
            return jsonify(result)
        return jsonify({"ratings": karma_core.business_ratings(conn, group_id)})
    finally:
        conn.close()


@app.route("/api/karma/me")
@login_required
def api_karma_me():
    conn = get_db()
    score = karma_core.individual_karma_score(conn, session["user_id"])
    history = karma_core.individual_karma_history(conn, session["user_id"])
    conn.close()
    return jsonify({"score": score, "history": history})


@app.route("/api/karma/user/<int:user_id>")
@login_required
def api_karma_user(user_id):
    """A karma score visible on someone else's public profile / candidate card -- the running
    total only, never their private history."""
    conn = get_db()
    score = karma_core.individual_karma_score(conn, user_id)
    conn.close()
    return jsonify({"score": score})


@app.route("/api/karma/collective/<level>/<path:location_id>")
def api_karma_collective(level, location_id):
    if level not in board_core.LEVELS:
        return jsonify({"error": "Unknown level"}), 404
    conn = get_db()
    points = karma_core.collective_karma_score(conn, location_id, level)
    conn.close()
    return jsonify({"location_id": location_id, "level": level, "points": points})


@app.route("/api/people/groups/<int:group_id>/rename", methods=["POST"])
@login_required
@_board_error
def api_people_rename(group_id):
    conn = _social(get_db())
    try:
        social_core.rename_group(conn, session["user_id"], group_id, (request.get_json(silent=True) or {}).get("name"))
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/people/groups/<int:group_id>/messages", methods=["GET", "POST"])
@login_required
@_board_error
def api_people_group_messages(group_id):
    conn = _social(get_db())
    try:
        if request.method == "POST":
            social_core.send_group_message(conn, session["user_id"], group_id, (request.get_json(silent=True) or {}).get("text"))
            notify_core.mark_read(conn, session["user_id"], "group", group_id)
            return jsonify({"status": "ok"}), 201
        result = jsonify(social_core.group_messages(conn, session["user_id"], group_id))
        notify_core.mark_read(conn, session["user_id"], "group", group_id)
        return result
    finally:
        conn.close()


@app.route("/api/people/invite", methods=["POST"])
@login_required
@_board_error
def api_people_invite():
    data = request.get_json(silent=True) or {}
    conn = _social(get_db())
    try:
        social_core.send_group_invite(conn, session["user_id"], int(data.get("group_id", 0)), int(data.get("user_id", 0)))
    finally:
        conn.close()
    return jsonify({"status": "sent"}), 201


@app.route("/api/people/message", methods=["POST"])
@login_required
@_board_error
def api_people_message_request():
    data = request.get_json(silent=True) or {}
    conn = _social(get_db())
    try:
        social_core.send_message_request(conn, session["user_id"], int(data.get("user_id", 0)), data.get("text"))
    finally:
        conn.close()
    return jsonify({"status": "sent"}), 201


@app.route("/api/people/inbox")
@login_required
def api_people_inbox():
    conn = _social(get_db())
    items = social_core.inbox(conn, session["user_id"])
    conn.close()
    return jsonify({"requests": items})


@app.route("/api/people/inbox/<int:request_id>/decide", methods=["POST"])
@login_required
@_board_error
def api_people_decide(request_id):
    decision = (request.get_json(silent=True) or {}).get("decision")
    conn = _social(get_db())
    try:
        result = social_core.decide_request(conn, session["user_id"], request_id, decision)
    finally:
        conn.close()
    return jsonify(result)


@app.route("/api/people/chats")
@login_required
def api_people_chats():
    conn = _social(get_db())
    chats = social_core.my_chats(conn, session["user_id"])
    conn.close()
    return jsonify({"chats": chats})


@app.route("/api/people/chats/<int:chat_id>", methods=["GET", "POST"])
@login_required
@_board_error
def api_people_chat_messages(chat_id):
    conn = _social(get_db())
    try:
        if request.method == "POST":
            social_core.send_chat_message(conn, session["user_id"], chat_id, (request.get_json(silent=True) or {}).get("text"))
            notify_core.mark_read(conn, session["user_id"], "private", chat_id)
            return jsonify({"status": "ok"}), 201
        result = jsonify(social_core.chat_messages(conn, session["user_id"], chat_id))
        notify_core.mark_read(conn, session["user_id"], "private", chat_id)
        return result
    finally:
        conn.close()


@app.route("/api/people/chats/<int:chat_id>/rename", methods=["POST"])
@login_required
@_board_error
def api_people_chat_rename(chat_id):
    name = (request.get_json(silent=True) or {}).get("name")
    conn = _social(get_db())
    try:
        social_core.rename_chat(conn, session["user_id"], chat_id, name)
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/people/chats/<int:chat_id>/leave", methods=["POST"])
@login_required
@_board_error
def api_people_chat_leave(chat_id):
    conn = _social(get_db())
    try:
        social_core.leave_chat(conn, session["user_id"], chat_id)
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/people/chats/<int:chat_id>/request-rejoin", methods=["POST"])
@login_required
@_board_error
def api_people_chat_rejoin(chat_id):
    conn = _social(get_db())
    try:
        social_core.request_rejoin(conn, session["user_id"], chat_id)
    finally:
        conn.close()
    return jsonify({"status": "sent"}), 201


# ---- Notifications (unread Personal-timeline chats + pending people-requests) ----

@app.route("/api/notifications/summary")
@login_required
def api_notifications_summary():
    conn = get_db()
    result = notify_core.summary(conn, session["user_id"])
    result["election"] = None
    user = _current_user_row(conn)
    try:
        loc = json.loads(user["present_location_json"])
        if (loc.get("village") or {}).get("id") == election_core.PILOT_VILLAGE_ID:
            cycle = election_core.current_cycle_for_village(conn, election_core.PILOT_VILLAGE_ID)
            guide = election_core.member_guide(conn, user, cycle)
            if guide["action"]:
                result["election"] = {"sign": cycle["zodiac_sign"], "week": guide["week"], "action": guide["action"], "text": guide["text"]}
                result["total"] += 1
    finally:
        conn.close()
    return jsonify(result)


@app.route("/api/notifications/mark-read", methods=["POST"])
@login_required
@_board_error
def api_notifications_mark_read():
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        notify_core.mark_read(conn, session["user_id"], data.get("kind"), int(data.get("id", 0)))
    finally:
        conn.close()
    return jsonify({"status": "ok"})


# ---- Wallet weekly history (private wallet, and every location wallet for its council) ----

@app.route("/api/wallet/history")
@login_required
def api_wallet_history():
    conn = get_db()
    include_older = _is_admin()
    history = wallet_core.weekly_history(conn, "user", str(session["user_id"]), include_older=include_older)
    conn.close()
    return jsonify(history)


@app.route("/api/wallet/history/<location_type>/<path:location_id>")
@login_required
def api_wallet_location_history(location_type, location_id):
    if location_type not in wallet_core.LOCATION_TIERS:
        return jsonify({"error": "Unknown location_type"}), 404
    is_council = _is_admin()  # placeholder until real elected council seats exist per level
    conn = get_db()
    history = wallet_core.weekly_history(conn, location_type, location_id, include_older=is_council)
    conn.close()
    history["is_council"] = is_council
    return jsonify(history)


# ---- Election history (private, optional) ----

@app.route("/api/election-history", methods=["GET", "POST"])
@login_required
@_board_error
def api_election_history():
    conn = get_db()
    try:
        user = _current_user_row(conn)
        country_code = (json.loads(user["present_location_json"]).get("country") or {}).get("code", "IND")
        if request.method == "POST":
            election_core.save_party_history(conn, session["user_id"], request.get_json(silent=True) or {}, country_code)
            return jsonify({"status": "ok"})
        return jsonify({
            "party": election_core.get_party_history(conn, session["user_id"], country_code),
            "qpunch": election_core.qpunch_history(conn, session["user_id"]),
            "parties": election_core.parties_for_country(country_code),
        })
    finally:
        conn.close()


# ---- Forgotten PIN (self-service, by OTP on a phone/email already on file) ----

@app.route("/api/election-sentiment/<level>/<path:location_id>")
def api_election_sentiment(level, location_id):
    """Lok-Sabha-equivalent % breakdown on a country page, Vidhan-Sabha-equivalent on a state page.
    Nowhere else -- see election_core.loksabha_aggregate/vidhansabha_aggregate."""
    if level not in ("country", "state"):
        return jsonify({"error": "Sentiment is only shown on Country and State pages"}), 404
    conn = get_db()
    if level == "country":
        code = location_id.split("_")[-1] if "_" in location_id else location_id
        data = election_core.loksabha_aggregate(conn, location_id, code)
        label = "National Election"
    else:
        code_row = conn.execute("SELECT present_location_json FROM users WHERE json_extract(present_location_json, '$.state.id') = ? LIMIT 1", (location_id,)).fetchone()
        code = (json.loads(code_row["present_location_json"]).get("country") or {}).get("code", "IND") if code_row else "IND"
        data = election_core.vidhansabha_aggregate(conn, location_id, code)
        label = "State Election"
    conn.close()
    return jsonify(dict(data, level=level, label=label))


@app.route("/api/auth/forgot-pin/request", methods=["POST"])
def api_forgot_pin_request():
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        ok, result = recovery_core.request_pin_reset(conn, re.sub(r"\D", "", data.get("private_id") or ""), data.get("channel", ""))
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    conn.close()
    if not ok:
        return jsonify({"error": result}), 404
    body = {"status": "sent", "masked_target": result["masked_target"]}
    if os.environ.get("QM_DEV_SHOW_OTP") == "1":
        body["dev_code"] = result["dev_code"]  # simulated delivery until a real SMS/email provider is connected
    else:
        print(f"[SIMULATED OTP] {result['masked_target']}: {result['dev_code']}")  # so it's visible in the dev console
    return jsonify(body)


@app.route("/api/auth/forgot-pin/verify", methods=["POST"])
def api_forgot_pin_verify():
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        recovery_core.verify_pin_reset(conn, re.sub(r"\D", "", data.get("private_id") or ""), data.get("otp", ""), data.get("new_pin", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()
    return jsonify({"status": "ok"})


# ---- Forgotten Private ID: never self-service -- intake form, then a manual, audited, by-post reveal ----

@app.route("/api/auth/recover-id", methods=["POST"])
def api_recover_id_submit():
    conn = get_db()
    try:
        request_id = recovery_core.submit_id_recovery(conn, request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()
    return jsonify({"status": "received", "reference": f"REQ-{request_id:06d}"}), 201


@app.route("/api/admin/recover-id")
@login_required
def api_recover_id_list():
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    items = recovery_core.list_requests(conn, request.args.get("status"))
    conn.close()
    return jsonify({"requests": items})


@app.route("/api/admin/recover-id/<int:request_id>/decide", methods=["POST"])
@login_required
def api_recover_id_decide(request_id):
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        recovery_core.decide_request(conn, session["user_id"], request_id, data.get("status"), data.get("admin_note"))
    except (ValueError, LookupError) as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/admin/recover-id/<int:request_id>/reveal", methods=["POST"])
@login_required
def api_recover_id_reveal(request_id):
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    try:
        code = recovery_core.reveal_private_code(conn, session["user_id"], request_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()
    if not code:
        return jsonify({"error": "No matching account"}), 404
    return jsonify({"private_code": code})


@app.route("/api/qoins/config")
@login_required
def api_qoins_config():
    """Currency for the user's present country, the allowed Qoin values and every post price."""
    conn = get_db()
    user = _current_user_row(conn)
    conn.close()
    loc = json.loads(user["present_location_json"])
    code, symbol, name = qoin_core.currency_for((loc.get("country") or {}).get("code"))
    return jsonify({"currency": code, "symbol": symbol, "currency_name": name, "denominations": qoin_core.DENOMINATIONS,
                    "max_donation": qoin_core.MAX_DONATION, "village_prices": qoin_core.VILLAGE_PRICES, "paid_prices": qoin_core.PAID_PRICES})


@app.route("/api/qoins/preview")
def api_qoins_preview():
    """?amount=289 -> the Qoins that amount becomes, and (for donations) the top-up split."""
    try:
        amount = int(request.args.get("amount", ""))
        return jsonify({"amount": amount, "qoins": qoin_core.to_qoins(amount),
                        "topup": qoin_core.topup_split(amount) if amount >= 1 else None})
    except ValueError as e:
        return jsonify({"error": str(e) or "Enter a whole number"}), 400


@app.route("/api/user/languages", methods=["GET", "POST"])
@login_required
def api_user_languages():
    """GET the user's languages (mother tongue, English, optional daily-use one).
    POST {"daily": "<language name>"|""} sets or clears the third language."""
    conn = get_db()
    user = _current_user_row(conn)
    if request.method == "POST":
        name = ((request.get_json(silent=True) or {}).get("daily") or "").strip()
        table = _language_table()
        if name and (name not in table or name in ("English", user["language"])):
            conn.close()
            return jsonify({"error": "Choose a language other than your mother tongue and English"}), 400
        conn.execute("UPDATE users SET daily_language = ? WHERE id = ?", (name or None, user["id"]))
        conn.commit()
        user = _current_user_row(conn)
    conn.close()
    return jsonify({"languages": _user_languages(user)})


@app.route("/dashboard")
@login_required
def dashboard():
    """User dashboard: 4 tabs (Private/Personal/Public/Global). Only
    Private is built out this pass — Karma/Activities have zero real
    backing data anywhere in this repo yet, so they're shown as honest
    empty-state sections, not fabricated numbers."""
    profile = _profile_for(session["user_id"])
    if not profile:
        session.pop("user_id", None)
        return redirect(url_for("login"))
    all_langs = [l for g in ("common", "indian", "subcontinent") for l in _load_json(LANGUAGES_FILE)[g]]
    return render_template("dashboard.html", profile=profile, all_languages=all_langs)


@app.route("/api/me")
@login_required
def api_me():
    """The signed-in person's profile for the phone app — the dashboard's Private-profile data.
    The readable IDs and the 9-digit Private ID are left out (the code is revealed only via
    /api/user/private-code, after the PIN is typed again)."""
    profile = _profile_for(session["user_id"])
    if not profile:
        return jsonify({"error": "Please sign in again"}), 401
    for hidden in ("private_id", "account_id", "kundali_view", "element_bars", "planets"):
        profile.pop(hidden, None)
    profile["is_admin"] = _is_admin()
    return jsonify(profile)


@app.route("/api/user/pin", methods=["POST"])
@login_required
def api_change_pin():
    """Change the 5-digit PIN (the current PIN is required). Old app tokens stop working;
    the app receives a fresh one."""
    data = request.get_json(silent=True) or {}
    current, new = str(data.get("current_pin", "")), str(data.get("new_pin", ""))
    if not re.fullmatch(r"\d{5}", new):
        return jsonify({"error": "Your new PIN must be exactly 5 digits"}), 400
    conn = get_db()
    user = _current_user_row(conn)
    if not user["pin_hash"] or not check_password_hash(user["pin_hash"], current):
        conn.close()
        return jsonify({"error": "Your current PIN is not correct"}), 403
    new_hash = generate_password_hash(new)
    conn.execute("UPDATE users SET pin_hash = ?, pin_fails = 0, pin_locked_until = NULL WHERE id = ?", (new_hash, user["id"]))
    conn.commit()
    conn.close()
    body = {"status": "ok"}
    if data.get("client") == "app":
        body["token"] = _issue_app_token(user["id"], new_hash)
    return jsonify(body)


# ---- App tour and the one-time rating & review (review_core.py) ----

@app.route("/api/onboarding")
@login_required
def api_onboarding():
    """{tour: null|"done"|"skipped", review_done: bool} -- the app shows the tour, then the one rating ask."""
    conn = get_db()
    try:
        return jsonify(review_core.status(conn, session["user_id"]))
    finally:
        conn.close()


@app.route("/api/onboarding/tour", methods=["POST"])
@login_required
def api_onboarding_tour():
    conn = get_db()
    try:
        review_core.set_tour(conn, session["user_id"], (request.get_json(silent=True) or {}).get("status"))
        return jsonify(review_core.status(conn, session["user_id"]))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/reviews", methods=["POST"])
@login_required
def api_review_submit():
    """One rating (1-5) + review (max 100 characters) per member, ever. {decline: true} uses the chance without one."""
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        if data.get("decline"):
            review_core.decline_review(conn, session["user_id"])
        else:
            review_core.submit_review(conn, session["user_id"], data.get("rating"), data.get("text"), bool(data.get("allow_public")),
                                      "app" if data.get("client") == "app" else "web")
        return jsonify({"status": "ok"}), 201
    except PermissionError as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/reviews/public")
def api_reviews_public():
    """Average rating and the admin-approved public reviews (first name + village only) -- for the home page / marketing."""
    conn = get_db()
    try:
        return jsonify(review_core.public_reviews(conn))
    finally:
        conn.close()


@app.route("/api/admin/reviews")
@login_required
def api_admin_reviews():
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    try:
        return jsonify({"reviews": review_core.all_reviews(conn)})
    finally:
        conn.close()


@app.route("/api/admin/reviews/<int:review_id>/approve", methods=["POST"])
@login_required
def api_admin_review_approve(review_id):
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    try:
        review_core.set_approved(conn, review_id, bool((request.get_json(silent=True) or {}).get("approved", True)))
        return jsonify({"status": "ok"})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


def _profile_for(user_id):
    """Private-profile data shared by the website dashboard and the app (/api/me); None if no such user."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    zodiac = conn.execute("SELECT * FROM user_zodiac WHERE user_id = ?", (user_id,)).fetchone()
    elemental = conn.execute(
        "SELECT * FROM user_elemental_profile WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not user:
        return None

    dob = dt.date.fromisoformat(user["dob"])
    today = dt.date.today()
    age_years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    age_category = {"A1": "Balak (Child)", "A2": "Yuvak (Youth)", "A3": "Vridh (Elder)", "A4": "Mentor"}[
        id_generator.age_code(dob)
    ]

    planets = json.loads(zodiac["planetary_positions"]) if zodiac and zodiac["planetary_positions"] else {}

    element_bars = []
    if elemental:
        counts = {
            "Fire": elemental["fire_balance"], "Earth": elemental["earth_balance"],
            "Air": elemental["air_balance"], "Water": elemental["water_balance"],
        }
        max_count = max(counts.values()) or 1
        for name, count in counts.items():
            element_bars.append({
                "name": name, "count": count,
                "width_pct": max(8, round(100 * count / max_count)),
                "css_class": "el-fill--" + name.lower(),
            })

    profile = {
        "private_id": user["private_id"],
        "account_id": user["account_id"],
        "name": user["name"],
        "gender": user["gender"],
        "age_years": age_years,
        "age_category": age_category,
        "email": user["email"],
        "phone": user["phone"],
        "mother_tongue": user["language"] or "—",
        "daily_language": user["daily_language"] or "",
        "languages": _user_languages(user),
        "kundali_view": _kundali_view(json.loads(zodiac["birth_chart"])) if zodiac and zodiac["birth_chart"] else None,
        "sun_sign": zodiac["sun_sign"] if zodiac else None,
        "sun_element": zodiac["sun_element"] if zodiac else None,
        "moon_sign": zodiac["moon_sign"] if zodiac else None,
        "moon_nakshatra": zodiac["moon_nakshatra"] if zodiac else None,
        "ascendant_sign": zodiac["ascendant_sign"] if zodiac else None,
        "kundali_summary": zodiac["kundali_summary"] if zodiac else None,
        "planets": planets,
        "elemental_balance": dict(elemental) if elemental else None,
        "element_bars": element_bars,
        "birth_location": _location_display(json.loads(user["birth_location_json"])),
        "present_location": _location_display(json.loads(user["present_location_json"])),
        "present_location_struct": json.loads(user["present_location_json"]),
    }
    return profile


# ---- Relationship status + work profile (Private account, 2026-09-28) ----
# Self-service (no council approval): unlike PROFILE_CHANGE_FIELDS below, these never touch
# kundali/zodiac/location, so there's nothing for a council to verify.
RELATIONSHIP_STATUSES = ("single", "married", "divorced_widowed")
WORK_PROFILES = ("unemployed_student", "employed", "govt", "security", "medical", "other")


@app.route("/api/profile/personal-details", methods=["GET", "POST"])
@login_required
def api_profile_personal_details():
    conn = get_db()
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            sets, vals = [], []
            if "relationship_status" in data:
                status = data.get("relationship_status") or None
                if status is not None and status not in RELATIONSHIP_STATUSES:
                    return jsonify({"error": "Unknown relationship status"}), 400
                sets.append("relationship_status = ?"); vals.append(status)
                has_children = bool(data.get("has_children")) if status == "married" else None
                sets.append("has_children = ?"); vals.append(1 if has_children else (0 if has_children is not None else None))
                sons = max(0, int(data.get("sons_count") or 0)) if has_children else 0
                daughters = max(0, int(data.get("daughters_count") or 0)) if has_children else 0
                sets.append("sons_count = ?"); vals.append(sons)
                sets.append("daughters_count = ?"); vals.append(daughters)
            if "work_profile" in data:
                wp = data.get("work_profile") or None
                if wp is not None and wp not in WORK_PROFILES:
                    return jsonify({"error": "Unknown work profile"}), 400
                sets.append("work_profile = ?"); vals.append(wp)
                sets.append("work_profile_other = ?"); vals.append((data.get("work_profile_other") or "").strip()[:120] if wp == "other" else None)
            if sets:
                vals.append(session["user_id"])
                conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)
                conn.commit()
            return jsonify({"status": "ok"})
        row = conn.execute(
            "SELECT relationship_status, has_children, sons_count, daughters_count, work_profile, work_profile_other FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()
        return jsonify({
            "relationship_status": row["relationship_status"],
            "has_children": bool(row["has_children"]) if row["has_children"] is not None else None,
            "sons_count": row["sons_count"] or 0,
            "daughters_count": row["daughters_count"] or 0,
            "work_profile": row["work_profile"],
            "work_profile_other": row["work_profile_other"],
        })
    finally:
        conn.close()


PROFILE_CHANGE_FIELDS = ("name", "email", "phone", "dob", "tob", "birth_location", "present_location")
FOUNDATIONAL_FIELDS = ("dob", "tob", "birth_location", "present_location")  # only a council can approve these


def _ensure_profile_change_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS profile_change_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, fields_json TEXT NOT NULL,
        reason TEXT, status TEXT NOT NULL DEFAULT 'pending', decided_by INTEGER, decided_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()


@app.route("/api/dashboard/edit-request", methods=["POST"])
@login_required
def api_dashboard_edit_request():
    """Queues a profile-change request for a council to review. Name/email/phone were already
    self-service in the older Edit Profile modal; dob/tob/birth & present location are "foundational"
    per the founder's rule and need a council decision (api_admin_decide_change) before they apply.
    Also still written into the user's real folder as a durable record, as before."""
    data = request.get_json(force=True) or {}
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    zodiac = conn.execute(
        "SELECT sun_element FROM user_zodiac WHERE user_id = ?", (session["user_id"],)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    fields = {k: data.get(k) for k in PROFILE_CHANGE_FIELDS if data.get(k) not in (None, "")}
    if not fields:
        conn.close()
        return jsonify({"error": "Nothing to change"}), 400

    _ensure_profile_change_table(conn)
    conn.execute("INSERT INTO profile_change_requests (user_id, fields_json, reason) VALUES (?, ?, ?)",
                 (session["user_id"], json.dumps(fields), data.get("reason", "")))
    conn.commit()

    birth_location = json.loads(user["birth_location_json"])
    location_dir = folder_connector.resolve_location_dir(birth_location)
    if location_dir is not None:
        user_dir = folder_connector.create_user_folder(location_dir, "BORN_HERE", zodiac["sun_element"], user["private_id"])
        folder_connector.save_change_request(user_dir, {
            "requested_by": user["private_id"], "fields": fields, "reason": data.get("reason", ""),
            "requested_at": dt.datetime.utcnow().isoformat() + "Z",
        })
    conn.close()
    return jsonify({"status": "queued"})


@app.route("/api/admin/profile-changes")
@login_required
def api_admin_profile_changes():
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    _ensure_profile_change_table(conn)
    rows = [dict(r) for r in conn.execute(
        """SELECT r.id, r.fields_json, r.reason, r.created_at, u.name FROM profile_change_requests r
           JOIN users u ON u.id = r.user_id WHERE r.status = 'pending' ORDER BY r.id""")]
    conn.close()
    for r in rows:
        r["fields"] = json.loads(r.pop("fields_json"))
    return jsonify({"requests": rows})


def _recompute_profile(conn, user_id):
    """Re-runs the same zodiac/Kundali/elemental-balance computation registration does, for a user
    whose dob/tob/birth_location a council has just approved a change to. Also moves the birth
    location_elements counts and the physical BORN_HERE folder if the birth location itself moved.
    Present-location folder/account-id are untouched here -- that's what Account ID switching is for."""
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    dob = dt.date.fromisoformat(user["dob"])
    tob = dt.time.fromisoformat(user["tob"])
    birth_location = json.loads(user["birth_location_json"])

    tropical = zodiac_core.get_zodiac_sign(dob)
    lat, lng, precision = _location_lat_lng(birth_location)
    kundali = zodiac_core.generate_kundali(dob, tob, lat, lng)
    kundali["ephemeris"]["location_precision"] = precision
    zodiac_row = {
        "sun_sign": tropical["sign"], "sun_element": tropical["element"],
        "moon_sign": kundali["moon"]["sign"], "moon_nakshatra": kundali["moon"]["nakshatra"],
        "ascendant_sign": kundali["ascendant"]["sign"],
    }
    kundali_summary = zodiac_core.generate_kundali_summary(zodiac_row)

    conn.execute(
        """UPDATE user_zodiac SET sun_sign=?, sun_element=?, moon_sign=?, moon_nakshatra=?, moon_nakshatra_pada=?,
           ascendant_sign=?, birth_chart=?, kundali_summary=?, planetary_positions=? WHERE user_id=?""",
        (tropical["sign"], tropical["element"], kundali["moon"]["sign"], kundali["moon"]["nakshatra"], kundali["moon"]["pada"],
         kundali["ascendant"]["sign"], json.dumps(kundali), kundali_summary, json.dumps(kundali["planets"]), user_id),
    )
    balance = elemental_core.compute_elemental_balance(tropical["element"], kundali)
    conn.execute(
        """UPDATE user_elemental_profile SET fire_balance=?, earth_balance=?, air_balance=?, water_balance=?,
           space_balance=?, dominant_element=? WHERE user_id=?""",
        (balance["fire_balance"], balance["earth_balance"], balance["air_balance"], balance["water_balance"],
         balance["space_balance"], balance["dominant_element"], user_id),
    )

    conn.commit()
    return {"zodiac": zodiac_row, "kundali_summary": kundali_summary, "elemental_balance": balance}


@app.route("/api/admin/profile-changes/<int:request_id>/decide", methods=["POST"])
@login_required
def api_admin_profile_decide(request_id):
    """Approving applies simple fields (name/email/phone/dob/tob) and location fields directly, then
    -- if dob/tob/birth_location changed -- automatically recomputes the zodiac, Kundali and elemental
    balance (age category is derived live from dob, so it updates itself)."""
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    approve = bool((request.get_json(silent=True) or {}).get("approve"))
    conn = get_db()
    _ensure_profile_change_table(conn)
    row = conn.execute("SELECT * FROM profile_change_requests WHERE id = ? AND status = 'pending'", (request_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Request not found"}), 404
    conn.execute("UPDATE profile_change_requests SET status = ?, decided_by = ?, decided_at = CURRENT_TIMESTAMP WHERE id = ?",
                 ("approved" if approve else "rejected", session["user_id"], request_id))
    if approve:
        fields = json.loads(row["fields_json"])
        old_user = conn.execute("SELECT birth_location_json FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        old_birth_location = json.loads(old_user["birth_location_json"])
        old_zodiac = conn.execute("SELECT sun_element FROM user_zodiac WHERE user_id = ?", (row["user_id"],)).fetchone()

        sets, args = [], []
        for k, v in fields.items():
            col = {"birth_location": "birth_location_json", "present_location": "present_location_json"}.get(k, k)
            sets.append(f"{col} = ?")
            args.append(json.dumps(v) if k in ("birth_location", "present_location") else v)
        args.append(row["user_id"])
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", args)

        if any(k in fields for k in FOUNDATIONAL_FIELDS if k != "present_location"):
            result = _recompute_profile(conn, row["user_id"])
            new_element = result["zodiac"]["sun_element"]
            new_birth_location = json.loads(conn.execute("SELECT birth_location_json FROM users WHERE id = ?", (row["user_id"],)).fetchone()["birth_location_json"])
            if old_zodiac:
                _move_location_element_counts(conn, old_birth_location, old_zodiac["sun_element"], new_birth_location, new_element)
            if "birth_location" in fields:
                _move_born_here_folder(conn, row["user_id"], old_birth_location, new_birth_location, new_element)
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


def _move_location_element_counts(conn, old_location, old_element, new_location, new_element):
    """Shifts one user's element tally from every level of their old birth-location chain to their new one."""
    col = {"Fire": "fire_count", "Earth": "earth_count", "Air": "air_count", "Water": "water_count"}.get(old_element)
    new_col = {"Fire": "fire_count", "Earth": "earth_count", "Air": "air_count", "Water": "water_count"}.get(new_element)
    if not col or not new_col:
        return
    old_levels = elemental_core.location_levels_for(old_location)
    new_levels = elemental_core.location_levels_for(new_location)
    for location_id, location_type in old_levels:
        conn.execute(f"UPDATE location_elements SET {col} = {col} - 1, total_users = total_users - 1 WHERE location_id = ? AND location_type = ?",
                     (location_id, location_type))
    for location_id, location_type in new_levels:
        if not conn.execute("SELECT 1 FROM location_elements WHERE location_id = ? AND location_type = ?", (location_id, location_type)).fetchone():
            conn.execute("INSERT INTO location_elements (location_id, location_type, fire_count, earth_count, air_count, water_count, space_count, total_users) VALUES (?, ?, 0, 0, 0, 0, 0, 0)",
                         (location_id, location_type))
        conn.execute(f"UPDATE location_elements SET {new_col} = {new_col} + 1, total_users = total_users + 1 WHERE location_id = ? AND location_type = ?",
                     (location_id, location_type))


def _move_born_here_folder(conn, user_id, old_location, new_location, element):
    """Moves a user's BORN_HERE folder to wherever their (now-corrected) birth location really resolves
    to on disk, copying its contents across. Skipped quietly if either folder can't be resolved."""
    user = conn.execute("SELECT private_id FROM users WHERE id = ?", (user_id,)).fetchone()
    old_dir = folder_connector.resolve_location_dir(old_location)
    new_dir = folder_connector.resolve_location_dir(new_location)
    if old_dir is None or new_dir is None:
        return
    old_user_dir = old_dir / "BORN_HERE" / element / user["private_id"]
    if not old_user_dir.exists():
        return
    new_user_dir = folder_connector.create_user_folder(new_dir, "BORN_HERE", element, user["private_id"])
    import shutil
    for item in old_user_dir.iterdir():
        dest = new_user_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    if old_user_dir != new_user_dir:
        shutil.rmtree(old_user_dir)


# ---- Poems marquee (bottom bar on every page) ----
# One JSON file per language in Poems/, each a list of {id, marker, text} with the
# same ids in the same order. To add a translation, drop its file in Poems/ and add
# an entry here: code -> (file name, label shown on the language toggle).
POEMS_DIR = BASE_DIR / "Poems"
POEM_LANGUAGES = {
    "hi": ("poems_hindi.json", "हिन्दी"),
    "en": ("poems_english.json", "English"),
}
_poem_cache = {}


def _poems(lang):
    if lang not in POEM_LANGUAGES:
        return None
    if lang not in _poem_cache:
        path = POEMS_DIR / POEM_LANGUAGES[lang][0]
        _poem_cache[lang] = sorted(_load_json(path), key=lambda p: p["id"]) if path.exists() else None
    return _poem_cache[lang]


def _poem_languages():
    return [{"code": c, "label": label, "available": True} for c, (_, label) in POEM_LANGUAGES.items() if _poems(c)]


@app.route("/api/poems/meta")
def api_poems_meta():
    langs = _poem_languages()
    if not langs:
        return jsonify({"error": "No poems available"}), 404
    count = min(len(_poems(l["code"])) for l in langs)
    result = {"count": count, "languages": langs, "personal": False}
    if session.get("user_id"):
        conn = get_db()
        user = _current_user_row(conn)
        conn.close()
        if user:
            have = {l["code"] for l in langs}
            # the user's own languages; ones without a poem translation yet are listed as "coming soon"
            result["languages"] = [
                {"code": u["code"], "label": u["native"], "available": u["code"] in have} for u in _user_languages(user)
            ]
            result["personal"] = True
            result["default"] = next((u["code"] for u in _user_languages(user) if u["code"] in have), langs[0]["code"])
    return jsonify(result)


@app.route("/api/poems/<lang>/<int:index>")
def api_poem(lang, index):
    """One poem by 0-based position (the same position is the same poem in every language)."""
    poems = _poems(lang)
    if not poems or not 0 <= index < len(poems):
        return jsonify({"error": "Poem not found"}), 404
    poem = poems[index]
    resp = jsonify({"index": index, "id": poem["id"], "marker": poem["marker"], "text": poem["text"]})
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@app.route("/api/global-data")
def api_global_data():
    """Global Timeline sidebar stats + India's zone list."""
    return jsonify(_load_json(DATA_FILE))


@app.route("/api/world-data")
def api_world_data():
    """All 7 continents and their 229 countries, parsed from the real
    'O राम - World Data.xlsx' sheet — used for the continent/country
    markers on the globe and the country-picker panel."""
    return jsonify(_load_json(WORLD_DATA_FILE))


@app.route("/api/india-states")
def api_india_states():
    """India's 5 zones and 37 states (real names, parsed from SITAXML),
    used by the registration wizard once a user picks India as their
    birth or present country."""
    return jsonify(_load_json(INDIA_STATES_FILE))


@app.route("/api/india-districts")
def api_india_districts():
    """Real District/Tehsil names per state, parsed from SITAXML.xml —
    see scripts/extract_india_districts_tehsils.py for the important
    caveat: these are the source's real administrative districts/tehsils,
    not verified Lok Sabha/Vidhan Sabha constituency data (the source has
    no constituency-specific fields at all)."""
    return jsonify(_load_json(INDIA_DISTRICTS_FILE))


SUBCONTINENT_STATES_FILE = BASE_DIR / "static" / "data" / "subcontinent_states.json"
SUBCONTINENT_DISTRICTS_FILE = BASE_DIR / "static" / "data" / "subcontinent_districts.json"
# The 10 countries of the Indian Sub-continent (Balochistan is its own country
# in the location master, not a Pakistan province). Every user's PRESENT
# location must be one of these; birth location can be anywhere on Earth.
SUBCONTINENT_COUNTRY_IDS = (
    "O_AS_IND", "O_AS_NPL", "O_AS_BTN", "O_AS_BGD", "O_AS_MMR",
    "O_AS_LKA", "O_AS_PAK", "O_AS_BLC", "O_AS_AFG", "O_AS_MDV",
)


def _public_state_ids(country_id):
    """Valid state-level ids of one Public-timeline country."""
    data = _load_json(SUBCONTINENT_STATES_FILE)
    for country in data["countries"]:
        if country["id"] == country_id:
            return {st["id"] for zone in country["zones"] for st in zone["states"]}
    return set()


@app.route("/api/subcontinent")
def api_subcontinent():
    """The 9 Sub-continent countries with their zones and states -- India's
    from the SITAXML-derived india_states.json, the other 8 from the
    compiled location master (scripts/build_subcontinent_data.py)."""
    return jsonify(_load_json(SUBCONTINENT_STATES_FILE))


@app.route("/api/subcontinent/districts")
def api_subcontinent_districts():
    """District/tehsil names per state id for all 9 countries. A district
    with `direct_villages` has villages hanging straight off it (no tehsil
    tier) -- fetch them with /api/india-villages/<district_id>."""
    return jsonify(_load_json(SUBCONTINENT_DISTRICTS_FILE))


@app.route("/api/subcontinent/stats")
def api_subcontinent_stats():
    """Registered-user demographics for everyone whose birth (default) or
    present location is in one of the 9 Sub-continent countries."""
    column = "present_location_json" if request.args.get("basis") == "present" else "birth_location_json"
    marks = ",".join("?" for _ in SUBCONTINENT_COUNTRY_IDS)
    conn = get_db()
    rows = conn.execute(
        f"""SELECT u.gender, u.dob, z.sun_sign, z.sun_element
           FROM users u JOIN user_zodiac z ON z.user_id = u.id
           WHERE json_extract(u.{column}, '$.country.id') IN ({marks})""",
        SUBCONTINENT_COUNTRY_IDS,
    ).fetchall()
    conn.close()
    return jsonify(elemental_core.registered_user_stats_from_rows(rows))


@app.route("/api/india/state-districts/<path:state_id>")
def api_india_state_districts(state_id):
    """Real 2011-census district shapes for one state, for the registration
    wizard's decorative 'selected state' overlay map only -- see
    INDIA_DISTRICT_SHAPES_FILE's comment above for why this is never used to
    resolve an actual district selection (different taxonomy than SITAXML)."""
    states_data = _load_json(INDIA_STATES_FILE)
    state_name = None
    for zone in states_data["zones"]:
        for s in zone["states"]:
            if s["id"] == state_id:
                state_name = s["name"]
                break
    if not state_name:
        return jsonify({"error": "Unknown state id"}), 404

    shapes = _load_json(INDIA_DISTRICT_SHAPES_FILE)
    matched = [
        f for f in shapes["features"]
        if f["properties"].get("st_nm", "").strip().lower() == state_name.strip().lower()
    ]
    return jsonify({"type": "FeatureCollection", "features": matched})


@app.route("/api/india-villages/<path:tehsil_id>")
def api_india_villages(tehsil_id):
    """Real villages for one tehsil (621,057 for India, plus ~85k for the
    other 8 Sub-continent countries -- queried per-parent from the
    india_villages table rather than shipped as one static file; the id may
    also be a district id for villages that hang directly off a district).
    See scripts/import_india_villages.py; 482 village ids
    repeat in the source XML itself (a real data-quality issue, ~0.08% of
    rows) — INSERT OR REPLACE means the table has one row per id, so a
    couple of tehsils may show one fewer village than the source's raw count."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name FROM india_villages WHERE tehsil_id = ? ORDER BY name", (tehsil_id,)
    ).fetchall()
    conn.close()
    return jsonify({"tehsil_id": tehsil_id, "villages": [dict(r) for r in rows]})


@app.route("/api/country/stats/<path:country_id>")
def api_country_stats(country_id):
    """Registered-user demographics for one country (Total Humans, gender,
    age bands, zodiac element/sign breakdown) — live from users + user_zodiac,
    filtered by birth_location's country id. NOT population/capital/area/
    currency: this app has never ingested that data, and the real ask is
    about registered users, per the user's own correction of the brief."""
    conn = get_db()
    rows = conn.execute(
        """SELECT u.gender, u.dob, z.sun_sign, z.sun_element
           FROM users u JOIN user_zodiac z ON z.user_id = u.id
           WHERE json_extract(u.birth_location_json, '$.country.id') = ?""",
        (country_id,),
    ).fetchall()
    conn.close()
    return jsonify(elemental_core.registered_user_stats_from_rows(rows))


@app.route("/api/continent/stats/<path:continent_id>")
def api_continent_stats(continent_id):
    """Same registered-user demographics as /api/country/stats, scoped to
    one continent instead of one country."""
    conn = get_db()
    rows = conn.execute(
        """SELECT u.gender, u.dob, z.sun_sign, z.sun_element
           FROM users u JOIN user_zodiac z ON z.user_id = u.id
           WHERE json_extract(u.birth_location_json, '$.continent.id') = ?""",
        (continent_id,),
    ).fetchall()
    conn.close()
    return jsonify(elemental_core.registered_user_stats_from_rows(rows))


_LOCATION_STATS_LEVELS = ("continent", "country", "zone", "state", "district", "tehsil", "village")


@app.route("/api/location/stats/<level>/<path:location_id>")
def api_location_stats(level, location_id):
    """Same registered-user demographics as /api/country/stats and
    /api/continent/stats, generalized over every level the location payload
    can carry (continent/country/zone/state/district/tehsil/village) and
    over which side of a user's location this checks (?basis=birth|present,
    default present -- the dashboard's Global/Public tabs need present-
    location stats, which /api/country/stats and /api/continent/stats have
    never covered; those two routes are untouched, still birth-only, still
    used by the homepage and registration wizard)."""
    if level not in _LOCATION_STATS_LEVELS:
        return jsonify({"error": "Unknown level: " + level}), 404
    basis = request.args.get("basis", "present")
    column = "present_location_json" if basis == "present" else "birth_location_json"
    conn = get_db()
    rows = conn.execute(
        f"""SELECT u.gender, u.dob, z.sun_sign, z.sun_element
           FROM users u JOIN user_zodiac z ON z.user_id = u.id
           WHERE json_extract(u.{column}, ?) = ?""",
        ("$." + level + ".id", location_id),
    ).fetchall()
    conn.close()
    return jsonify(elemental_core.registered_user_stats_from_rows(rows))


@app.route("/api/location/members/village/<path:village_id>")
def api_location_members(village_id):
    """Village-only member directory for the dashboard's location explorer
    (Phase 1 of docs/DASHBOARD_REDESIGN_PLAN.md) -- every other level already
    has real aggregate stats (/api/location/stats above); only villages are
    small/bounded enough for a browsable name list. Privacy-scoped per the
    plan: name/gender/age category only, never private_id/account_id/email/
    phone/zodiac -- `id` here is just the internal numeric user id, used only
    to key the profile popup client-side, never displayed."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, gender, dob FROM users WHERE json_extract(present_location_json, '$.village.id') = ?",
        (village_id,),
    ).fetchall()
    conn.close()
    members = [
        {
            "id": r["id"],
            "name": r["name"],
            "gender": r["gender"],
            "age_category": _AGE_CATEGORY_NAMES[id_generator.age_code(dt.date.fromisoformat(r["dob"]))],
        }
        for r in rows
    ]
    return jsonify({"members": members})


@app.route("/api/earth/stats")
def api_earth_stats():
    """Same registered-user demographics, Earth-wide (no location filter)."""
    conn = get_db()
    rows = conn.execute(
        """SELECT u.gender, u.dob, z.sun_sign, z.sun_element
           FROM users u JOIN user_zodiac z ON z.user_id = u.id"""
    ).fetchall()
    conn.close()
    return jsonify(elemental_core.registered_user_stats_from_rows(rows))


# ---- Zodiac / kundali / elemental API (Part 5 of the zodiac architecture brief) ----

def _location_lat_lng(location: dict) -> tuple[float, float, str]:
    """Best available coordinate for a wizard location selection, plus a
    precision label — the wizard only collects continent/country (state,
    for India), not an exact birthplace, so ascendant/houses are only ever
    approximate. Sun/Moon signs are effectively unaffected by this."""
    state = location.get("state")
    if state and state.get("lat") is not None:
        return state["lat"], state["lng"], "state_centroid"
    continent = location.get("continent") or {}
    if continent.get("lat") is not None:
        return continent["lat"], continent["lng"], "continent_centroid_approx"
    return 20.0, 0.0, "unknown_fallback"


def _verify_helper(private_id, pin):
    """(helper user id, None) if this Private ID + PIN are right, else (None, error). Wrong PINs count
    toward the same 5-tries / 15-minute lock as sign-in."""
    code = re.sub(r"\D", "", str(private_id or ""))
    pin = str(pin or "").strip()
    generic = "Your Private ID or PIN is not correct, so you can't be recorded as the referrer."
    if not re.fullmatch(r"\d{9}", code) or not re.fullmatch(r"\d{5}", pin):
        return None, generic
    conn = get_db()
    try:
        user = conn.execute("SELECT id, pin_hash, pin_fails, pin_locked_until FROM users WHERE private_id_9digit = ?", (code,)).fetchone()
        now = dt.datetime.now(dt.timezone.utc)
        if user and user["pin_locked_until"] and dt.datetime.fromisoformat(user["pin_locked_until"]) > now:
            return None, "Too many wrong PINs. Try again in a few minutes."
        if not user or not user["pin_hash"] or not check_password_hash(user["pin_hash"], pin):
            if user:
                fails = (user["pin_fails"] or 0) + 1
                lock = (now + dt.timedelta(minutes=PIN_LOCK_MINUTES)).isoformat() if fails >= PIN_MAX_TRIES else None
                conn.execute("UPDATE users SET pin_fails = ?, pin_locked_until = ? WHERE id = ?", (0 if lock else fails, lock, user["id"]))
                conn.commit()
            return None, generic
        conn.execute("UPDATE users SET pin_fails = 0, pin_locked_until = NULL WHERE id = ?", (user["id"],))
        conn.commit()
        return user["id"], None
    finally:
        conn.close()


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    """Register a user in one shot: personal details + contact info +
    password (Step 1 of the wizard) together with birth/present location
    (Steps 2-3), auto-calculate zodiac + full kundali, set up the login
    session, and update that location's elemental counts. Email and phone
    are optional (format-checked only if given); password is required."""
    data = request.get_json(force=True) or {}
    required = ["name", "gender", "dob", "tob", "pin", "birth_location", "present_location"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    email = (data.get("email") or "").strip()
    if email and not _EMAIL_RE.match(email):
        return jsonify({"error": "Invalid email address"}), 400
    phone = (data.get("phone") or "").strip()
    if not re.fullmatch(r"\d{5}", str(data["pin"])):
        return jsonify({"error": "Your PIN must be exactly 5 digits"}), 400

    try:
        dob = dt.date.fromisoformat(data["dob"])
        tob = dt.time.fromisoformat(data["tob"])
    except ValueError as e:
        return jsonify({"error": f"Invalid dob/tob: {e}"}), 400

    language = (data.get("language") or "").strip()
    if language and language not in _language_names():
        return jsonify({"error": "Choose your mother tongue from the list"}), 400

    # "Register a new member": an existing member fills this in for someone else (e.g. a person
    # without a smartphone). The helper becomes the referrer and stays who they are. On the website
    # the helper is the signed-in session; on the phone app the helper has signed out, so they
    # confirm with their own Private ID + PIN (same 5-tries lock as sign-in), checked BEFORE the
    # account is created so a wrong PIN can simply be retried.
    helper_user_id = None
    if data.get("assisted"):
        if data.get("helper_private_id"):
            helper_user_id, helper_error = _verify_helper(data.get("helper_private_id"), data.get("helper_pin"))
            if helper_error:
                return jsonify({"error": helper_error}), 403
        elif session.get("user_id"):
            helper_user_id = session["user_id"]

    birth_location = data["birth_location"]
    present_location = data["present_location"]

    if not (birth_location.get("country") or {}).get("id"):
        return jsonify({"error": "Birth location needs a country"}), 400
    present_country_id = (present_location.get("country") or {}).get("id")
    if present_country_id not in SUBCONTINENT_COUNTRY_IDS:
        return jsonify({"error": "Present location must be in the Indian Sub-continent"}), 400
    present_state_id = (present_location.get("state") or {}).get("id")
    if present_state_id not in _public_state_ids(present_country_id):
        return jsonify({"error": "Present location needs a valid state/province for its country"}), 400

    tropical = zodiac_core.get_zodiac_sign(dob)
    if tropical is None:
        return jsonify({"error": "Could not determine zodiac sign from dob"}), 400

    lat, lng, precision = _location_lat_lng(birth_location)
    try:
        kundali = zodiac_core.generate_kundali(dob, tob, lat, lng)
    except Exception as e:
        return jsonify({"error": f"Kundali calculation failed: {e}"}), 500
    kundali["ephemeris"]["location_precision"] = precision

    conn = get_db()
    private_id = id_generator.generate_private_id(
        conn, data["name"], data["gender"], dob, tob, tropical["element"], birth_location
    )
    account_id = id_generator.generate_account_id(
        conn, data["name"], data["gender"], dob, tob, tropical["element"], present_location
    )
    private_code = id_generator.generate_private_code(conn)
    cur = conn.execute(
        """INSERT INTO users (name, gender, dob, tob, language, birth_location_json,
                               present_location_json, private_id, account_id,
                               email, phone, pin_hash, private_id_9digit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data["name"], data["gender"], data["dob"], data["tob"], data.get("language"),
         json.dumps(birth_location), json.dumps(present_location), private_id, account_id,
         email or None, phone or None, generate_password_hash(str(data["pin"])), private_code),
    )
    user_id = cur.lastrowid
    if helper_user_id:
        conn.execute("UPDATE users SET referred_by_user_id = ? WHERE id = ?", (helper_user_id, user_id))

    zodiac_row = {
        "sun_sign": tropical["sign"], "sun_element": tropical["element"],
        "moon_sign": kundali["moon"]["sign"], "moon_nakshatra": kundali["moon"]["nakshatra"],
        "ascendant_sign": kundali["ascendant"]["sign"],
    }
    kundali_summary = zodiac_core.generate_kundali_summary(zodiac_row)

    conn.execute(
        """INSERT INTO user_zodiac
           (user_id, sun_sign, sun_element, moon_sign, moon_nakshatra, moon_nakshatra_pada,
            ascendant_sign, birth_chart, kundali_summary, planetary_positions)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, tropical["sign"], tropical["element"], kundali["moon"]["sign"],
         kundali["moon"]["nakshatra"], kundali["moon"]["pada"], kundali["ascendant"]["sign"],
         json.dumps(kundali), kundali_summary, json.dumps(kundali["planets"])),
    )

    balance = elemental_core.compute_elemental_balance(tropical["element"], kundali)
    conn.execute(
        """INSERT INTO user_elemental_profile
           (user_id, fire_balance, earth_balance, air_balance, water_balance, space_balance, dominant_element)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, balance["fire_balance"], balance["earth_balance"], balance["air_balance"],
         balance["water_balance"], balance["space_balance"], balance["dominant_element"]),
    )
    conn.commit()

    # The 12-digit search code for this Account ID (otherwise only created by the start-up backfill).
    social_core.ensure_tables(conn)
    social_core.record_new_account_id(conn, user_id, account_id, present_location)

    elemental_core.update_location_stats(conn, birth_location, tropical["element"])
    conn.close()

    try:
        folder_connector.register_user_folder(birth_location, present_location, tropical["element"], {
            "user_id": user_id, "name": data["name"], "gender": data["gender"],
            "dob": data["dob"], "tob": data["tob"],
            "private_id": private_id, "account_id": account_id,
            "birth_location_path": id_generator.location_path_for(birth_location),
            "present_location_path": id_generator.location_path_for(present_location),
            "sun_sign": tropical["sign"], "sun_element": tropical["element"],
        })
    except OSError as e:
        print(f"[folder_connector] could not write user folder for {private_id}: {e}")

    # ---- optional registration-time donation (0-200, per qoin_core / wallet_core.apply_registration_donation) ----
    # the connection above was already closed once folder_connector had the user's data; reopen for this.
    conn = get_db()
    donation_error = None
    donation_breakdown = None
    try:
        donation_amount = int(data.get("donation_amount") or 0)
    except (TypeError, ValueError):
        donation_amount = 0
    donation_amount = max(0, min(donation_amount, qoin_core.MAX_DONATION))
    referral_code = (data.get("referral_code") or "").strip()
    referrer_user_id = None
    board_core.ensure_sub_tables(conn)
    if helper_user_id:
        # The helper registering them in person is the referrer, and has already proved who they are.
        referrer_user_id = helper_user_id
        referral_code = ""
    elif referral_code:
        referrer_user_id = board_core.referrer_for_code(conn, referral_code)
        if referrer_user_id is None:
            donation_error = "That referral code was not recognised — registered without it."
        elif donation_amount > 0:
            referrer_pin = str(data.get("referrer_pin") or "")
            referrer_row = conn.execute("SELECT pin_hash FROM users WHERE id = ?", (referrer_user_id,)).fetchone()
            if not referrer_row or not referrer_row["pin_hash"] or not check_password_hash(referrer_row["pin_hash"], referrer_pin):
                donation_error = "The volunteer's PIN did not match, so the cash donation could not be confirmed — registered without it."
                referrer_user_id = None
                donation_amount = 0
    try:
        donation_breakdown = wallet_core.apply_registration_donation(conn, user_id, present_location, donation_amount, referrer_user_id)
        if referrer_user_id is not None:
            board_core.record_referral_use(conn, referral_code)
    except ValueError as e:
        donation_error = str(e)
        donation_breakdown = None
    conn.close()

    if helper_user_id:
        # The helper stays signed in as themself; the new member signs in later with their own ID + PIN.
        return jsonify({
            "user_id": user_id, "private_code": private_code, "token": None, "assisted": True,
            "donation": donation_breakdown, "donation_error": donation_error,
            "account_id": account_id, "zodiac": zodiac_row, "redirect": url_for("register"),
        }), 201

    session["user_id"] = user_id
    app_token = None
    if data.get("client") == "app":
        tconn = get_db()
        pin_hash = tconn.execute("SELECT pin_hash FROM users WHERE id = ?", (user_id,)).fetchone()["pin_hash"]
        tconn.close()
        app_token = _issue_app_token(user_id, pin_hash)
    return jsonify({
        "user_id": user_id,
        "private_code": private_code,
        "token": app_token,
        "donation": donation_breakdown, "donation_error": donation_error,
        "account_id": account_id,
        "zodiac": zodiac_row,
        "kundali": kundali,
        "kundali_summary": kundali_summary,
        "elemental_balance": balance,
        "redirect": url_for("dashboard"),
    }), 201


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_password(password: str) -> str | None:
    """Returns an error message, or None if valid. Same rule set as the
    brief's own validatePassword() sample: 8+ chars, 1 capital, 1 special,
    1 digit -- checked here too, server-side, since client validation alone
    is never trustworthy."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least 1 capital letter"
    if not re.search(r"[!@#$%^&*()_+=\-]", password):
        return "Password must contain at least 1 special character"
    if not re.search(r"[0-9]", password):
        return "Password must contain at least 1 number"
    return None


@app.route("/api/user/zodiac/<int:user_id>")
def api_user_zodiac(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM user_zodiac WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    result = dict(row)
    result["birth_chart"] = json.loads(result["birth_chart"]) if result["birth_chart"] else None
    result["planetary_positions"] = json.loads(result["planetary_positions"]) if result["planetary_positions"] else None
    return jsonify(result)


@app.route("/api/user/kundali/summary/<int:user_id>")
def api_user_kundali_summary(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT sun_sign, sun_element, moon_sign, moon_nakshatra, ascendant_sign, kundali_summary "
        "FROM user_zodiac WHERE user_id = ?", (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/location/elements/<path:location_id>")
def api_location_elements(location_id):
    location_type = request.args.get("type", "country")
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM location_elements WHERE location_id = ? AND location_type = ?",
        (location_id, location_type),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "No data yet for this location", "location_id": location_id, "location_type": location_type}), 404
    return jsonify(elemental_core.location_elements_row_to_dict(row))


@app.route("/api/global/elements")
def api_global_elements():
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM location_elements WHERE location_id = 'EARTH' AND location_type = 'earth'"
    ).fetchone()
    all_locations = conn.execute(
        "SELECT * FROM location_elements ORDER BY location_type, total_users DESC"
    ).fetchall()
    conn.close()
    return jsonify({
        "earth": elemental_core.location_elements_row_to_dict(row) if row else None,
        "all_locations": [elemental_core.location_elements_row_to_dict(r) for r in all_locations],
    })


@app.route("/api/zodiac/signs")
def api_zodiac_signs():
    conn = get_db()
    rows = conn.execute("SELECT * FROM zodiac_signs ORDER BY id").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["nakshatras"] = json.loads(d["nakshatras"]) if d["nakshatras"] else []
        result.append(d)
    return jsonify(result)


@app.route("/api/zodiac/current")
def api_zodiac_current():
    today = dt.date.today()
    tropical = zodiac_core.get_zodiac_sign(today)
    return jsonify({"date": today.isoformat(), "sign": tropical["sign"], "element": tropical["element"]})


_AGE_CATEGORY_NAMES = {"A1": "Balak", "A2": "Yuvak", "A3": "Vridh", "A4": "Mentor"}


@app.route("/api/zodiac/preview")
def api_zodiac_preview():
    """Sun sign/element + age category for a birth date, before the account
    actually exists yet -- the registration wizard's Review step needs both
    for display, but only has the DOB at that point (no lat/lng/tob, so the
    full kundali computation isn't run here, just the same tropical sign
    calculation /api/auth/register itself uses)."""
    dob_param = request.args.get("dob", "")
    try:
        dob = dt.date.fromisoformat(dob_param)
    except ValueError:
        return jsonify({"error": "dob must be an ISO date (YYYY-MM-DD)"}), 400

    tropical = zodiac_core.get_zodiac_sign(dob)
    age_code = id_generator.age_code(dob)
    return jsonify({
        "sign": tropical["sign"],
        "element": tropical["element"],
        "age_code": age_code,
        "age_name": _AGE_CATEGORY_NAMES[age_code],
        "age_range": elemental_core.AGE_BAND_LABELS[age_code],
    })


@app.route("/api/lunar/phase")
def api_lunar_phase():
    return jsonify({
        "current": lunar_core.get_current_lunar_phase(),
        "upcoming": lunar_core.get_upcoming_lunar_events(),
    })


def _current_user_row(conn):
    return conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


def _is_admin() -> bool:
    """No real role/admin system exists yet (prototype phase) — gated the
    same way QM_SECRET_KEY/QM_EARTH_ROOT are, via an env var of allowed
    Private IDs, until a real admin flag is built."""
    allowed = {pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()}
    if not allowed:
        return False
    conn = get_db()
    user = _current_user_row(conn)
    conn.close()
    return bool(user and user["private_id_9digit"] in allowed)


# ---- Karma Qoins wallet API ----

@app.route("/api/wallet/balance")
@login_required
def api_wallet_balance():
    conn = get_db()
    balance = wallet_core.wallet_balance(conn, "user", str(session["user_id"]))
    transactions = wallet_core.wallet_transactions(conn, "user", str(session["user_id"]))
    has_locked = wallet_core.has_locked_share(conn, session["user_id"])
    conn.close()
    return jsonify({"balance_qoins": balance, "has_locked_share": has_locked, "transactions": transactions})


@app.route("/api/wallet/balance/<location_type>/<path:location_id>")
def api_wallet_location_balance(location_type, location_id):
    if location_type not in wallet_core.LOCATION_TIERS:
        return jsonify({"error": "Unknown location_type: " + location_type}), 404
    conn = get_db()
    balance = wallet_core.wallet_balance(conn, location_type, location_id)
    conn.close()
    return jsonify({"location_type": location_type, "location_id": location_id, "balance_qoins": balance})


@app.route("/api/wallet/donate", methods=["POST"])
@login_required
def api_wallet_donate():
    """Simulated donation — no real payment processor. User picks a rupee
    amount (and optionally a referrer's Private ID); the system computes and
    credits the Qoin split immediately (see wallet_core.calculate_donation_
    distribution). The donor's own share is credited locked, unlocked on
    their first election vote."""
    data = request.get_json(force=True) or {}
    try:
        amount_rupees = int(data.get("amount_rupees"))
    except (TypeError, ValueError):
        return jsonify({"error": "amount_rupees must be an integer"}), 400

    conn = get_db()
    user = _current_user_row(conn)
    referrer_user_id = None
    referrer_private_id = (data.get("referrer_private_id") or "").strip()
    if referrer_private_id:
        referrer = conn.execute(
            "SELECT id FROM users WHERE private_id_9digit = ?", (referrer_private_id,)
        ).fetchone()
        if not referrer:
            conn.close()
            return jsonify({"error": "Unknown referrer Private ID"}), 400
        if referrer["id"] == user["id"]:
            conn.close()
            return jsonify({"error": "You can't refer yourself"}), 400
        referrer_user_id = referrer["id"]

    try:
        split = wallet_core.apply_donation(
            conn, user["id"], json.loads(user["present_location_json"]), amount_rupees, referrer_user_id
        )
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    conn.close()
    return jsonify({"status": "credited", "amount_rupees": amount_rupees, "distribution": split})


# ---- Village elections API (piloted on election_core.PILOT_VILLAGE_ID) ----

@app.route("/api/election/status")
@login_required
def api_election_status():
    conn = get_db()
    user = _current_user_row(conn)
    cycle = election_core.current_cycle_for_village(conn, election_core.PILOT_VILLAGE_ID)

    nomination_ok, nomination_reason = election_core.nomination_eligible(conn, user, cycle)
    voting_ok, voting_reason = election_core.voting_eligible(conn, user, cycle)
    already_nominated = bool(conn.execute(
        "SELECT 1 FROM election_candidates WHERE election_cycle_id = ? AND user_id = ?",
        (cycle["id"], user["id"]),
    ).fetchone())
    voted_genders = [r["gender"] for r in conn.execute(
        "SELECT gender FROM election_votes WHERE election_cycle_id = ? AND voter_user_id = ?",
        (cycle["id"], user["id"]),
    ).fetchall()]
    guide = election_core.member_guide(conn, user, cycle)
    weeks = election_core.election_weeks(cycle)
    conn.close()

    return jsonify({
        "cycle": {
            "zodiac_sign": cycle["zodiac_sign"], "element": cycle["element"], "year": cycle["year"],
            "status": cycle["status"],
            "nomination_start": cycle["nomination_start"], "nomination_end": cycle["nomination_end"],
            "voting_start": cycle["voting_start"], "voting_end": cycle["voting_end"],
        },
        "eligibility": {
            "can_nominate": nomination_ok and cycle["status"] == "nomination" and not already_nominated,
            "nominate_reason": "" if nomination_ok else nomination_reason,
            "already_nominated": already_nominated,
            "can_vote": voting_ok and cycle["status"] == "voting",
            "vote_reason": "" if voting_ok else voting_reason,
            "voted_genders": voted_genders,
        },
        "guide": guide, "weeks": weeks, "week": guide["week"],
    })


@app.route("/api/election/candidates")
def api_election_candidates():
    conn = get_db()
    cycle = election_core.current_cycle_for_village(conn, election_core.PILOT_VILLAGE_ID)
    candidates = election_core.candidates_for_cycle(conn, cycle["id"])
    conn.close()
    return jsonify(candidates)


@app.route("/api/election/nominate", methods=["POST"])
@login_required
def api_election_nominate():
    data = request.get_json(force=True) or {}
    conn = get_db()
    user = _current_user_row(conn)
    try:
        election_core.nominate(
            conn, user,
            reason=data.get("reason") or "",
            why_vote=data.get("why_vote") or "",
            changes=data.get("changes") or "",
            past_work=data.get("past_work") or "",
        )
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    conn.close()
    return jsonify({"status": "submitted"})


@app.route("/api/election/vote", methods=["POST"])
@login_required
def api_election_vote():
    data = request.get_json(force=True) or {}
    gender = (data.get("gender") or "").strip().lower()
    try:
        candidate_user_id = int(data.get("candidate_user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "candidate_user_id is required"}), 400
    conn = get_db()
    user = _current_user_row(conn)
    try:
        election_core.cast_vote(conn, user, candidate_user_id, gender)
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    conn.close()
    return jsonify({"status": "voted"})


@app.route("/api/election/summary")
@login_required
def api_election_summary():
    conn = get_db()
    try:
        return jsonify(election_core.election_summary(conn, election_core.PILOT_VILLAGE_ID))
    finally:
        conn.close()


@app.route("/api/admin/election/auto-nominate", methods=["POST"])
@login_required
def api_admin_election_auto_nominate():
    """Week 1 automation: randomly choose 3 eligible men and 3 eligible women of this month's sign."""
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    try:
        return jsonify({"picked": election_core.auto_nominate(conn, election_core.PILOT_VILLAGE_ID)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/admin/election/auto-vote", methods=["POST"])
@login_required
def api_admin_election_auto_vote():
    """Weeks 2-3 automation: eligible members of this month's sign who haven't voted vote at random."""
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    try:
        turnout = float((request.get_json(silent=True) or {}).get("turnout", 1.0))
        return jsonify({"cast": election_core.auto_vote(conn, election_core.PILOT_VILLAGE_ID, turnout=turnout)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/election/council")
def api_election_council():
    conn = get_db()
    roster = election_core.council_roster(conn, election_core.PILOT_VILLAGE_ID)
    conn.close()
    return jsonify({"village_id": election_core.PILOT_VILLAGE_ID, "council": roster})


@app.route("/api/admin/election/nominate/<int:candidate_id>/approve", methods=["POST"])
@login_required
def api_admin_election_approve(candidate_id):
    if not _is_admin():
        return jsonify({"error": "Admin access required"}), 403
    conn = get_db()
    conn.execute("UPDATE election_candidates SET status = 'approved' WHERE id = ?", (candidate_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "approved"})


@app.route("/api/admin/election/nominate/<int:candidate_id>/reject", methods=["POST"])
@login_required
def api_admin_election_reject(candidate_id):
    if not _is_admin():
        return jsonify({"error": "Admin access required"}), 403
    conn = get_db()
    conn.execute("UPDATE election_candidates SET status = 'rejected' WHERE id = ?", (candidate_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "rejected"})


# ---- Perception Calculator (annual Pro/Anti sentiment -- see docs/perception_calculator.md) ----
# Country Perception: any of the 10 Sub-continent countries, shown on that country's Global-tab
# page. Zone Perception: India's own zones only, shown on India's Public-tab page.

@app.route("/api/perception/country/<country_id>")
def api_perception_country(country_id):
    conn = get_db()
    user_id = session.get("user_id")
    result = perception_core.country_results(conn, country_id, user_id)
    conn.close()
    return jsonify(result)


@app.route("/api/perception/country/<country_id>/vote", methods=["POST"])
@login_required
def api_perception_country_vote(country_id):
    data = request.get_json(force=True) or {}
    conn = get_db()
    try:
        result = perception_core.cast_country_vote(conn, session["user_id"], country_id, (data.get("vote") or "").strip().lower())
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    conn.close()
    return jsonify(result)


@app.route("/api/perception/zone/<path:zone_id>")
def api_perception_zone(zone_id):
    conn = get_db()
    user_id = session.get("user_id")
    result = perception_core.zone_results(conn, zone_id, user_id)
    conn.close()
    return jsonify(result)


@app.route("/api/perception/zone/<path:zone_id>/vote", methods=["POST"])
@login_required
def api_perception_zone_vote(zone_id):
    data = request.get_json(force=True) or {}
    conn = get_db()
    try:
        result = perception_core.cast_zone_vote(conn, session["user_id"], zone_id, (data.get("vote") or "").strip().lower())
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    conn.close()
    return jsonify(result)


@app.route("/api/admin/election-cycle")
@login_required
def api_admin_election_cycle():
    """Every country's Lok Sabha election years (council-editable) -- see election_core.loksabha_years."""
    if not _is_admin():
        return jsonify({"error": "Admin access required"}), 403
    conn = get_db()
    configs = election_core.all_cycle_configs(conn)
    for c in configs:
        c["years"] = election_core.loksabha_years(conn, c["country_code"])
    conn.close()
    return jsonify({"countries": configs})


@app.route("/api/admin/election-cycle/<country_code>", methods=["POST"])
@login_required
@_board_error
def api_admin_election_cycle_set(country_code):
    """Council correction: {"last_election_year": 2024, "interval_years": 5} -- elections are not
    always exactly 5 years apart everywhere, so this is a manual override, not a formula."""
    if not _is_admin():
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        election_core.set_cycle_config(
            conn, country_code, "loksabha",
            data.get("last_election_year"), data.get("interval_years"), session["user_id"],
        )
        years = election_core.loksabha_years(conn, country_code)
    finally:
        conn.close()
    return jsonify({"status": "ok", "years": years})


@app.route("/api/admin/sync-folders", methods=["POST"])
def api_admin_sync_folders():
    conn = get_db()
    result = folder_sync.sync_database_to_folders(conn)
    conn.close()
    return jsonify(result)


def _run_scheduled_sync():
    conn = get_db()
    result = folder_sync.sync_database_to_folders(conn)
    conn.close()
    print("[folder_sync] daily sync:", result)


def _start_scheduler():
    """Daily DB -> folder export at midnight (Part 9). Guarded so Flask's
    debug-mode reloader (which re-execs the process) doesn't register the
    job twice."""
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(_run_scheduled_sync, "cron", hour=0, minute=0)
        scheduler.start()


def _validate_india_location_data():
    """Startup check: the website's India district/tehsil data must match Qumanity_Master.json
    (the source of truth, per the 2026-09-28 fix -- see docs/india_location_fix.md). Only warns;
    never blocks startup, since a stale copy is a data problem to fix, not a reason to go down."""
    try:
        master_path = Path(os.environ.get("QM_EARTH_ROOT", "/Users/macmudgal/Desktop/0_Earth")) / "Qumanity_Master.json"
        if not master_path.exists():
            return
        master = json.loads(master_path.read_text(encoding="utf-8"))
        india_m = next((c for cont in master["Continents"] for c in cont.get("Countries", []) if c.get("id") == "O_AS_IND"), None)
        if not india_m:
            return
        m_districts = {d["id"]: d["name"] for z in india_m["Zones"] for s in z["States"] for d in s.get("Districts", [])}
        web = _load_json(INDIA_DISTRICTS_FILE)
        mismatches = 0
        for state in web["states"].values():
            for d in state["districts"]:
                if m_districts.get(d["id"]) not in (d["name"], None):
                    mismatches += 1
        if mismatches:
            print(f"[STARTUP WARNING] {mismatches} India district id/name mismatches between "
                  f"{INDIA_DISTRICTS_FILE.name} and Qumanity_Master.json -- the website's India data "
                  f"has drifted from the source of truth. Re-run the regeneration in docs/india_location_fix.md.")
    except Exception as e:
        print(f"[STARTUP WARNING] Could not validate India location data against Qumanity_Master.json: {e}")


_ensure_user_columns()
_validate_india_location_data()
with get_db() as _startup_conn:
    social_core.ensure_tables(_startup_conn)
    social_core.backfill_account_ids(_startup_conn)
    social_core.migrate_group_defaults(_startup_conn)
    recovery_core.ensure_tables(_startup_conn)
    review_core.ensure_tables(_startup_conn)
    election_core.ensure_history_table(_startup_conn)
    election_core.ensure_council_columns(_startup_conn)
    perception_core.ensure_tables(_startup_conn)
    karma_core.ensure_tables(_startup_conn)

if __name__ == "__main__":
    _start_scheduler()
    port = int(os.environ.get("PORT", 5050))
    # QM_HOST=0.0.0.0 lets phones on the same Wi-Fi reach the site (Qumanity_App testing).
    # The debugger is switched off then, unless QM_DEBUG=1 asks for it.
    host = os.environ.get("QM_HOST", "127.0.0.1")
    debug = os.environ.get("QM_DEBUG", "1" if host in ("127.0.0.1", "localhost") else "0") == "1"
    app.run(debug=debug, host=host, port=port)
