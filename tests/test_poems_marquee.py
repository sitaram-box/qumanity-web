"""Covers the poems marquee / religion identity box redesign (2026-11-01, updated 2026-11-XX):

  1. QM_MARQUEE_ENABLED defaults True -- the marquee is live by default unless explicitly disabled.
  2. app.py's _poems_dir_for()/_poems() Vinaya-Patrika-vs-original fallback resolution: the
     "hindu" religion automatically serves Poems/hindu_original/ (newly-written, uncopied content)
     whenever Poems/hindu/ (the reserved, rights-cleared-edition slot) has no files -- which is
     still the case today -- and would prefer Poems/hindu/ automatically the moment real files
     ever appear there, with no code change.
  3. The standalone homepage religious symbol (formerly #hm-symbol, Shivalinga/राम/crescent/cross/
     khanda/dharma-wheel) is REMOVED entirely (2026-11-XX) -- religious identity now lives only
     inside the marquee's own gold chip (#pm-chip), which is data-driven from api_poems_meta()'s
     "religion"/"coming_soon"/"anonymous" fields.
  4. api_poems_meta()'s "title" field correctly distinguishes the original collection's own label
     ("मौलिक राम-भक्ति कविताएँ") from what a real Vinaya Patrika edition would say, and the two are
     never conflated.
  5. A LOGGED-OUT visitor is never assigned a religion (2026-11-XX privacy fix, replacing the
     previous DEFAULT_MARQUEE_RELIGION="hindu" default): /api/poems/meta returns {"anonymous":
     true} and nothing else, for every logged-out request, unconditionally.
  6. Every religion with an approved chip mapping (hindu/christian/muslim/sikh/buddhist) is
     reachable server-side via api_poems_meta(); jain/other/prefer_not_to_say correctly have none.

Standalone script, no test framework (none installed in this project): throwaway tempfile SQLite
DB via QM_DB_PATH before importing app, Flask test client driving real routes, PASS/FAIL printing,
sys.exit(1) on failure -- same conventions as tests/test_family_tree_cascade.py.

Note: this is a Flask-test-client script, not a browser -- it cannot execute poems.js, so it
cannot directly observe the gold chip's RENDERED text/visibility. It verifies everything the
server controls (api_poems_meta()'s fields, which religions resolve to what, the absence of the
removed #hm-symbol markup) and leaves client-rendered chip content to the separate live-browser
verification pass.

Run with: python3 tests/test_poems_marquee.py (not -I)
"""
from __future__ import annotations

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
    # call always overwrote it; the new anonymous-visitor checks below depend on this actually
    # clearing the session, which is what surfaced the bug (2026-11-XX fix).
    client.get("/logout")


print("=" * 70)
print("1. QM_MARQUEE_ENABLED defaults True (no env var set)")
print("=" * 70)

check("QM_MARQUEE_ENABLED is True by default", appmod.QM_MARQUEE_ENABLED is True)

print()
print("=" * 70)
print("2. _poems_dir_for(): the Vinaya-Patrika-vs-original fallback, resolved against the ACTUAL on-disk state")
print("=" * 70)

hindu_dir, hindu_title = appmod._poems_dir_for("hindu")
check("Poems/hindu/ (the reserved, rights-cleared slot) is still genuinely empty on disk today",
      not any((appmod.POEMS_DIR / "hindu").glob("*.json")) if (appmod.POEMS_DIR / "hindu").is_dir() else True)
check("hindu resolves to the original fallback directory, not the (empty) primary one",
      hindu_dir == "hindu_original")
check("hindu's resolved title is the original-collection label, never claims Vinaya Patrika",
      hindu_title == "मौलिक राम-भक्ति कविताएँ")

christian_dir, christian_title = appmod._poems_dir_for("christian")
check("christian (no fallback configured, and doesn't need one) resolves to its own real directory",
      christian_dir == "christian")
check("christian's title is its own real source label", christian_title == "Psalms, King James Version")

check("a religion with no RELIGION_MARQUEE_SOURCES entry at all resolves to (None, None)",
      appmod._poems_dir_for("muslim") == (None, None))

print()
print("=" * 70)
print("3. The original Hindi collection itself: real, loadable, correctly shaped")
print("=" * 70)

hindu_poems = appmod._poems("hindu", "hi")
check("_poems('hindu', 'hi') returns real poems (the original collection, via the fallback)",
      bool(hindu_poems) and len(hindu_poems) >= 10)
check("every poem has the {id, marker, text} shape", all({"id", "marker", "text"} <= set(p.keys()) for p in hindu_poems))
check("poems are sorted by id", [p["id"] for p in hindu_poems] == sorted(p["id"] for p in hindu_poems))
check("no poem's marker claims this is Vinaya Patrika",
      all("विनय" not in p["marker"] and "patrika" not in p["marker"].lower() for p in hindu_poems))

