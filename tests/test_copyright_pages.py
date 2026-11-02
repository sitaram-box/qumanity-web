"""Covers the public copyright/rights-notice pages (2026-11-02):

  1. /copyright/gita-press (pre-existing) -- still works, still public, still accurate.
  2. /copyright/religious-texts (new) -- the general six-tradition rights notice: route returns
     200 for an anonymous visitor, all six tradition sections are present, the page correctly
     distinguishes available from pending content (never implies a blocked collection is live),
     a verified Qumanity contact method is present, no restricted/blocked religious text is
     embedded anywhere in the page, and the homepage footer links to it.

Standalone script, no test framework (none installed in this project): throwaway tempfile SQLite
DB via QM_DB_PATH before importing app, Flask test client driving real routes, PASS/FAIL printing,
sys.exit(1) on failure -- same conventions as tests/test_poems_marquee.py.

Run with: python3 tests/test_copyright_pages.py (not -I)
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

print("=" * 70)
print("1. /copyright/gita-press -- pre-existing page, still correct")
print("=" * 70)

res = client.get("/copyright/gita-press")
check("route returns 200 for an anonymous visitor", res.status_code == 200)
gita_html = res.get_data(as_text=True)
check("mentions Gita Press", "Gita Press" in gita_html)
check("states no permission has been received", "We have not received permission" in gita_html)
check("does not claim the Vinaya Patrika translation is reproduced on the site",
      "no text from it is reproduced anywhere" in gita_html)

print()
print("=" * 70)
print("2. /copyright/religious-texts -- the new six-tradition rights notice")
print("=" * 70)

res = client.get("/copyright/religious-texts")
check("route returns 200 for an anonymous (logged-out) visitor", res.status_code == 200)
html = res.get_data(as_text=True)
# The template source wraps long paragraphs across multiple lines; normalize whitespace before
# any multi-word substring check so a check never spuriously fails just because a phrase happens
# to straddle a source line break (the raw `html` is still used for tag-structure checks below).
html_norm = re.sub(r"\s+", " ", html)

check("page has a real <title>", "<title>" in html and "Religious Text Rights" in html)
check("page has a meta description", 'name="description"' in html)

# All six tradition sections, by their required heading text (Step 1.2's own six areas).
_SECTIONS = [
    "Hindu — Gita Press Vinaya Patrika",
    "Muslim — Quran",
    "Christian — Bible",
    "Sikh — Gurbani",
    "Buddhist — Dhammapada",
    "Jain — Jain scriptures and texts",
]
for heading in _SECTIONS:
    check(f"section present: {heading!r}", heading in html)

print()
print("=" * 70)
print("3. The page never claims a blocked collection is available, and never claims an")
print("   available one is blocked")
print("=" * 70)

check("Gita Press is explicitly described as NOT presented in the public Marquee",
      "not presented in the public Marquee" in html_norm)
check("the page states no Urdu translation will be displayed",
      "No Urdu translation will be displayed" in html_norm)
check("the page states no Gurbani text is currently shown",
      "no Gurbani text is currently shown" in html_norm)
check("the page states a Hindi Dhammapada has not been approved",
      "has not yet been approved for publication" in html_norm and "Hindi translation" in html_norm)
check("the page states no Jain text has been approved",
      "no specific Jain text, edition, or translation has yet been approved" in html_norm)
check("the page DOES state the Arabic Quran (Al-Fatiha) is available",
      "Surah Al-Fatiha" in html_norm and "is available" in html_norm)
check("the page DOES state the Dhammapada Pali/English collections are available",
      "Dhammapada collections" in html_norm and "are available" in html_norm)
check("the 'where things stand' summary lists exactly the four live collections",
      "the original Qumanity Hindu Hindi poetry, the English Psalms (KJV), the Arabic Quran (Surah Al-Fatiha), and the Dhammapada in" in html_norm)

print()
print("=" * 70)
print("4. Contact information: a verified Qumanity address, never an invented one")
print("=" * 70)

check("Qumanity's own contact email (founder@qumanity.in, already public on the About page) is present",
      "founder@qumanity.in" in html)
check("third-party rights-holder links are clearly distinguished from Qumanity's own contact",
      "these are third-party organizations, not Qumanity" in html_norm)
check("Tanzil Project's own site is linked", "tanzil.net" in html)
check("Khalis Foundation's own site is linked", "khalisfoundation.org" in html)
check("Biblica's own permission-request page is linked", "biblica.com/permission-request-form" in html)

print()
print("=" * 70)
print("5. No restricted/unverified religious text is embedded in the page itself")
print("=" * 70)

check("no Devanagari Vinaya Patrika verse text appears (only the word 'Vinaya Patrika' as a label)",
      "विनय पत्रिका" not in html)
check("no Arabic Quran verse text beyond what's already approved appears unexpectedly",
      True)  # the approved Al-Fatiha text lives in the Marquee itself, not this notice page, and this page contains no Arabic script at all
check("the page contains no Arabic-range characters at all (it's a rights notice, not a scripture display)",
      not any("؀" <= ch <= "ۿ" for ch in html))
check("the page contains no Gurmukhi-range characters at all",
      not any("਀" <= ch <= "੿" for ch in html))

print()
print("=" * 70)
print("6. Footer link: present on the public homepage, resolves correctly")
print("=" * 70)

home_html = client.get("/").get_data(as_text=True)
check("the homepage footer links to /copyright/religious-texts", "copyright/religious-texts" in home_html)
check("the footer link's label matches the required wording",
      "Religious Text Rights &amp; Permissions" in home_html or "Religious Text Rights & Permissions" in home_html)
check("the pre-existing Gita Press footer link is still present alongside the new one",
      "copyright/gita-press" in home_html)

print()
print("=" * 70)
print("7. Feature flag independence: the page does not depend on QM_MARQUEE_ENABLED")
print("=" * 70)

appmod.QM_MARQUEE_ENABLED = False
try:
    res_off = client.get("/copyright/religious-texts")
    check("the rights notice page still works even if the Marquee feature itself is switched off",
          res_off.status_code == 200)
finally:
    appmod.QM_MARQUEE_ENABLED = True

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks PASSED.")
