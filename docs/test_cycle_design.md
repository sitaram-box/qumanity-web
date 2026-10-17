# Test Cycle Design — the Post Testing feature (2026-10-17)

Reference design for a one-year, automated demo-user testing cycle that exercises the
Collective Board's post → vote → reward → freeze/elevate → recognition-star path end to end.
**This document is a design reference, not yet implemented.** Nothing described here has been
written to code; it is the basis for a future implementation pass once approved.

---

## 1. Purpose

The Board's reward machinery — rank-based rewards, cumulative multi-level rewards, recognition
stars, the freeze/elevate/remove decision — has only been exercised by hand-written unit
scenarios (A–G, H1–H9) so far, never by a sustained population of posts and votes over time. The
Post Testing cycle's purpose is to run that machinery automatically, for a year, against a
population of posts diverse enough to exercise every outcome:

- Posts that freeze at Village without elevating
- Posts that elevate once, twice, or climb several levels
- Posts that accumulate a reward at each level they clear (the cumulative-reward path)
- Posts that earn a recognition star
- Posts that are removed (negative score → penalty karma) or frozen at zero
- Posts ranked at every position in a cohort — top-tier, middle, bottom

The **skewed vote distribution** (Decision 1, §2) exists to *manufacture that diversity*, not to
simulate how real members would actually vote. A symmetric, zero-mean distribution (uniform
±1/0) would leave almost every post stuck at Village — verified numerically: with 50 voters and a
uniform distribution, only ~5% of posts clear Village's threshold of 10. A skewed distribution
(`+1: 0.5, 0: 0.3, −1: 0.2`, mean +0.3/voter, mean score +15 at 50 voters) produces a realistic
*mix* — most posts clear Village, some climb further, a few don't — which is what the test
actually needs to cover the machinery, not a claim about how Qumanity's real members vote.

---

## 2. The `testing_windows` table

A testing window is **feature-scoped**, not global. The demo-user pool is a shared resource used
by any number of concurrent features; the constraint "only one active window" applies *within* a
feature, never across features.

```sql
CREATE TABLE IF NOT EXISTS testing_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature TEXT NOT NULL,              -- 'post_testing' | 'election_test' | 'wallet_test' | 'karma_test' | ...
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',   -- active | expired | stopped
    demo_user_count INTEGER NOT NULL,
    vote_distribution TEXT NOT NULL,    -- JSON, see below
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_testing_windows_feature_status ON testing_windows(feature, status);
```

**`vote_distribution` JSON format**: `{"+1": 0.5, "0": 0.3, "-1": 0.2}` — three keys, values
summing to 1.0. Stored as JSON (not three separate columns) specifically so it's editable by the
Admin panel without a schema change or redeploy — e.g. switching to a different mix mid-year to
test a different outcome profile.

**`status` values and transitions**:
- `active` — the only status the scheduler acts on. Set at creation, and by "Renew."
- `expired` — set when `end_date` has passed and nothing renewed it. The scheduler checks
  `end_date` on every run and flips `active → expired` itself before deciding whether to act,
  rather than relying on a separate job to notice the expiry.
- `stopped` — set only by the Admin's "Stop testing now" button. Terminal, like `expired`, but
  distinguishes "the year ran out" from "the Admin ended it early" for the panel's own display
  and for any future audit of what happened.
- There is no transition back to `active` from `expired`/`stopped` — "Renew" only works on a row
  that is still `active` (extends `end_date` by 365 days in place); once a window has gone
  `expired` or `stopped`, the only path forward is "Start a new test period," which inserts a
  **new row**, never resurrects the old one.

**The "one active per feature" rule**: enforced as
`SELECT 1 FROM testing_windows WHERE feature = ? AND status = 'active'` before allowing a new
`active` row for that same `feature` to be created — checked in application code (the route that
creates a window), not as a SQL `UNIQUE` constraint, since SQLite can't express "unique among rows
matching a condition" as cleanly as a plain application check here, and the check needs a clear
error message back to the Admin regardless.

**Features today and planned**: only `'post_testing'` is being implemented now. `'election_test'`,
`'wallet_test'`, `'karma_test'` are named here as the anticipated next features, each getting its
own scheduler module and its own `feature` key when built — this table and its rule are designed
to support them without any change to this schema when that happens.

---

## 3. The two flags on `board_posts`

```sql
ALTER TABLE board_posts ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0;
ALTER TABLE board_posts ADD COLUMN is_demo_post INTEGER NOT NULL DEFAULT 0;
```

| `is_test` | `is_demo_post` | Meaning | Badge |
|---|---|---|---|
| 0 | 0 | An ordinary real post | *(no badge)* |
| 1 | 0 | A real post the Admin explicitly tagged as a test | **"Admin · Test"** |
| 1 | 1 | A post the scheduler generated from a demo user | **"Demo · Test"** |
| 0 | 1 | **Invalid** — a demo-authored post is always a test | — |

