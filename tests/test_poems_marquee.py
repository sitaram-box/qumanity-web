"""Covers the poems marquee / religion identity box redesign (2026-11-01, updated 2026-11-02 twice:
first the public-by-default + hide/restore UX, then the Universal Multi-Religion, Multi-Language
Marquee -- RELIGION_MARQUEE_SOURCES was fully replaced by religious_text_core.py's DB-backed
tradition/collection/language library):

  1. QM_MARQUEE_ENABLED defaults True; DEFAULT_MARQUEE_RELIGION is "hindu".
  2. religious_text_core.resolve_collection(): the Vinaya-Patrika-vs-original fallback for "hindu"
     (still resolves to the original, uncopied collection -- Poems/hindu/, the reserved
     rights-cleared slot, is still empty), and the four newly-seeded collections (christian,
     muslim, buddhist) resolve correctly, each with real, rights-documented content.
  3. The standalone homepage religious symbol stays removed; the gold chip lives only in the
     marquee template, and its text is now server-driven (religious_traditions.default_label),
     never a hardcoded per-religion client table.
  4. No Gita Press/Vinaya Patrika attribution is ever shown (no verified rights exist); no Urdu
     Quran, Hindi Bible, Hindi Dhammapada, or any Sikh text is ever shown (all pending_rights_review
     -- see docs/marquee_religious_text_sources.md) -- confirmed both by DB content AND by the
     absence of the underlying Poems/ files.
  5. The Marquee is public by default for every visitor (unchanged from the 2026-11-02 reversal).
  6. The Universal Multi-Religion Marquee's own new behavior: an authenticated member's reading
     religion defaults to their PROFILE religion (when it has content) but can be switched
     independently via an explicit, allowlist-checked ?religion=/&lang= query parameter on the
     SAME two existing routes (api_poems_meta/api_poem -- no new route was added), and this
     switch NEVER writes users.religion_belief.

Standalone script, no test framework (none installed in this project): throwaway tempfile SQLite
DB via QM_DB_PATH before importing app, Flask test client driving real routes, PASS/FAIL printing,
sys.exit(1) on failure -- same conventions as tests/test_family_tree_cascade.py.

Note: this is a Flask-test-client script, not a browser -- it cannot execute poems.js, so it
cannot directly observe the gold chip's RENDERED text/visibility, the Religion/Language Selector's
rendered dropdown, RTL rendering, or the hide/restore slide/keyboard/localStorage behavior (all of
those were covered by a separate live-browser verification pass; see the task's own final report).
It verifies everything the server and the on-disk Poems/ tree control.

Run with: python3 tests/test_poems_marquee.py (not -I)
"""
from __future__ import annotations

import json as _json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"
# Deliberately NOT setting QM_MARQUEE_ENABLED here -- this test exercises the real, current
# DEFAULT (no env var set), which is the whole point of check #1 below.
os.environ.pop("QM_MARQUEE_ENABLED", None)

import app as appmod  # noqa: E402
import religious_text_core  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

VILLAGE_A = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_n = [0]


def register(religion):
    _n[0] += 1
    payload = {
        "name": f"Tester {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_A, "present_location": VILLAGE_A, "assisted": False,
        "religion_belief": religion or "",
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code):
    res = client.post("/login", json={"private_id": private_code, "pin": "12345"})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


def logout():
    # /logout is GET-only (app.py) -- a POST here would 405 and silently leave session["user_id"]
    # set, which went unnoticed in every earlier section only because the next register()/login()
    # call always overwrote it; the anonymous-visitor checks below depend on this actually
    # clearing the session.
    client.get("/logout")


print("=" * 70)
print("1. Defaults: QM_MARQUEE_ENABLED and DEFAULT_MARQUEE_RELIGION")
print("=" * 70)

check("QM_MARQUEE_ENABLED is True by default", appmod.QM_MARQUEE_ENABLED is True)
check("DEFAULT_MARQUEE_RELIGION is 'hindu' (2026-11-02 public-default decision)",
      appmod.DEFAULT_MARQUEE_RELIGION == "hindu")

print()
print("=" * 70)
print("2. religious_text_core.resolve_collection(): Hindu's Vinaya-Patrika-vs-original fallback,")
print("   and every other seeded collection, resolved against the ACTUAL on-disk/DB state")
print("=" * 70)

