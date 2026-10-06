# Announcements system — design note (Item 8)

## 1. Data model

Schema as given, additive only:

```sql
CREATE TABLE announcements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id TEXT NOT NULL,
  location_level TEXT NOT NULL,   -- village|tehsil|district|state|zone|country|continent|earth
  author_user_id TEXT NOT NULL,
  title TEXT,
  body TEXT NOT NULL,
  image_url TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active INTEGER DEFAULT 1
);
CREATE INDEX idx_ann_location ON announcements(location_id, created_at DESC);

CREATE TABLE announcement_reads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  announcement_id INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(announcement_id, user_id),
  FOREIGN KEY (announcement_id) REFERENCES announcements(id)
);
```

**One correction**: `location_level` must include `earth`, not just the 7 India-only sub-levels — `board_core.py`'s own `LEVELS` constant is the 8-level `village…earth` list, and Global-tab announcements (Earth/Continent/Country) are in scope per the location pages they attach to. Recommend the comment read `village|tehsil|district|state|zone|country|continent|earth`.

- **`image_url` is TEXT**: matches the codebase's existing pattern everywhere else an image is referenced (e.g. profile avatars) — images live on disk/object storage (or an external URL), never as a DB blob. No new upload endpoint in this phase; B5's "optional image URL" is a plain paste-a-link field, not a file upload.
- **`is_active` needed now**: yes — it's the only soft-delete/retract mechanism a council member has if they publish something wrong. Cheap column, used from day one (`WHERE is_active = 1` on every read query).
- **No denormalized columns needed yet**: `author_user_id` → `users.name`/role is a cheap `LEFT JOIN` at read time (same pattern `election_core.council_roster()` already uses for head names) given the expected volume (dozens, not thousands, of announcements per location). Revisit only if a location's announcement list ever gets slow in practice.
- **Not stamping `cycle_id`**: unlike the 28 tables Phase 2 stamped, announcements are not pipeline/lunar-archived content — they're moderator-authored, not user activity — so no `cycle_id` column, consistent with Phase 2's own exclusion of role/config-type tables.

## 2. API surface

| Route | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `POST /api/announcements` | Council member of `location_id` (`location_level`), or admin | `{location_id, location_level, title?, body, image_url?}` | `{id, created_at}` | 400 empty body; 403 not council/admin; 404 unknown location |
| `GET /api/announcements/<level>/<id>?limit=20` | Any logged-in user | — | `{announcements: [{id, title, body, image_url, author_name, created_at, is_read}]}` | 404 bad level |
| `POST /api/announcements/<id>/read` | Any logged-in user | — | `{ok: true}` (idempotent — `INSERT OR IGNORE`) | 404 unknown id |
| `GET /api/announcements/unread-count` | Any logged-in user | — | `{total: N}` | — |

`unread-count` scope = the user's own location lineage only (their birth/present chain at every level — same set `board.js` already walks for the Global/Public tabs), not every location on Earth.

## 3. Council member check

```python
# announcements_core.py
def is_council_member(conn, user_id, location_id, location_level) -> bool:
    if location_level != "village":
        return False   # no elected council model exists above village yet
    today = dt.date.today().isoformat()
    row = conn.execute(
        """SELECT 1 FROM village_council
           WHERE village_id = ? AND leadership_start <= ? AND leadership_end >= ?
             AND (male_head_user_id = ? OR female_head_user_id = ?)""",
        (location_id, today, today, str(user_id), str(user_id)),
    ).fetchone()
    return row is not None
```

Route-level gate is `_is_admin() or announcements_core.is_council_member(...)` — same OR-pattern `app.py` already uses elsewhere (e.g. `board_core.send_message(..., _is_admin())`), not folded into the helper itself, since `_is_admin()` reads the Flask session and belongs in `app.py`, not a `*_core` module.

**Note, not a question** (matches your own fallback rule in C5, applied here too): the real table is `village_council` (Phase 2's report already noted "`council_members`" is this project's plain-English name for it, not a literal table) and it **only exists at village level** — one male head + one female head per village per zodiac-month term, confirmed in `election_core.py`. For every other level (tehsil…earth), there is no elected-council data at all, so `is_council_member` always returns `False` there and publishing falls back to Founder/Admin-only, exactly as your own instruction anticipates. This is a real current gap, not an oversight of this design — flagging it so it's a known, accepted scope boundary rather than a silent one.

## 4. UI placement

- **(a) Right sidebar** — new `.qm-dash-card` titled "📢 Announcements" placed in the existing right-column stats area next to the open location's panel, latest 5 via `GET /api/announcements/<level>/<id>?limit=5`; "View all" opens a `.dq-modal` (the existing generic modal plumbing from `dash_extras.js` — no new dismiss wiring needed) listing the full `limit=20`.
- **(b) Pinned banner in the `[Level] Lok` panel** — a new one-line strip inserted in `board.js`'s `render(v)`, directly under the `v.group + " Lok"` title (added in Item 7) and above the post list. Rotates through active announcements every 5s via `setInterval`; click expands in place (toggles a class, no modal).
- **(c) Notification icon** — **cannot reuse the existing bell** (`#notif-btn`/`#notif-badge`): that icon is already wired (`dash_extras.js`) to unread Personal-timeline chats + people-requests, and clicking it jumps to the Personal tab, not a dropdown. Recommend a **second, new icon** next to it (same `.dq-dot.dq-dot-icon` chip styling, so it looks like a sibling control, not a bolt-on) — e.g. a 📢 megaphone glyph — with its own badge and dropdown, rather than overloading the existing bell's established behavior. Flagging this explicitly since the brief says "the notification icon" (singular); I think two small icons reads cleaner than one icon serving two unrelated concerns, but will build it either way per your call.
- **Council publish UI**: "+ New Announcement" button on the location page, visible only when `is_council_member || is_admin` (server already told the page this via the existing `v` payload pattern — one more boolean), opens a `.dq-modal` with title/body/image-url, `POST`s, then refreshes (a)/(b)/(c) in place.

## 5. Notification badge performance

Given current scale (hundreds of users, not millions), a live `COUNT(*) ... WHERE NOT IN announcement_reads` per page load is cheap — no caching layer needed yet. Recommend **skipping the 30s server cache for now** (adds a moving part — cache invalidation on two different write paths — for no measurable win at this volume) and revisiting only if the Phase-6-style load testing ever flags this endpoint. The client already polls every 30s itself (matching the existing `#notif-btn` pattern), which is the only "TTL" that actually matters here.

## 6. Migration plan

- `migrations/012_announcements.sql` — both `CREATE TABLE`s + the one index, additive only, zero changes to any existing table.
- Rollback: `DROP TABLE announcement_reads; DROP TABLE announcements;` (reads table first, FK order).

## 7. Verification plan

- Council member (village head) publishes → appears in sidebar, Lok banner, and (via a second test user's session) the new notification icon.
- Non-council villager → no "+ New Announcement" button; can still read all three surfaces.
- Admin/Founder → can publish at any location regardless of council.
- Read status: mark-as-read in the dropdown persists across reload (per-user, not per-browser).
- Unread count: 0 → N after a new announcement; back to 0 after reading all.
- Mobile (375px): sidebar card stacks, Lok banner doesn't overflow, dropdown doesn't clip off-screen.
- Empty state: "No announcements yet" placeholder in sidebar card, banner hidden entirely (not an empty strip) when there are zero active announcements.

---
**Open items for your OK before I build**: (1) the two-icon vs. one-icon notification approach in §4c, (2) including `earth` in `location_level`, (3) no caching on unread-count per §5.
