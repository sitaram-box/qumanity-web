# Citizen Report (FIR) system — design note (Item 9)

## 1. Data model

Schema as given, additive only:

```sql
CREATE TABLE reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  location_id TEXT NOT NULL,
  location_level TEXT NOT NULL,       -- always 'village' at creation (see C1)
  body TEXT NOT NULL,
  anonymous INTEGER DEFAULT 0,
  status TEXT DEFAULT 'open',         -- open|in_progress|resolved|denied|escalated
  current_holder_level TEXT,          -- village|tehsil|district|state|zone|country|continent|earth
  current_holder_id TEXT,
  escalation_path TEXT DEFAULT '[]',
  sla_deadline TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  resolved_at TIMESTAMP
);
CREATE INDEX idx_reports_holder ON reports(current_holder_level, current_holder_id);
CREATE INDEX idx_reports_user ON reports(user_id);
CREATE INDEX idx_reports_status ON reports(status, sla_deadline);

CREATE TABLE report_updates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL,
  author_user_id TEXT NOT NULL,
  author_role TEXT,                   -- council_member|admin|system
  update_type TEXT NOT NULL,          -- acknowledged|needs_time|resolved|denied|escalated|comment
  message TEXT,
  new_deadline TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (report_id) REFERENCES reports(id)
);
CREATE INDEX idx_report_updates ON report_updates(report_id, created_at);
```