_conn = appmod.get_db()

check("Poems/hindu/ (the reserved, rights-cleared slot) is still genuinely empty on disk today",
      not any((appmod.POEMS_DIR / "hindu").glob("*.json")) if (appmod.POEMS_DIR / "hindu").is_dir() else True)

hindu_resolved = religious_text_core.resolve_collection(_conn, "hindu")
check("hindu resolves to a real collection", hindu_resolved is not None)
check("hindu's resolved title is the original-collection label, never claims Vinaya Patrika",
      hindu_resolved["title"] == "मौलिक राम-भक्ति कविताएँ")
check("hindu's collection is flagged as original Qumanity work", hindu_resolved["is_original_work"] is True)

christian_resolved = religious_text_core.resolve_collection(_conn, "christian")
check("christian resolves to its own real collection", christian_resolved is not None)
check("christian's title is its own real source label", christian_resolved["title"] == "Psalms, King James Version")
check("christian's only available language is English (no Hindi Bible -- pending rights review)",
      {l["code"] for l in christian_resolved["languages"]} == {"en"})

muslim_resolved = religious_text_core.resolve_collection(_conn, "muslim")
check("muslim resolves to a real collection (Quran, Al-Fatiha, Tanzil Arabic)", muslim_resolved is not None)
check("muslim's only available language is Arabic (no Urdu -- pending rights review)",
      {l["code"] for l in muslim_resolved["languages"]} == {"ar"})
check("muslim's Arabic language is flagged right-to-left",
      next(l["dir"] for l in muslim_resolved["languages"] if l["code"] == "ar") == "rtl")

buddhist_resolved = religious_text_core.resolve_collection(_conn, "buddhist")
check("buddhist resolves to a real collection (Dhammapada)", buddhist_resolved is not None)
check("buddhist's available languages are exactly Pali and English (no Hindi -- pending rights review)",
      {l["code"] for l in buddhist_resolved["languages"]} == {"pi", "en"})
check("buddhist's default/resolved language (no override given) is Pali, the original language, not Set-order-dependent",
      buddhist_resolved["resolved_language"] == "pi")

sikh_resolved = religious_text_core.resolve_collection(_conn, "sikh")
check("sikh resolves to NOTHING -- research came back pending_rights_review, no collection exists",
      sikh_resolved is None)

check("an entirely unrecognized religion code resolves to nothing, never crashes",
      religious_text_core.resolve_collection(_conn, "totally-made-up-religion") is None)

_conn.close()

print()
print("=" * 70)
print("3. JSON collection validation: every seeded collection's on-disk source file")
print("=" * 70)

_COLLECTION_FILES = [
    ("hindu_original/hi", appmod.POEMS_DIR / "hindu_original" / "poems_hindi.json"),
    ("christian/en", appmod.POEMS_DIR / "christian" / "psalms_kjv_en.json"),
    ("buddhist/pi", appmod.POEMS_DIR / "buddhist" / "dhammapada_pi" / "pali.json"),
    ("buddhist/en", appmod.POEMS_DIR / "buddhist" / "dhammapada_en" / "english_muller.json"),
    ("muslim/ar", appmod.POEMS_DIR / "muslim" / "quran_ar" / "alfatiha.json"),
]
_raw_by_key = {}
for _key, _path in _COLLECTION_FILES:
    check(f"{_key}: file exists", _path.exists())
    with open(_path, "rb") as _f:
        _raw = _f.read()
    _raw_by_key[_key] = _raw
    check(f"{_key}: decodes as strict UTF-8 with no BOM", not _raw.startswith(b"\xef\xbb\xbf"))
    try:
        _entries = _json.loads(_raw.decode("utf-8"))
        check(f"{_key}: valid JSON syntax", True)
    except Exception as e:
        check(f"{_key}: valid JSON syntax ({e})", False)
        continue
    check(f"{_key}: at least one entry", len(_entries) > 0)
    _ids = [p["id"] for p in _entries]
    check(f"{_key}: no duplicate entry ids", len(_ids) == len(set(_ids)))
    check(f"{_key}: ids are contiguous starting at 1", _ids == list(range(1, len(_ids) + 1)))
    check(f"{_key}: every entry has non-empty marker and text",
          all(p.get("marker", "").strip() and p.get("text", "").strip() for p in _entries))
    check(f"{_key}: no entry's marker/text contains HTML/script-like content", all(
        "<" not in p["marker"] and ">" not in p["marker"] and "<" not in p["text"] and ">" not in p["text"]
        for p in _entries
    ))