print()
print("=" * 70)
print("4. GET /api/poems/meta: live end-to-end, for a signed-in Hindu member")
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
# api_poems_meta() personalizes "languages" to the SIGNED-IN member's own registered languages
# (not the raw content-language list) once a user is attached -- this test's member registered
# with "English", which the original collection has no translation for yet, so it's correctly
# marked unavailable here; real Hindi-content availability is already proven directly in section 3
# above via _poem_languages("hindu"), independent of any one member's own language choice.
check("meta is personalized for a signed-in member", meta.get("personal") is True)
check("the member's own (English) language is listed, correctly marked unavailable (no English translation of the original collection exists yet)",
      any(l["code"] == "en" and l.get("available") is False for l in meta.get("languages", [])))

res2 = client.get("/api/poems/hi/0")
check("fetching the actual first poem by index succeeds", res2.status_code == 200)
poem0 = res2.get_json()
check("the fetched poem has real Hindi text, not a placeholder", bool(poem0.get("text")) and len(poem0["text"]) > 10)

print()
print("=" * 70)
print("5. The standalone homepage symbol is GONE; the gold chip lives only in the marquee template")
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
print("6. Non-Hindu religions: content resolution unaffected; each resolves correctly server-side")
print("=" * 70)

logout()
for religion in ("muslim", "christian", "sikh", "buddhist"):
    user = register(religion)
    login(user["private_code"])
    meta_res = client.get("/api/poems/meta")
    meta = meta_res.get_json()
    home_html = client.get("/").get_data(as_text=True)
    check(f"{religion}: no standalone symbol markup anywhere on the homepage (it no longer exists)",
          'id="hm-symbol"' not in home_html)
    check(f"{religion}: never sees the old Shivalinga path data",
          "M48 7 C33 7 24 18 23 34" not in home_html)
    if religion == "christian":
        check("christian: meta resolves real content (not coming_soon)", meta.get("coming_soon") is not True)
    else:
        check(f"{religion}: meta correctly reports coming_soon (no poem content exists yet)",
              meta_res.status_code == 200 and meta.get("coming_soon") is True and meta.get("religion") == religion)
    logout()

logout()
no_religion_user = register("")
login(no_religion_user["private_code"])
meta_res = client.get("/api/poems/meta")
check("a member with no declared religion gets hidden:true (no inferred identity), even with the feature on",
      meta_res.status_code == 200 and meta_res.get_json().get("hidden") is True)
logout()

print()
print("=" * 70)
print("7. QM_MARQUEE_ENABLED precedence: all three states, driven by a real subprocess each time")
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
print("8. All ten member states from the audit's own required list")
print("=" * 70)

logout()
# State 6: "another supported religion, if such a mapping exists" -- RELIGION_MARQUEE_SOURCES only
# defines hindu/christian (poem CONTENT); the gold chip's own identity-label mapping (poems.js's
# CHIP_BY_RELIGION, client-side) separately covers hindu/christian/muslim/sikh/buddhist for the
# IDENTITY BOX, independent of whether poem content exists for that religion. Confirmed exhaustively.
check("RELIGION_MARQUEE_SOURCES (poem content) covers exactly hindu and christian, nothing else",
      set(appmod.RELIGION_MARQUEE_SOURCES.keys()) == {"hindu", "christian"})

# State 8: religion unsupported by the current symbol/content catalogue (jain/other/prefer_not_to_say)
for unsupported in ("jain", "other", "prefer_not_to_say"):
    user = register(unsupported)
    login(user["private_code"])
    meta_res = client.get("/api/poems/meta")
    meta = meta_res.get_json()
    check(f"{unsupported}: meta correctly reports coming_soon, not silently another religion's content",
          meta_res.status_code == 200 and meta.get("coming_soon") is True and meta.get("religion") == unsupported)
    home_html = client.get("/").get_data(as_text=True)
    check(f"{unsupported}: no standalone symbol markup exists anywhere (the feature was removed, "
          f"not just hidden for this religion)", 'id="hm-symbol"' not in home_html)
    logout()

# State 9: a pending religion-change request must NOT silently alter the currently-served content.
hindu_for_change = register("hindu")
login(hindu_for_change["private_code"])
before_res = client.get("/api/poems/meta")
before_meta = before_res.get_json()
change_res = client.post("/api/dashboard/identity-request", json={
    "request_type": "religion_change", "religion_belief": "christian",
})
check("submitting a religion-change request to christian succeeds (a pending ticket is created)",
      change_res.status_code in (200, 201))
after_res = client.get("/api/poems/meta")
after_meta = after_res.get_json()
check("meta's religion is UNCHANGED (still hindu) while the request is only pending, not approved",
      after_meta.get("religion") == before_meta.get("religion") == "hindu")
check("meta's title is still the Hindu collection's own label, never the pending Christian one",
      after_meta.get("title") == before_meta.get("title") == "मौलिक राम-भक्ति कविताएँ")
logout()