The `0/1` combination is never written by any code path: the scheduler sets `is_test=1` and
`is_demo_post=1` together, in the same statement, whenever it creates a demo post (§5) — there is
no code path that sets one without the other. This is enforced by construction (one write site),
not by a database `CHECK` constraint; if a second write path to `is_demo_post` is ever added later,
a `CHECK (is_demo_post = 0 OR is_test = 1)` constraint would be the place to add real enforcement,
but isn't needed while the invariant is maintained by having exactly one writer.

---

## 4. `board_votes.voted_at` — **one correction to the original spec, verified empirically**

The original spec called for:
```sql
ALTER TABLE board_votes ADD COLUMN voted_at TEXT NOT NULL DEFAULT (datetime('now'));
```
**This fails.** I tested it directly against this project's SQLite (3.50.4):
```
sqlite3.OperationalError: Cannot add a column with non-constant default
```
SQLite's `ALTER TABLE ADD COLUMN` only accepts a literal constant as a default — not a function
call like `datetime('now')`, and (also tested) not even the `CURRENT_TIMESTAMP` keyword once a
`NOT NULL` constraint is attached, on this version. This isn't a workaround-able syntax issue —
it's a hard restriction on `ALTER TABLE ADD COLUMN` specifically (a full table rebuild can do
anything; a lazy `ADD COLUMN` cannot).

It also wouldn't match this codebase's own convention anyway: every other timestamp column here
(`created_at`, `voting_start`, etc.) is set explicitly by **application code** computing
`dt.datetime.now(...).isoformat(...)` and passing it as a bound parameter on `INSERT` — never by
a SQL-level default. `voted_at` should follow the same pattern:

```sql
ALTER TABLE board_votes ADD COLUMN voted_at TEXT;   -- nullable at the schema level; see below
```
Then, in the same migration, a one-time backfill computed once in Python (mirroring exactly how
migration 015 backfills existing wallets — one `now` string computed once, reused for every row):
```python
now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
conn.execute("UPDATE board_votes SET voted_at = ? WHERE voted_at IS NULL", (now,))
```
Every **future** vote gets `voted_at` supplied explicitly by `cast_vote()`'s own `INSERT OR
REPLACE` statement (the same `_iso(now)` value `cast_vote()` already computes for `cycle_id` —
just added as one more bound column), so the column is NOT-NULL *in practice* from the moment this
migration runs, even though it can't carry a `NOT NULL` constraint at the schema level without a
full table rebuild (not worth doing for this).

### Why the default is applied by the application, not by SQL

SQLite's `ALTER TABLE ADD COLUMN` only accepts a constant as a default value — a function call
like `datetime('now')` is rejected outright (verified directly against this project's SQLite,
3.50.4), because `ADD COLUMN` is a lazy, metadata-only operation that never rewrites existing
rows, so SQLite has no mechanism to evaluate a non-constant expression once per existing row at
`ALTER` time. The application supplies the timestamp explicitly on every `INSERT` instead — the
same pattern every other timestamp column in this codebase already uses (`created_at`,
`voting_start`, `voting_end`, etc. are all set by Python code computing `dt.datetime.now(...)` and
passing it as a bound parameter, never by a SQL-level `DEFAULT`). The alternative — rewriting the
whole `board_votes` table under a new schema just to attach a constant or computed default — is
the kind of unnecessary risk this project avoids for a one-column, timestamp-only change; a lazy
`ADD COLUMN` plus an explicit backfill achieves the identical end state with no risk to existing
data.

**Purpose confirmed**: this is exactly what the top-up logic (§5) needs — "has this demo user
already voted on this post" — and the backfill's single shared timestamp correctly marks every
*pre-existing* vote as "from before this feature existed," which is accurate: every row in
`board_votes` today is from a real user (confirmed by the earlier audit — zero votes currently
exist from the 500 is_demo=1 users), so none of them should ever be mistaken for a demo top-up
vote. The top-up check only ever looks at *rows written after this migration*, by construction —
it doesn't need to distinguish by timestamp at all, only by whether a `(post_id, user_id)` pair
exists at all for a given demo user.

---

## 5. The `test_cycle_scheduler` module

Mirrors `pipeline_scheduler.py`'s structure: its own `SCHEMA` (the `testing_windows` table goes
here, not in `board_core.py`, since it's test-cycle infrastructure, not a board concept), its own
guarded startup registration, kept entirely separate from the lunar pipeline and the existing
midnight sync job so the whole feature stays independently removable.

```python
# test_cycle_scheduler.py (sketch — not implemented)