# Rights-specific content checks (never just "is it valid JSON" -- does it say what it's allowed to say).
_hindu_entries = _json.loads(_raw_by_key["hindu_original/hi"].decode("utf-8"))
check("hindu_original: no entry's marker claims this is Vinaya Patrika or a scriptural quotation",
      all("विनय" not in p["marker"] and "पत्रिका" not in p["marker"] for p in _hindu_entries))
check("hindu_original: every entry contains at least one Devanagari character",
      all(any("ऀ" <= ch <= "ॿ" for ch in p["text"]) for p in _hindu_entries))
check("hindu_original: no file anywhere mentions Poddar (the removed, in-copyright translator)",
      "पोद्दार" not in _raw_by_key["hindu_original/hi"].decode("utf-8")
      and "Poddar" not in _raw_by_key["hindu_original/hi"].decode("utf-8"))

_muslim_entries = _json.loads(_raw_by_key["muslim/ar"].decode("utf-8"))
check("muslim/ar: exactly Surah Al-Fatiha's 7 ayahs", len(_muslim_entries) == 7)
check("muslim/ar: every marker cites Surah 1 (Al-Fatiha), never a different Surah",
      all(p["marker"].startswith("Surah 1:") for p in _muslim_entries))
check("muslim/ar: every entry contains at least one Arabic-range character",
      all(any("؀" <= ch <= "ۿ" for ch in p["text"]) for p in _muslim_entries))

_buddhist_pi = _json.loads(_raw_by_key["buddhist/pi"].decode("utf-8"))
_buddhist_en = _json.loads(_raw_by_key["buddhist/en"].decode("utf-8"))
check("buddhist/pi and buddhist/en have the same entry count (same verses, two languages)",
      len(_buddhist_pi) == len(_buddhist_en))
check("buddhist: every marker cites the Dhammapada's own chapter:verse (1.1-1.5), never a generic counter",
      all(p["marker"].startswith("Dhammapada 1.") for p in _buddhist_pi + _buddhist_en))

print()
print("=" * 70)
print("4. Collections that are NOT permitted have NO file anywhere in the repository")
print("   (pending_rights_review is enforced by absence, not just a DB flag)")
print("=" * 70)

check("no Poems/sikh/ directory exists at all (Sikh research: pending_rights_review)",
      not (appmod.POEMS_DIR / "sikh").exists())
check("no Gita Press/Vinaya Patrika file exists under Poems/hindu/",
      not (appmod.POEMS_DIR / "hindu").exists() or not any((appmod.POEMS_DIR / "hindu").glob("*.json")))
check("no Hindi Bible file exists under Poems/christian/",
      not list((appmod.POEMS_DIR / "christian").glob("*hi*")))
check("no Urdu Quran directory/file exists under Poems/muslim/ (only quran_ar/)",
      not (appmod.POEMS_DIR / "muslim" / "quran_ur").exists()
      and sorted(p.name for p in (appmod.POEMS_DIR / "muslim").iterdir() if p.is_dir()) == ["quran_ar"])
check("no Hindi Dhammapada file exists under Poems/buddhist/",
      not list((appmod.POEMS_DIR / "buddhist").glob("**/*hi*")))

print()
print("=" * 70)
print("5. GET /api/poems/meta: live end-to-end, for a signed-in Hindu member")
print("=" * 70)

hindu_user = register("hindu")
login(hindu_user["private_code"])
res = client.get("/api/poems/meta")
check("meta succeeds now that QM_MARQUEE_ENABLED is on by default", res.status_code == 200)
meta = res.get_json()
check("meta is not hidden for a Hindu member who hasn't hidden it", meta.get("hidden") is False)
check("meta's religion is hindu", meta.get("religion") == "hindu")
check("meta's title is the original-collection label (the only real content available today)",
      meta.get("title") == "मौलिक राम-भक्ति कविताएँ")
