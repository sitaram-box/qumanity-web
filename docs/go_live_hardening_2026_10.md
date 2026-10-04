# Production hardening + Railway deploy prep (2026-10-05)

Next go-live step after Karma (`docs/karma_finalization_2026_10.md`) and Qoins payment
(`docs/qoins_payment_2026_10.md`). The Founder is separately learning how to switch Razorpay to
test mode and generate test keys — this pass doesn't touch Razorpay credentials; it prepares
everything needed to actually deploy to Railway once the Founder is ready, using GitHub + Railway
as the deployment path they named.

## What changed

- **`app.secret_key`**: refuses to boot with the insecure placeholder default
  (`"dev-insecure-secret-change-me"`) when `RAILWAY_ENVIRONMENT` is set (Railway always sets this
  on every deploy) — forces a real `QM_SECRET_KEY` to be configured before the app can ever run in
  that environment, rather than silently shipping sessions signed with a key anyone can read in
  this file.
- **The daily DB→folder export scheduler** (`_start_scheduler()`) used to only run inside
  `if __name__ == "__main__":` — meaning it would never fire at all under a production WSGI server
  like gunicorn (gunicorn imports the `app` module directly; it never executes that block). Moved
  to run unconditionally at import time instead.
- **`db.py`'s `DB_PATH`** is now configurable via `QM_DB_PATH` — unset, it behaves exactly as
  before (a file next to the repo, for local dev); set, it points the SQLite file at wherever a
  Railway Volume is mounted, so the database survives redeploys instead of being wiped (Railway's
  container filesystem is otherwise ephemeral).
- **`Procfile`** (new) + `gunicorn` added to `requirements.txt`: `web: gunicorn --workers 1 --bind
  0.0.0.0:$PORT app:app`.

## Why exactly 1 worker — not Railway's default

As long as this app stays on SQLite with an in-process APScheduler (both true for this launch, per
the Founder's own 2026-10-04 "stay on SQLite, migrate later" decision), running more than one
gunicorn worker would (a) register the midnight export job once per worker, running it N times
instead of once, and (b) let multiple processes write the same SQLite file concurrently, which
SQLite doesn't handle well under write contention. Single-worker is the correct choice for this
architecture, not a placeholder to revisit casually — revisit it only alongside an eventual
Postgres migration.

## What Railway needs set, before the first deploy

| Variable | Required? | Purpose |
|---|---|---|
| `QM_SECRET_KEY` | **Yes, or the app refuses to boot** | Flask session signing key — generate a real random secret, never reuse the placeholder. |
| `QM_DB_PATH` | Yes, for data to survive redeploys | Point this at a path inside a Railway **Volume** (e.g. `/data/qumanity_prototype.db`) — without a Volume, every redeploy wipes the database. |
| `QM_EARTH_ROOT` | Yes, for the 0_Earth folder-tree feature to keep working | Point this at a path inside the SAME (or another) Railway Volume, pre-populated with the current `0_Earth` tree (all 10 countries, `Qumanity_Master.json`, every registered user's folder) — without it, the app still runs, but every folder-tree write silently no-ops (soft-fails by design, per `folder_connector.py`), so no new user ever gets a `BORN_HERE`/`LIVING_HERE` folder. This is the single easiest thing to forget before a real launch. |
| `QM_ADMIN_PRIVATE_IDS` | Yes, to use any `/api/admin/*` route (visibility overrides, election-cycle config) | Comma-separated list of Private IDs allowed admin access — currently unset even in local dev. |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Not yet — the Founder is still setting these up | Until set, donations fall back to the simulated instant-credit path (see `docs/qoins_payment_2026_10.md`) — safe default, but real money won't move until these are set. |
| `PORT` | No — Railway sets this automatically | Already read by both the Procfile and `app.py`'s own fallback. |
| `QM_HOST` / `QM_DEBUG` / `QM_TEST_PIN` / `QM_DEV_SHOW_OTP` | No — leave unset | Dev-only conveniences; their defaults are already safe in a production environment (`QM_DEBUG` auto-disables off-localhost; the others default to disabled). |

## Explicitly not done in this pass

- **No Postgres migration** — per the Founder's own decision, this launch stays on SQLite.
- **No Razorpay live/test keys set or touched** — the Founder is doing this themselves.
- **No actual Railway project created, no domain DNS touched** — those need the Founder's own
  Railway/registrar accounts; this pass only prepares the application-level code and config so
  that work, once started, has everything it needs.