def init_scheduler():
    """Registers the two cron jobs on their own BackgroundScheduler instance. Guarded the same
    way pipeline_scheduler.py and app.py's own _start_scheduler() already are, against Flask's
    debug-mode reloader double-exec (WERKZEUG_RUN_MAIN) -- safe only because this deploy runs a
    single gunicorn worker (Procfile: --workers 1); more workers would register this job once per
    worker."""
    ...
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(monthly_post_job, "cron", day=1, hour=6, minute=0)
    scheduler.add_job(weekly_vote_job, "cron", day_of_week="mon", hour=6, minute=0)
    scheduler.start()
```

Called once from `app.py`, alongside the existing `pipeline_scheduler.init_scheduler()` call.

**`monthly_post_job()`** — 1st of the month:
1. `window = active window WHERE feature='post_testing'` (flip `active→expired` first if
   `end_date` has passed). If none, exit — no window, no posts.
2. For each `is_demo=1 AND is_removed=0` user: skip if they already have an
   `is_demo_post=1` post with `created_at` in the current calendar month. Otherwise, call the
   **existing** `board_core.create_post()` exactly as a real resident would (content is a
   plainly-labelled placeholder, e.g. `"Test post from Demo Voter 7 — Qumanity board-testing
   cycle, 2027-03."` — clearly marked, not an attempt at realistic civic content), then
   `UPDATE board_posts SET is_test=1, is_demo_post=1 WHERE id=?`.

**`weekly_vote_job()`** — every Monday:
1. Same window check as above.
2. For every post where `is_test=1 AND status='active'`: for every `is_demo=1 AND is_removed=0`
   user, skip if `EXISTS (SELECT 1 FROM board_votes WHERE post_id=? AND user_id=?)` (the top-up
   check — Decision 2: a demo user votes on a given post **exactly once**, ever; a second weekly
   round only picks up voters who haven't voted that post yet). Otherwise, draw a value from
   `window.vote_distribution` and call the **existing** `board_core.cast_vote()`.
3. By the third weekly round after a post opens, every eligible demo voter has voted on it once;
   further rounds are no-ops for that post (exactly as specified) — the loop naturally converges
   without any extra "is this post done" bookkeeping, since the `EXISTS` check already makes every
   subsequent round cheap once everyone's voted.

**Idempotency, stated precisely**:
- Monthly: idempotent per `(demo_user, calendar_month)` — re-running the same day, or even
  re-running after the month has already produced one post per demo user, creates nothing new.
- Weekly: idempotent per `(demo_user, post)` — re-running the same week, or any later week after
  a demo user has already voted a given post, changes nothing for that pair.

Neither job needs a separate "did I already run this period" log table — both idempotency checks
query data that already exists for an entirely different reason (the posts/votes themselves),
exactly the same principle used throughout this task's earlier `is_demo`/`name LIKE` scoping.

---

## 6. The Admin tagging UI

Unchanged from the single-test-post design already approved earlier in this task: the icon/
checkbox on the compose form renders only when `v.is_admin` is true (the same `is_admin` key
already threaded into `api_board()`'s view dict); clicking it sends `is_test: true` on submission;
the server-side gate is the same one line already approved:
```python
is_test = _is_admin() and bool(data.get("is_test"))
```
**`is_demo_post` is never settable through this UI, or through any user-facing route at all** — it
is written *only* by `monthly_post_job()`, directly via SQL, never passed through
`board_core.create_post()`'s normal parameters. There is no client-facing concept of "post as the
demo pool" for a real user or even the Admin to trigger manually — only the scheduler does that,
which is exactly what keeps the "is_demo_post implies is_test" invariant (§3) true by construction.

---

## 7. Visibility enforcement — one query, confirmed

The existing post-listing query in `board_view()` ([board_core.py:317-322](../board_core.py:317))
gets one additional `AND` clause:
```sql
SELECT p.*, u.name AS author_name, v.value AS my_vote FROM board_posts p
JOIN users u ON u.id = p.author_id
LEFT JOIN board_votes v ON v.post_id = p.id AND v.user_id = ?
WHERE p.group_id = ? AND p.level = ? AND p.status != 'removed'
  AND (p.is_test = 0 OR p.status != 'active' OR ? = 1 OR ? = 1)
ORDER BY p.created_at DESC, p.id DESC LIMIT 100
```
bound to `(user_id, group_id, level, is_admin, is_demo_viewer)`. Read as: *show this post unless
it's an active test post and the viewer is neither the Admin nor a demo user.*

- **`is_admin`**: already available wherever `board_view()` is called from — threaded in exactly
  like the existing `can_publish_announcement`/`can_view_report_inbox` pattern in `app.py`'s
  `api_board()`.
- **`is_demo_viewer`**: one cheap additional lookup *inside* `board_view()` itself —
  `SELECT is_demo FROM users WHERE id = ?` against the `user_id` parameter `board_view()` already
  has. No new parameter needs to travel through the route layer for this one; it's derived locally
  from data `board_core.py` already holds.

Once a test post's `status` changes to `frozen`/`elevated`, the `p.status != 'active'` clause
alone makes it visible to everyone — no viewer-specific condition needed at that point, which is
exactly the two-stage visibility rule (hidden while active, visible once settled) expressed as a
single `OR` chain rather than two separate queries.

---

## 8. The Admin panel

A small admin-only section in the dashboard (parallel to the existing "Mark as test" checkbox's
own `v.is_admin`-gated rendering — same principle, different part of the page), showing:

```
Testing window: 2026-10-17 → 2027-10-17
Status: active
Demo users: 50
Vote distribution: 50% +1, 30% 0, 20% -1
Posts created this month: 47
Votes cast this month: 2,350
```
with buttons that depend on `status`:
- **`active`**: `[Renew for another year]` (extends `end_date` by 365 days in place),
  `[Stop testing now]` (sets `status='stopped'`)
- **`expired` or `stopped`**: `[Start a new test period]` (inserts a fresh row; per Decision 3,
  this is the *only* way to get a new active window once the current one has ended — there is no
  direct "restart" that skips the stop step while one is still `active`)

"Posts created this month" / "Votes cast this month" are both simple counts
(`is_demo_post=1 AND created_at >= <month start>`, `voted_at >= <month start> AND user_id IN
(demo ids)`), not stored anywhere separately — the panel computes them fresh on each view, same
principle as every other count in this design.

---

## 9. The seed script change

`scripts/seed_demo_voters.py`'s `DEFAULT_N` changes from `20` to `50` (the script itself, proposed
earlier in this task, has not yet been written to disk — this is a change to that still-pending
proposal, not a diff against an existing file).

After seeding, the script additionally creates the `testing_windows` row:
```python
conn.execute(
    """INSERT INTO testing_windows (feature, start_date, end_date, status, demo_user_count,
                                     vote_distribution, created_at)
       VALUES ('post_testing', ?, ?, 'active', ?, ?, ?)""",
    (now_iso, (now + 365 days), len(made), '{"+1": 0.5, "0": 0.3, "-1": 0.2}', now_iso),
)
```
guarded the same way everything else in that script is — skipped if an `active` `post_testing`
window already exists (consistent with the "one active per feature" rule), with a clear printed
message either way, so re-running the seed script never silently creates a second window.

The script's final printed summary gains one line reporting what happened to the window (created,
or "already active, left alone") alongside the existing demo-voter list.