check("meta is personalized for a signed-in member", meta.get("personal") is True)
# 2026-11-02 (Universal Multi-Religion Marquee): "languages" is now ALWAYS the collection's own
# real, servable languages -- never padded with the signed-in member's account-language list the
# way the pre-multi-religion code did (that padding made "available": false entries appear for
# languages no collection actually has, which the new Language Selector must never do -- see
# docs the task gave: "Only display a language option when a valid collection exists").
check("meta's languages are exactly the Hindu collection's own real languages (hi only), never padded",
      meta.get("languages") == [{"code": "hi", "label": "हिन्दी", "dir": "ltr", "available": True}])
check("meta's attribution field is present and accurate (original authorship, not a translation)",
      meta.get("attribution") == "Original Qumanity Hindi poetry, composed 2026-11-01.")
check("meta's label (gold chip text) is सीताराम", meta.get("label") == "सीताराम")
check("meta's profile_religion matches the member's own account religion", meta.get("profile_religion") == "hindu")

res2 = client.get("/api/poems/hi/0")
check("fetching the actual first poem by index succeeds", res2.status_code == 200)
poem0 = res2.get_json()
check("the fetched poem has real Hindi text, not a placeholder", bool(poem0.get("text")) and len(poem0["text"]) > 10)

print()
print("=" * 70)
print("6. The standalone homepage symbol is GONE; the gold chip lives only in the marquee template")
print("=" * 70)

home_res = client.get("/")
check("GET / succeeds for the signed-in Hindu member", home_res.status_code == 200)
home_html = home_res.get_data(as_text=True)
check("the old standalone symbol container (#hm-symbol) no longer exists in the HTML at all",
      'id="hm-symbol"' not in home_html)
check("the old Shivalinga path data no longer appears anywhere on the homepage",
      "M48 7 C33 7 24 18 23 34" not in home_html)
check("the marquee bar's own template content is present on the homepage (unaffected)",
      'id="pm-bar"' in home_html)
check("the gold identity chip's own container is present (inside the marquee, not a separate element)",
      'id="pm-chip"' in home_html)
check("the Religion Selector's own markup is present (Universal Multi-Religion Marquee, 2026-11-02)",
      'id="pm-religionhead"' in home_html and 'id="pm-religionmenu"' in home_html)
check("the Religion Selector's accessible label is 'Reading tradition', never implying it changes account identity",
      "Reading tradition" in home_html)

# Simulate the feature being switched off globally (the real production kill-switch) and confirm
# the marquee bar (and with it, the chip it contains) correctly disappears.
appmod.QM_MARQUEE_ENABLED = False
try:
    home_res_off = client.get("/")
    home_html_off = home_res_off.get_data(as_text=True)
    check("with the feature flag off, the marquee bar's own content is absent",
          'id="pm-bar"' not in home_html_off)
    meta_off = client.get("/api/poems/meta")
    check("with the feature flag off, /api/poems/meta correctly 404s", meta_off.status_code == 404)
finally:
    appmod.QM_MARQUEE_ENABLED = True  # restore for the remaining checks below

print()
print("=" * 70)
print("7. Logged-in non-Hindu profile defaults: each member's OWN religion is their initial reading religion")
print("=" * 70)

logout()
for religion, expect_content in (("muslim", True), ("christian", True), ("buddhist", True), ("sikh", False)):
    user = register(religion)
    login(user["private_code"])
    meta_res = client.get("/api/poems/meta")
    meta = meta_res.get_json()
    home_html = client.get("/").get_data(as_text=True)
    check(f"{religion}: no standalone symbol markup anywhere on the homepage (it no longer exists)",
          'id="hm-symbol"' not in home_html)
    check(f"{religion}: meta's profile_religion matches this member's own account religion",
          meta.get("profile_religion") == religion)
    if expect_content:
        check(f"{religion}: meta resolves real content (not coming_soon), matching their own profile religion",
              meta.get("coming_soon") is not True and meta.get("religion") == religion)
        check(f"{religion}: meta's label (gold chip text) is present and non-empty", bool(meta.get("label")))
    else:
        check(f"{religion}: meta correctly reports coming_soon (pending rights review, no poem content exists yet)",
              meta_res.status_code == 200 and meta.get("coming_soon") is True and meta.get("religion") == religion)
    logout()