- **`sla_deadline` is stored, not computed**, because it's mutable business state, not a pure function of `created_at`: a `needs_time` response sets it to a *new* value, and escalating to the next level resets it to a fresh 10-day window for the new holder (recommended — your C3 spec gives the original 10 days but doesn't say whether escalation restarts the clock; restarting is the only reading that makes "council must respond within 10 days" meaningful at *every* level, not just the first). Computing it on read would lose both of those mutations.
- **`escalation_path`** is a pure audit trail, JSON array of `{level, id, at}` appended to on every escalation — not consulted for routing (that's `current_holder_level`/`current_holder_id`, always authoritative) and not editable after the fact. It powers two things: the detail view's timeline ("Escalated to Tehsil on …") and a cheap invariant check — a new escalation's level must come after every level already in the path, which is how "a report cannot bounce back down" is enforced (see §3).
- **Anonymous hides identity from the council too, not just some separate "public."** Reports have no public view at all (unlike posts) — the checkbox's own label ("hidden from public view") only makes sense if "public" here means "everyone except the owner," which per C4 ("If anonymous AND viewed by non-owner → 'Anonymous Citizen'") is exactly council/holder and anyone else who isn't the reporter. Recommendation: `user_id` stays in the row regardless (the owner's own "My Reports" list and any abuse handling need it), but every API response masks the name/account_id/private_id behind "Anonymous Citizen" whenever `anonymous = 1` **and** the requester is neither the owner nor an admin. Admin can always see real identity (same override every other gate in this codebase already gives `_is_admin()`) — flagging this as a recommendation for your confirmation, not an assumption.

## 2. Council assignment

Village-level (the only real case today):

```python
def assign_holder(conn, village_id):
    # Reuses the exact same "active term" query announcements_core.is_council_member
    # already runs -- no need to separately resolve the zodiac cycle via
    # election_core.current_cycle_for_village(); the leadership_start/end window on
    # village_council already IS "whoever is currently serving."
    today = dt.date.today().isoformat()
    row = conn.execute(
        """SELECT male_head_user_id, female_head_user_id FROM village_council
           WHERE village_id = ? AND leadership_start <= ? AND leadership_end >= ?""",
        (village_id, today, today),
    ).fetchone()
    if row and (row["male_head_user_id"] or row["female_head_user_id"]):
        return "village", village_id   # current_holder_id is the village_id; the
                                        # *members* are resolved at read/notify time
                                        # via the same village_council lookup, same
                                        # as announcements_core.is_council_member
    return "earth", "ADMIN"            # Founder/Admin fallback -- see below
```

**Scaling to Tehsil → Earth**: exactly the same gap already documented and approved for Announcements (Item 8) — no elected-council data model exists above village. So:
- A **fresh** report always starts `current_holder_level='village'`.
- The **only** path that reaches Tehsil…Earth is escalation, and at every one of those levels `is_council_member` (reused from `announcements_core`) is hard-coded to return `False` for non-village levels, so the escalated report's "holder council" is always Founder/Admin until those levels get real elected data. This is visible and intentional, not silent — the inbox query for a non-village level simply returns admin-only results.
- `current_holder_id` for an escalated level is the village's own *ancestor* id at that level (e.g. the village's tehsil id), read from the reporting user's own `present_location_json` chain at escalation time — not a separate "escalation target" lookup, since the location hierarchy is already fixed per-village.

## 3. SLA and escalation

- `sla_deadline = created_at + 10 days` at creation; reset to `now + 10 days` on every `escalate` (see §1); **not** reset on `needs_time` — that action's whole purpose is to set a deliberately-chosen custom deadline, so `new_deadline` (required for that update type) becomes the new `sla_deadline` directly, not a +10-day default.
- Response types stored verbatim as given: `acknowledged | needs_time | resolved | denied | escalated | comment`. `resolved`/`denied` also set `reports.status` and (`resolved` only) `resolved_at`; `escalated` sets `status='escalated'` and advances `current_holder_level`/`current_holder_id`; `acknowledged`/`comment` don't change `status` at all (status stays `open`/`in_progress`).
- **No bounce-back enforcement**: `escalate` validates the target level is strictly later in `LEVELS = (village, tehsil, district, state, zone, country, continent, earth)` than every level already recorded in `escalation_path` (plus the report's own starting `village`) — rejects (400) a level that isn't strictly forward. Since the only escalation trigger in this phase is "current holder escalates to the next level up" (no arbitrary level jump exposed in the API), this is mostly a defensive check, but it's cheap and makes the invariant explicit rather than merely "true because the UI only offers one button."

## 4. API surface

| Route | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `POST /api/reports` | Logged in, has a present-village | `{body, anonymous}` | `{id, sla_deadline}` | 400 empty body / no present-village |
| `GET /api/reports/<id>` | Owner, or council/admin of `current_holder_level`+`current_holder_id`, or admin | — | `{id, body, status, anonymous, author (masked unless owner/admin), current_holder_level, current_holder_id, sla_deadline, escalation_path, updates: [...]}` | 403 not owner/not holder; 404 unknown id |
| `GET /api/reports/mine` | Logged in | — | `{reports: [{id, status, current_holder_level, sla_deadline, last_update_at}]}` | — |
| `GET /api/reports/inbox?location_id=&location_level=` | Council/admin of that location | — | `{reports: [{id, body_preview, anonymous, created_at, sla_deadline}]}` — never masked here even if anonymous is false for the requester's own eyes, but **is** masked per §1 if anonymous | 403 not council/admin of that location |
| `POST /api/reports/<id>/update` | Council/admin of current holder | `{update_type, message?, new_deadline?}` | `{ok: true}` | 400 bad update_type / missing new_deadline for needs_time; 403 not holder; 404 |
| `POST /api/reports/<id>/escalate` | Council/admin of current holder | — (next level is computed server-side, not client-supplied — see §3) | `{current_holder_level, current_holder_id, sla_deadline}` | 400 already at `earth` (nothing above it); 403 not holder; 404 |

## 5. UI placement

- **Village Lok page**: a "Report" button next to the existing post composer (`.bd-compose`), opening a small choice popup ("Make a Post" / "Submit a Report") reusing the `.qm-confirm-backdrop` popup styling already established (Item 12's registration-exit popup). "Submit a Report" opens a `.dq-modal` with the textarea (2000 max), the anonymous checkbox, and Submit.
- **Private Account → "My Reports"**: a new `pv-card` (same family as the existing Wallet/Karma/Election-history cards) listing the user's own reports with status/holder/SLA countdown/last update; click opens the shared detail view modal.
- **Council inbox**: a new card inside the Lok panel's sidebar area (next to the Announcements card built in Item 8), visible only when `can_publish_announcement`-equivalent is true for that location (i.e. reusing the exact same council/admin check) — "📋 Report Inbox" with open reports assigned to that holder; click opens the detail view with the reply form (update_type dropdown, message, optional new deadline).
- **Report detail view**: one shared modal (not duplicated per surface) — timeline newest-first, "Anonymous Citizen" substitution per §1, reply form only rendered when the viewer is the current holder's council/admin.

## 6. Migration plan

- `migrations/013_reports.sql` — both `CREATE TABLE`s + 3 indexes, additive only.
- Rollback: `DROP TABLE report_updates; DROP TABLE reports;` (updates table first, FK order).

## 7. Verification plan

- Citizen submits a report on their village Lok page → sees a confirmation, and it appears under their own "My Reports."
- The village's current council head sees it in their inbox; a different village's council does not.
- Council responds with `acknowledged` then later `resolved` → owner's "My Reports" and the detail-view timeline both reflect it.
- `needs_time` requires and stores a `new_deadline`; `sla_deadline` updates to that exact value.
- Escalate → `current_holder_level` moves to `tehsil`, a system-authored `escalated` update is appended, `sla_deadline` resets to a fresh 10 days, and the (currently admin-only) Tehsil inbox shows it.
- Attempting to "escalate" again from `earth` is rejected (400 — nothing above Earth).
- Anonymous report: council/holder view shows "Anonymous Citizen"; the owner's own view and the admin view show the real name.
- A user who is not the owner and not the holder's council gets 403 on `GET /api/reports/<id>`.

---
**Open items for your OK before I build** (mirroring the pattern from Announcements): (1) escalation resets the SLA clock to a fresh 10 days — confirm vs. "the original 10-day deadline just keeps ticking down regardless of who holds it"; (2) anonymous masks identity from council/holder too (not merely some other "public" audience that doesn't see reports at all), with Admin as the one exception; (3) the Tehsil→Earth admin-only fallback is the same approved gap as Announcements, just re-confirming it applies here identically.
