"""Verifies the structural precondition for the qmail_format.js extraction (2026-10-18):
templates/dashboard.html and templates/qmail.html both load static/js/qmail_format.js BEFORE the
consumer on that page that calls window.qmRenderFormattedText at render time (dashboard.js's
apOpenCouncil on the dashboard; qmail.js's reading pane on /qmail). None of these <script> tags
use defer/async, so the browser executes them strictly in document order -- get the order right
in the HTML and the function is guaranteed defined before either consumer's code can run; get it
wrong and window.qmRenderFormattedText is undefined the first time either tries to call it.

dash_extras.js is NOT a consumer any more, and that is correct, not a regression: the member
mailbox UI (which used to live inline on the dashboard, in dash_extras.js) moved entirely to the
standalone /qmail page in this same pass, taking its only call to window.qmRenderFormattedText
with it. dash_extras.js keeps the Qmail *activation* card (username chooser, address display,
"Open Qmail ->" link) -- none of which needs the formatted-text renderer at all.

This is as far as a Python test can reach. Whether window.qmRenderFormattedText is ACTUALLY
defined at runtime, and whether the two real consumers (the Admin Panel's council detail view,
and /qmail's own reading pane) actually render a formatted body correctly, are facts about the
browser's JS runtime with no Python-testable surface in this project's stack (no
Selenium/Playwright/jsdom installed) -- the same honest boundary already documented for the
renderer's <script>/javascript: safety properties in docs/QMAIL.md. Both were verified directly,
by hand, in a live browser, immediately after the extraction and again after the /qmail page was
built: window.qmRenderFormattedText confirmed defined via a direct property check, the Admin
Panel's council detail view and /qmail's reading pane both rendered a real <b>/<i>/<a> body, and
the console showed zero errors throughout. That is a one-time manual proof, not a regression test
-- nothing in this file re-checks runtime behavior, and a future change could break it without
this suite catching it.

Standalone script, no test framework (none installed in this project). Pure static-file
inspection, no Flask app needed.

Run with: python3 tests/test_qmail_format_extraction.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


def script_srcs(html):
    return re.findall(r'<script src="\{\{ url_for\(\'static\', filename=\'(js/[^\']+)\'\) \}\}"', html)


def none_deferred(html, names):
    return all(
        'defer' not in html[html.find(f'js/{name}') - 60:html.find(f'js/{name}') + 20]
        and 'async' not in html[html.find(f'js/{name}') - 60:html.find(f'js/{name}') + 20]
        for name in names
    )


print("=" * 70)
print("Script tag order in templates/dashboard.html (apOpenCouncil's consumer)")
print("=" * 70)

dashboard_html = open(f"{ROOT}/templates/dashboard.html").read()
srcs = script_srcs(dashboard_html)
check("qmail_format.js and dashboard.js are both present among dashboard.html's script tags",
      {"js/qmail_format.js", "js/dashboard.js"} <= set(srcs))
check("qmail_format.js loads BEFORE dashboard.js", srcs.index("js/qmail_format.js") < srcs.index("js/dashboard.js"))
check("neither tag uses defer/async -- document order IS execution order, deterministically",
      none_deferred(dashboard_html, ("qmail_format.js", "dashboard.js")))

print()
print("=" * 70)
print("Script tag order in templates/qmail.html (the new page's own consumer)")
print("=" * 70)

qmail_html = open(f"{ROOT}/templates/qmail.html").read()
qsrcs = script_srcs(qmail_html)
check("qmail_format.js and qmail.js are both present among qmail.html's script tags",
      {"js/qmail_format.js", "js/qmail.js"} <= set(qsrcs))
check("qmail_format.js loads BEFORE qmail.js", qsrcs.index("js/qmail_format.js") < qsrcs.index("js/qmail.js"))
check("neither tag uses defer/async", none_deferred(qmail_html, ("qmail_format.js", "qmail.js")))

print()
print("=" * 70)
print("The extraction left dashboard.js's other code alone, and dash_extras.js correctly lost its")
print("only call site when the mailbox UI moved to /qmail")
print("=" * 70)

dashboard_js = open(f"{ROOT}/static/js/dashboard.js").read()
check("dashboard.js no longer DEFINES qmRenderFormattedText (moved out, not duplicated)",
      "function qmRenderFormattedText" not in dashboard_js)
check("dashboard.js still CALLS window.qmRenderFormattedText (apOpenCouncil, untouched)",
      "window.qmRenderFormattedText(" in dashboard_js)
check("apOpenCouncil itself is still present and intact", "function apOpenCouncil" in dashboard_js)

qmail_format_js = open(f"{ROOT}/static/js/qmail_format.js").read()
check("qmail_format.js defines the function and assigns it to window",
      "function qmRenderFormattedText" in qmail_format_js
      and "window.qmRenderFormattedText = qmRenderFormattedText" in qmail_format_js)

qmail_js = open(f"{ROOT}/static/js/qmail.js").read()
check("qmail.js (the new page) calls window.qmRenderFormattedText for its reading pane",
      "window.qmRenderFormattedText(" in qmail_js)

dash_extras_js = open(f"{ROOT}/static/js/dash_extras.js").read()
check("dash_extras.js no longer calls window.qmRenderFormattedText at all -- correct, since the "
      "mailbox UI that used to call it moved entirely to /qmail's own script",
      "window.qmRenderFormattedText(" not in dash_extras_js)
check("dash_extras.js still keeps the Qmail ACTIVATION card logic (unrelated to the renderer)",
      "qmailActivateBtn" in dash_extras_js and "renderQmailStatus" in dash_extras_js)

print()
print("=" * 70)
print("The legacy Message Box card is gone, and the activation card now links to /qmail")
print("=" * 70)

check("templates/dashboard.html no longer contains the #qm-messagebox-card element",
      "qm-messagebox-card" not in dashboard_html)
check("templates/dashboard.html no longer contains the old inline #qm-mail-card mailbox UI",
      "qm-mail-card" not in dashboard_html)
check("the Qmail activation card links to the /qmail route", "url_for('qmail_page')" in dashboard_html)

dashboard_css = open(f"{ROOT}/static/css/dashboard.css").read()
check("dashboard.css no longer has the #qm-messagebox-card rule", "qm-messagebox-card" not in dashboard_css)
check("dashboard.css no longer has the old inline .qm-mail-* mailbox rules", ".qm-mail-" not in dashboard_css)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL EXTRACTION STRUCTURE CHECKS PASSED")