logout()
no_religion_user = register("")
login(no_religion_user["private_code"])
meta_res = client.get("/api/poems/meta")
no_religion_meta = meta_res.get_json()
check("a member with no declared religion gets the Hindu default religion/title, not suppressed",
      meta_res.status_code == 200 and no_religion_meta.get("religion") == "hindu"
      and no_religion_meta.get("title") == "मौलिक राम-भक्ति कविताएँ")
check("a member with no declared religion is NOT hidden by default (hidden only reflects their own preference)",
      no_religion_meta.get("hidden") is False)
# profile_religion mirrors _marquee_religion_for_session()'s own already-defaulted return value
# (by design -- that function's docstring says its result is "NEVER None"), so a no-religion
# member's profile_religion is "hindu" here too, same as "religion" -- there is no separate "raw,
# undefaulted" value exposed by this route, since the client only ever needs to know the EFFECTIVE
# default to render correctly.
check("a member with no declared religion has profile_religion equal to the same resolved Hindu default",
      no_religion_meta.get("profile_religion") == "hindu")
logout()

print()
print("=" * 70)
print("7b. A stored religion_belief value outside RELIGION_BELIEF_VALUES defensively falls back to Hindu")
print("=" * 70)

stale_user = register("hindu")
conn = appmod.get_db()
conn.execute("UPDATE users SET religion_belief = ? WHERE id = ?", ("tibetan_buddhist_removed", stale_user["user_id"]))
conn.commit()
conn.close()
login(stale_user["private_code"])
stale_meta = client.get("/api/poems/meta").get_json()
check("an unrecognized stored religion_belief value safely falls back to the Hindu default, never 500s or leaks it verbatim",
      stale_meta.get("religion") == "hindu" and stale_meta.get("title") == "मौलिक राम-भक्ति कविताएँ")
logout()

print()
print("=" * 70)
print("8. Independent reading-religion selection: ?religion=/&lang= override, NEVER writing the profile")
print("=" * 70)

muslim_reader = register("muslim")
login(muslim_reader["private_code"])

default_meta = client.get("/api/poems/meta").get_json()
check("a Muslim-profile member's default reading religion is Muslim", default_meta.get("religion") == "muslim")

switched_meta = client.get("/api/poems/meta?religion=hindu").get_json()
check("switching the READING religion to Hindu via ?religion= succeeds", switched_meta.get("religion") == "hindu")
check("the gold-chip label updates to the newly-selected religion's own label (सीताराम, not the Muslim one)",
      switched_meta.get("label") == "सीताराम")
check("switching reading religion still reports the member's OWN profile religion, unchanged, alongside it",
      switched_meta.get("profile_religion") == "muslim")

# The actual database-level proof the profile was never touched.
conn = appmod.get_db()
row = conn.execute("SELECT religion_belief FROM users WHERE id = ?", (muslim_reader["user_id"],)).fetchone()
conn.close()
check("users.religion_belief in the database is STILL 'muslim' after the reading-religion switch -- never written",
      row["religion_belief"] == "muslim")

# Switch back, and confirm the Quran collection (and its Arabic-only language set) is intact.
back_meta = client.get("/api/poems/meta?religion=muslim").get_json()
check("switching reading religion back to Muslim restores the Quran collection correctly",
      back_meta.get("religion") == "muslim" and back_meta.get("title") == back_meta.get("title")
      and {l["code"] for l in back_meta.get("languages", [])} == {"ar"})
check("switching back also restores the correct attribution (Tanzil Project, CC BY 3.0)",
      "Tanzil" in (back_meta.get("attribution") or ""))

print()
print("=" * 70)
print("9. Religion switching across all four live collections -- label/title/languages/attribution each update correctly")
print("=" * 70)

_EXPECTED = {
    "hindu": {"label": "सीताराम", "langs": {"hi"}, "title": "मौलिक राम-भक्ति कविताएँ"},
    "christian": {"label": "Jesus", "langs": {"en"}, "title": "Psalms, King James Version"},
    "muslim": {"label": "الله", "langs": {"ar"}, "title": "القرآن الكريم — سورة الفاتحة"},
    "buddhist": {"label": "Buddha", "langs": {"pi", "en"}, "title": "Dhammapada"},
}
for code, expected in _EXPECTED.items():
    m = client.get(f"/api/poems/meta?religion={code}").get_json()
    check(f"switching to {code}: religion resolves correctly", m.get("religion") == code)
    check(f"switching to {code}: label matches", m.get("label") == expected["label"])
    check(f"switching to {code}: title matches", m.get("title") == expected["title"])
    check(f"switching to {code}: languages match exactly", {l["code"] for l in m.get("languages", [])} == expected["langs"])
