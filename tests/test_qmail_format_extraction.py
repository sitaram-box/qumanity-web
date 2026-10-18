"""Verifies the structural precondition for the qmail_format.js extraction (2026-10-18):
templates/dashboard.html loads static/js/qmail_format.js BEFORE both consumers that call
window.qmRenderFormattedText at render time (dashboard.js's apOpenCouncil and dash_extras.js's
member mailbox). None of these three <script> tags use defer/async, so the browser executes them
strictly in document order -- get the order right in the HTML and the function is guaranteed
defined before either consumer's code can run; get it wrong and window.qmRenderFormattedText is
undefined the first time either tries to call it.

This is as far as a Python test can reach. Whether window.qmRenderFormattedText is ACTUALLY
defined at runtime, and whether the two consumers actually render a formatted body correctly, are
facts about the browser's JS runtime with no Python-testable surface in this project's stack (no
Selenium/Playwright/jsdom installed) -- the same honest boundary already documented for the
renderer's <script>/javascript: safety properties in docs/QMAIL.md. Both were verified directly,
by hand, in a live browser this session, immediately after the extraction: window.
qmRenderFormattedText was confirmed defined via a direct property check, the Admin Panel's council
detail view rendered a real <b>/<i> body, the member mailbox's inbox rendered the same, and the
console showed zero errors throughout. That is a one-time manual proof, not a regression test --
nothing in this file re-checks runtime behavior, and a future change could break it without this
suite catching it.

Standalone script, no test framework (none installed in this project). Pure static-file
inspection, no Flask app needed.

Run with: python3 tests/test_qmail_format_extraction.py
"""
from __future__ import annotations

import re
import sys

ROOT = "/Users/macmudgal/Desktop/Qumanity_DPG"

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


print("=" * 70)
print("Script tag order in templates/dashboard.html")
print("=" * 70)

html = open(f"{ROOT}/templates/dashboard.html").read()
srcs = re.findall(r'<script src="\{\{ url_for\(\'static\', filename=\'(js/[^\']+)\'\) \}\}"', html)
check("qmail_format.js, dashboard.js and dash_extras.js are all present among the script tags",
      {"js/qmail_format.js", "js/dashboard.js", "js/dash_extras.js"} <= set(srcs))

idx_format = srcs.index("js/qmail_format.js")
idx_dashboard = srcs.index("js/dashboard.js")
idx_extras = srcs.index("js/dash_extras.js")
check("qmail_format.js loads BEFORE dashboard.js (apOpenCouncil's own consumer)",
      idx_format < idx_dashboard)
check("qmail_format.js loads BEFORE dash_extras.js (the member mailbox's own consumer)",
      idx_format < idx_extras)

none_deferred = all(
    'defer' not in html[html.find(f'js/{name}') - 60:html.find(f'js/{name}') + 20]
    and 'async' not in html[html.find(f'js/{name}') - 60:html.find(f'js/{name}') + 20]
    for name in ("qmail_format.js", "dashboard.js", "dash_extras.js")
)
check("none of the three tags use defer/async -- document order IS execution order, "
      "deterministically, not just usually", none_deferred)

print()
print("=" * 70)
print("The extraction left dashboard.js's other code alone")
print("=" * 70)

dashboard_js = open(f"{ROOT}/static/js/dashboard.js").read()
check("dashboard.js no longer DEFINES qmRenderFormattedText (moved out, not duplicated)",
      "function qmRenderFormattedText" not in dashboard_js)
check("dashboard.js still CALLS window.qmRenderFormattedText (apOpenCouncil, untouched)",
      "window.qmRenderFormattedText(" in dashboard_js)
check("apOpenCouncil itself is still present and intact",
      "function apOpenCouncil" in dashboard_js)

qmail_format_js = open(f"{ROOT}/static/js/qmail_format.js").read()
check("qmail_format.js defines the function and assigns it to window",
      "function qmRenderFormattedText" in qmail_format_js
      and "window.qmRenderFormattedText = qmRenderFormattedText" in qmail_format_js)

dash_extras_js = open(f"{ROOT}/static/js/dash_extras.js").read()
check("dash_extras.js needed no change -- it already called window.qmRenderFormattedText, "
      "which now resolves to the extracted file instead of dashboard.js's old local copy",
      "window.qmRenderFormattedText(" in dash_extras_js)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL EXTRACTION STRUCTURE CHECKS PASSED")
