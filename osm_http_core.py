"""Shared Overpass HTTP layer for OSM features, 2026-11.

Extracted as a standalone module (not a modification of the already-committed, tested
scripts/fetch_north_west_delhi_osm.py) so osm_proximity_worker.py can reuse the SAME
proven request/backoff/User-Agent design without touching committed pilot code. The design here
is deliberately identical to that script's own: a real, configurable project contact in the
User-Agent (never invented), a certifi-backed SSL context, and a bounded 30/60/120s backoff that
respects Retry-After and never retries a non-retryable error -- see
scripts/fetch_north_west_delhi_osm.py's own module docstring for the full reasoning, which applies
unchanged here.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

OVERPASS_URL = os.environ.get("QM_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
DEFAULT_CONTACT_EMAIL = "founder@qumanity.in"  # Qumanity's own published contact -- see docs/dpg_evidence/03_clear_ownership.md
BACKOFF_SCHEDULE_SECONDS = (30, 60, 120)
RETRYABLE_HTTP_STATUSES = {429, 502, 503, 504}


class OverpassError(RuntimeError):
    """Raised when Overpass cannot be reached or returns an unusable response, after retries."""


def contact_email() -> str:
    return os.environ.get("QM_OSM_CONTACT_EMAIL", DEFAULT_CONTACT_EMAIL)


def user_agent(purpose: str) -> str:
    return f"QumanityOSM/1.0 ({purpose}; contact: {contact_email()})"


def post_overpass(query: str, purpose: str, opener=None, sleep=time.sleep) -> dict:
    """POSTs one Overpass QL query with bounded retry/backoff. `opener` is injectable for tests."""
    opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT))
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    headers = {"User-Agent": user_agent(purpose), "Content-Type": "application/x-www-form-urlencoded"}

    for attempt in range(len(BACKOFF_SCHEDULE_SECONDS) + 1):
        req = urllib.request.Request(OVERPASS_URL, data=data, headers=headers, method="POST")
        try:
            resp = opener(req, 60)
            raw = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw_body = e.read() if hasattr(e, "read") else b""
            if status in RETRYABLE_HTTP_STATUSES and attempt < len(BACKOFF_SCHEDULE_SECONDS):
                wait = _retry_wait(e.headers.get("Retry-After") if e.headers else None, attempt)
                print(f"[retry] Overpass returned HTTP {status}; waiting {wait}s "
                      f"(attempt {attempt + 1}/{len(BACKOFF_SCHEDULE_SECONDS)})", file=sys.stderr)
                sleep(wait)
                continue
            raise OverpassError(f"Overpass request failed: HTTP {status}: {raw_body[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < len(BACKOFF_SCHEDULE_SECONDS):
                wait = BACKOFF_SCHEDULE_SECONDS[attempt]
                print(f"[retry] Overpass network error ({e}); waiting {wait}s "
                      f"(attempt {attempt + 1}/{len(BACKOFF_SCHEDULE_SECONDS)})", file=sys.stderr)
                sleep(wait)
                continue
            raise OverpassError(f"Overpass unreachable after {len(BACKOFF_SCHEDULE_SECONDS)} retries: {e}") from e

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            if attempt < len(BACKOFF_SCHEDULE_SECONDS):
                wait = BACKOFF_SCHEDULE_SECONDS[attempt]
                print(f"[retry] malformed Overpass response ({e}); waiting {wait}s "
                      f"(attempt {attempt + 1}/{len(BACKOFF_SCHEDULE_SECONDS)})", file=sys.stderr)
                sleep(wait)
                continue
            raise OverpassError(f"Malformed Overpass response after retries: {e}") from e

        if "elements" not in parsed:
            raise OverpassError(f"Overpass response missing 'elements' (remark: {parsed.get('remark')!r})")
        return parsed

    raise OverpassError("Overpass request exhausted all retries")  # unreachable in practice


def _retry_wait(retry_after_header, attempt: int) -> int:
    scheduled = BACKOFF_SCHEDULE_SECONDS[attempt]
    if retry_after_header and str(retry_after_header).strip().isdigit():
        return max(scheduled, int(str(retry_after_header).strip()))
    return scheduled