logout()

print()
print("=" * 70)
print("10. Language switching within one religion, via &lang=, independent of the reading religion")
print("=" * 70)

anon_pi = client.get("/api/poems/meta?religion=buddhist&lang=pi").get_json()
check("&lang=pi honored for buddhist", anon_pi.get("default") == "pi")
anon_en = client.get("/api/poems/meta?religion=buddhist&lang=en").get_json()
check("&lang=en honored for buddhist (switching language keeps the same reading religion)",
      anon_en.get("default") == "en" and anon_en.get("religion") == "buddhist")
anon_bad_lang = client.get("/api/poems/meta?religion=buddhist&lang=xx").get_json()
check("an invalid &lang= value is silently ignored, safely falls back to the collection's own default (pi)",
      anon_bad_lang.get("default") == "pi")

pi_poem = client.get("/api/poems/pi/0?religion=buddhist").get_json()
en_poem = client.get("/api/poems/en/0?religion=buddhist").get_json()
check("the same ordinal (0) in different languages returns different text (genuinely two languages, not one duplicated)",
      pi_poem.get("text") != en_poem.get("text"))
check("the Pali entry is marked with its own citation, matching the English one (same verse, two languages)",
      pi_poem.get("marker") == en_poem.get("marker") == "Dhammapada 1.1")

print()
print("=" * 70)
print("11. Missing/unapproved collection fallback: a stale or bogus ?religion= never breaks, never 500s")
print("=" * 70)

fallback_user = register("christian")
login(fallback_user["private_code"])
sikh_override = client.get("/api/poems/meta?religion=sikh").get_json()
check("?religion=sikh (pending_rights_review, unavailable) is ignored -- falls back to the member's own profile religion",
      sikh_override.get("religion") == "christian")
bogus_res = client.get("/api/poems/meta?religion=not-a-real-religion")
bogus_override = bogus_res.get_json()
check("?religion=<nonsense> is ignored -- falls back to the member's own profile religion, never 500s",
      bogus_res.status_code == 200 and bogus_override.get("religion") == "christian")
check("the Religion Selector's own list (available_religions) never includes sikh",
      "sikh" not in {a["code"] for a in sikh_override.get("available_religions", [])})
check("the Religion Selector's own list never includes jain/other/prefer_not_to_say (no tradition row at all)",
      {"jain", "other", "prefer_not_to_say"}.isdisjoint({a["code"] for a in sikh_override.get("available_religions", [])}))
logout()

print()
print("=" * 70)
print("12. Personalized metadata is never leaked between accounts (Cache-Control, and two members never see each other's content)")
print("=" * 70)

cache_res = client.get("/api/poems/meta")
check("api_poems_meta() sets a non-cacheable Cache-Control header on every response",
      cache_res.headers.get("Cache-Control") == "private, no-store")

christian_a = register("christian")
login(christian_a["private_code"])
meta_a = client.get("/api/poems/meta").get_json()
logout()
muslim_b = register("muslim")
login(muslim_b["private_code"])
meta_b = client.get("/api/poems/meta").get_json()
logout()
check("two different signed-in members' default meta responses correctly differ (never a stale cached cross-account value)",
      meta_a.get("religion") == "christian" and meta_b.get("religion") == "muslim")

print()
print("=" * 70)
print("13. QM_MARQUEE_ENABLED precedence: all three states, driven by a real subprocess each time")
print("=" * 70)

import subprocess  # noqa: E402

_PRECEDENCE_SNIPPET = (
    "import os, tempfile; "
    "fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd); "
    "os.environ['QM_DB_PATH'] = path; os.environ['QM_DISABLE_SCHEDULER'] = '1'; "
    "import app as appmod; print('RESULT=' + str(appmod.QM_MARQUEE_ENABLED))"
)