print()
print("=" * 70)
print("8b. Anonymous (logged-out) visitors: never assigned a religion, never shown a Hindu default")
print("=" * 70)

logout()
anon_res = client.get("/api/poems/meta")
anon_meta = anon_res.get_json()
check("a genuinely logged-out visitor's meta response is exactly {'anonymous': True}, nothing else",
      anon_res.status_code == 200 and anon_meta == {"anonymous": True})
check("the anonymous response never includes a 'religion' field",
      "religion" not in anon_meta)
check("the anonymous response never includes poem 'count'/'languages' fields",
      "count" not in anon_meta and "languages" not in anon_meta)
anon_home_html = client.get("/").get_data(as_text=True)
check("the anonymous homepage never contains the old standalone symbol markup",
      'id="hm-symbol"' not in anon_home_html)
check("the anonymous homepage never contains सीताराम anywhere in the raw page (no Hindu default leak)",
      "सीताराम" not in anon_home_html)
# Direct poem-fetch attempt by a logged-out visitor must also 404 -- confirms the backend, not just
# the frontend JS, is what's actually enforcing "no anonymous content" (api_poem() resolves
# religion via the session, which is now None for a logged-out request).
anon_poem_res = client.get("/api/poems/hi/0")
check("a logged-out visitor cannot fetch a poem directly either, even by guessing the URL",
      anon_poem_res.status_code == 404)

print()
print("=" * 70)
print("9. API-level security: the backend resolves religion from the session, never from a client-supplied parameter")
print("=" * 70)

import inspect  # noqa: E402

poem_route_params = list(inspect.signature(appmod.api_poem).parameters.keys())
check("api_poem()'s only parameters are lang/index -- no religion or directory parameter exists to manipulate at all",
      poem_route_params == ["lang", "index"])

christian_user = register("christian")
login(christian_user["private_code"])
# Try every plausible manipulation of the one parameter that DOES exist (lang) -- none of them can
# ever reach Hindu content, because _poems() always looks up the SESSION's own resolved religion
# first; `lang` only ever selects among THAT religion's own available languages.
for attack_lang in ("hindu", "hindu_original", "../hindu_original/poems_hindi", "hi"):
    res = client.get(f"/api/poems/{attack_lang}/0")
    if attack_lang == "hi":
        # Christian's own real language is "en", not "hi" -- this must 404, not silently serve
        # content in a language this religion's source doesn't actually have.
        check(f"lang={attack_lang!r}: correctly 404s (christian has no 'hi' content)", res.status_code == 404)
    else:
        check(f"lang={attack_lang!r}: correctly 404s, never leaks another religion's directory contents",
              res.status_code == 404)
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
print("10. The original Hindi collection's own data integrity (re-checked as part of the regression suite, not just by hand)")
print("=" * 70)

import json as _json  # noqa: E402

_poems_path = appmod.POEMS_DIR / "hindu_original" / "poems_hindi.json"
with open(_poems_path, "r", encoding="utf-8") as _f:
    _raw_bytes_ok = True
    _f.seek(0)
with open(_poems_path, "rb") as _f:
    _raw = _f.read()
_hindu_original_poems = _json.loads(_raw.decode("utf-8"))

check("the file decodes as strict UTF-8 with no BOM", not _raw.startswith(b"\xef\xbb\xbf"))
check("exactly 20 poems, as reported", len(_hindu_original_poems) == 20)
_ids = [p["id"] for p in _hindu_original_poems]
check("no duplicate poem ids", len(_ids) == len(set(_ids)))
check("ids are contiguous 1..20", _ids == list(range(1, 21)))
check("every poem has non-empty marker and text", all(p.get("marker", "").strip() and p.get("text", "").strip() for p in _hindu_original_poems))
check("no poem's marker or text contains HTML/script-like content", all(
    "<" not in p["marker"] and ">" not in p["marker"] and "<" not in p["text"] and ">" not in p["text"]
    for p in _hindu_original_poems
))
check("no poem's marker claims this is Vinaya Patrika or a scriptural quotation",
      all("विनय" not in p["marker"] and "पत्रिका" not in p["marker"] for p in _hindu_original_poems))
check("every poem's text contains at least one Devanagari character (not broken/empty rendering)",
      all(any("ऀ" <= ch <= "ॿ" for ch in p["text"]) for p in _hindu_original_poems))

print()
print("=" * 70)
print("11. Regression: the real Vinaya Patrika copyright safeguard is untouched by any of this")
print("=" * 70)

check("Poems/hindu/ (the reserved, rights-cleared slot) is still genuinely empty",
      not (appmod.POEMS_DIR / "hindu").is_dir() or not any((appmod.POEMS_DIR / "hindu").glob("*.json")))
check("no file anywhere under Poems/hindu_original/ mentions Poddar (the removed translator)",
      "पोद्दार" not in _raw.decode("utf-8") and "Poddar" not in _raw.decode("utf-8"))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks PASSED.")