---

## 10. Stop vs. retire — independent, by design

| Action | Table/column touched | Effect |
|---|---|---|
| Stop a testing window | `testing_windows.status = 'stopped'` | The scheduler's jobs exit immediately on their next run (no active `post_testing` row). Demo users are untouched — still `is_removed=0`, can still sign in, still have all their board history. |
| Retire demo users | `users.is_removed = 1` (via `scripts/retire_demo_voters.py`) | Those users can no longer sign in and are excluded from member counts. `testing_windows` is untouched — a window can remain `active` with no eligible voters left, which simply means `weekly_vote_job()`'s voter loop (§11) finds nobody to vote and does nothing, silently, every week, until the Admin notices and stops the window themselves. |

No code path updates both in one step. This is intentional — the Admin may want to end the
*testing activity* while keeping the accounts around a while longer (e.g. to inspect their
history), or retire the *accounts* while a window technically stays open (harmless but pointless,
per the row above).

---

## 11. The scheduler's voter query

Every place `test_cycle_scheduler.py` selects "which demo users vote/post right now":
```sql
SELECT id FROM users WHERE is_demo = 1 AND is_removed = 0
```
— never `is_demo = 1` alone. The Admin's own id is never in this set (the Admin is never
`is_demo = 1`), so there's no exclusion logic to get wrong; it's absent by construction, matching
Decision/Q5's "Admin votes only if they choose to, through the normal UI."

If a demo user is retired (`is_removed=1`) while a window is still active, they simply drop out of
this `SELECT` on the scheduler's very next run — no code change needed, no cleanup of their past
activity. Every vote they already cast, every post they already authored, every reward and
recognition star already recorded for them stays exactly as it was (Decision 3 from the earlier
test-post design: retirement never touches `board_votes`, never touches anything historical).

---

## What this document does not cover

Per the task rules, this is a design reference only — no migration file, no scheduler module, no
UI changes, and no changes to `scripts/seed_demo_voters.py` have been written yet. The two
pending-but-unwritten scripts from the earlier round (`seed_demo_voters.py`,
`retire_demo_voters.py`) still need their own review before anything in this document builds on
top of them. This document also does not touch the quantum-qualities work or the DPG evidence
pack.