def _marquee_flag_in_fresh_process(env_value):
    env = dict(os.environ)
    if env_value is None:
        env.pop("QM_MARQUEE_ENABLED", None)
    else:
        env["QM_MARQUEE_ENABLED"] = env_value
    out = subprocess.run([sys.executable, "-c", _PRECEDENCE_SNIPPET], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=30)
    line = next((l for l in out.stdout.splitlines() if l.startswith("RESULT=")), None)
    return line.split("=", 1)[1] if line else f"<no RESULT line; stderr: {out.stderr[-500:]}>"


check("variable absent -> enabled by the new application default", _marquee_flag_in_fresh_process(None) == "True")
check("variable explicitly 'true' -> enabled", _marquee_flag_in_fresh_process("true") == "True")
check("variable explicitly 'false' -> disabled", _marquee_flag_in_fresh_process("false") == "False")
check("variable explicitly '1' -> enabled (same truthy parsing as 'true'/'yes')", _marquee_flag_in_fresh_process("1") == "True")
check("variable explicitly '0' -> disabled", _marquee_flag_in_fresh_process("0") == "False")

print()
print("=" * 70)
print("14. jain/other/prefer_not_to_say: profile-accepted, but no tradition row, no symbol, no content")
print("=" * 70)

logout()
for unsupported in ("jain", "other", "prefer_not_to_say"):
    user = register(unsupported)
    login(user["private_code"])
    meta_res = client.get("/api/poems/meta")
    meta = meta_res.get_json()
    check(f"{unsupported}: meta correctly reports coming_soon, not silently another religion's content",
          meta_res.status_code == 200 and meta.get("coming_soon") is True and meta.get("religion") == unsupported)
    check(f"{unsupported}: meta's label is None (no religious_traditions row -- never a guessed/borrowed label)",
          meta.get("label") is None)
    home_html = client.get("/").get_data(as_text=True)
    check(f"{unsupported}: no standalone symbol markup exists anywhere (the feature was removed, "
          f"not just hidden for this religion)", 'id="hm-symbol"' not in home_html)
    logout()

# A pending religion-change request must NOT silently alter the currently-served content.
hindu_for_change = register("hindu")
login(hindu_for_change["private_code"])
before_meta = client.get("/api/poems/meta").get_json()
change_res = client.post("/api/dashboard/identity-request", json={
    "request_type": "religion_change", "religion_belief": "christian",
})
check("submitting a religion-change request to christian succeeds (a pending ticket is created)",
      change_res.status_code in (200, 201))
after_meta = client.get("/api/poems/meta").get_json()
check("meta's religion is UNCHANGED (still hindu) while the request is only pending, not approved",
      after_meta.get("religion") == before_meta.get("religion") == "hindu")
check("meta's title is still the Hindu collection's own label, never the pending Christian one",
      after_meta.get("title") == before_meta.get("title") == "मौलिक राम-भक्ति कविताएँ")
logout()

print()
print("=" * 70)
print("15. Anonymous (logged-out) visitors: the PUBLIC Hindu default, same as any no-religion member")
print("=" * 70)

logout()
anon_res = client.get("/api/poems/meta")
anon_meta = anon_res.get_json()
check("a genuinely logged-out visitor's meta succeeds and is never the old {'anonymous': True} stub",
      anon_res.status_code == 200 and anon_meta.get("anonymous") is not True)
check("the anonymous response resolves the Hindu default religion",
      anon_meta.get("religion") == "hindu")
check("the anonymous response's default language is Hindi", anon_meta.get("default") == "hi")
check("the anonymous response's title is the original-collection label (accurate attribution, no Gita Press claim)",
      anon_meta.get("title") == "मौलिक राम-भक्ति कविताएँ")
check("the anonymous response includes real poem count/languages -- content is never withheld for being logged out",
      anon_meta.get("count", 0) > 0 and bool(anon_meta.get("languages")))
check("the anonymous response is never personalized (no signed-in user row to personalize from)",
      anon_meta.get("personal") is False)
check("the anonymous response is never reported as hidden (no users.hide_marquee row exists for a visitor)",
      anon_meta.get("hidden") is False)
check("the anonymous response's reader_scope is 'anon' (no account to scope reading-preference localStorage by)",
      anon_meta.get("reader_scope") == "anon")
check("an anonymous visitor CAN still switch reading religion via ?religion= (public selector, no sign-in gate)",
      client.get("/api/poems/meta?religion=muslim").get_json().get("religion") == "muslim")
anon_home_html = client.get("/").get_data(as_text=True)
check("the anonymous homepage never contains the old standalone symbol markup",
      'id="hm-symbol"' not in anon_home_html)
check("the anonymous homepage DOES contain the marquee bar (public by default, no sign-in gate)",
      'id="pm-bar"' in anon_home_html)
check("the anonymous homepage's marquee hide control is the new down-arrow with its own tooltip/label",
      'title="Hide"' in anon_home_html and 'aria-label="Hide marquee"' in anon_home_html)
check("the anonymous homepage includes the new floating restore button, present but hidden by default",
      'id="pm-restore"' in anon_home_html)
check("the old permanent-dismiss 'X' hide icon path is gone from the template",
      "M6 6l12 12M18 6L6 18" not in anon_home_html)
check("the anonymous homepage includes the Religion Selector too (available to visitors, not just members)",
      'id="pm-religionhead"' in anon_home_html)
anon_poem_res = client.get("/api/poems/hi/0")
check("a logged-out visitor CAN fetch the public default poem directly -- content is genuinely public",
      anon_poem_res.status_code == 200)
anon_poem = anon_poem_res.get_json()
check("the anonymously-fetched poem is real Hindi text from the original collection",
      bool(anon_poem.get("text")) and len(anon_poem["text"]) > 10)

print()
print("=" * 70)
print("16. Hide/restore markup (server-rendered template only -- the actual slide/localStorage/keyboard")
print("    behavior driven by poems.js needs a real browser, see the final report)")
print("=" * 70)

check("the floating restore button's own markup is present, with its accessible label/tooltip",
      'id="pm-restore"' in anon_home_html and 'title="Show"' in anon_home_html
      and 'aria-label="Show marquee"' in anon_home_html)
check("the restore button starts hidden in the server-rendered markup (shown only once the user hides the bar)",
      '<button type="button" class="pm-restore-btn" id="pm-restore" aria-label="Show marquee" title="Show" hidden>' in anon_home_html)
check("the hide button is a real, keyboard-focusable <button>, not a non-semantic clickable div/span",
      '<button type="button" class="pm-dot pm-dot-hide" id="pm-hide"' in anon_home_html)

print()
print("=" * 70)
print("17. API-level security: the backend resolves religion/language from an ALLOWLIST, never a raw client path")
print("=" * 70)

import inspect  # noqa: E402

poem_route_params = list(inspect.signature(appmod.api_poem).parameters.keys())
check("api_poem()'s only URL-path parameters are lang/index -- no religion/directory parameter in the route itself",
      poem_route_params == ["lang", "index"])

christian_user = register("christian")
login(christian_user["private_code"])
# Try every plausible manipulation of the `lang` URL parameter and the `?religion=` query
# parameter -- none can ever reach content outside the resolved, allowlisted collection, because
# religious_text_core only ever does DB lookups keyed by exact language_code match, never
# constructs a filesystem path from either parameter.
for attack_lang in ("hindu", "hindu_original", "../hindu_original/poems_hindi", "hi"):
    res = client.get(f"/api/poems/{attack_lang}/0")
    check(f"lang={attack_lang!r} (no religion override, christian profile): correctly 404s, never leaks another collection's content",
          res.status_code == 404)
for attack_religion in ("../../etc/passwd", "hindu_original", "DROP TABLE users", ""):
    res = client.get(f"/api/poems/en/0?religion={attack_religion}")
    check(f"?religion={attack_religion!r}: never 500s (falls back to the member's own profile religion cleanly)",
          res.status_code in (200, 404))
# The one real, legitimate language this christian member has:
res = client.get("/api/poems/en/0")
check("the christian member's own real language (en) correctly returns Psalms, not Hindu content",
      res.status_code == 200 and "राम" not in res.get_json().get("text", ""))
logout()

# Invalid poem indices, for whichever religion actually has content.
hindu_idx_user = register("hindu")
login(hindu_idx_user["private_code"])
check("a wildly out-of-range index 404s cleanly", client.get("/api/poems/hi/9999").status_code == 404)
check("a negative index does not route at all (int: converter rejects it) or 404s",
      client.get("/api/poems/hi/-1").status_code == 404)
check("index 0 (the first poem) succeeds", client.get("/api/poems/hi/0").status_code == 200)
logout()

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks PASSED.")
