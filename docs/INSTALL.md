# Installing Qumanity

This covers getting the website running locally and the one piece of data every
fresh clone is missing: `Qumanity_Master.json`, the India location hierarchy.

## Quick start

```bash
git clone https://github.com/sitaram-box/qumanity-web.git
cd qumanity-web
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

The app boots with an empty, schema-only SQLite database at `./qumanity_prototype.db`
(created automatically on first boot) and no India villages loaded yet — see
[Master.json](#qumanity_masterjson) below to fix that. Without it, every page loads
except the Village step of registration, whose dropdown will be empty (the app logs
`[boot] CRITICAL: india_villages table is empty` to make this obvious rather than
silently broken — see `docs/india_location_fix.md`).

## Environment variables

None of these are required to boot locally — every one has a safe, repo-relative
default for local development. Set them explicitly for a real deployment.

| Variable | Default (local) | Purpose |
|---|---|---|
| `QM_DB_PATH` | `./qumanity_prototype.db` | SQLite database file |
| `QM_EARTH_ROOT` | `./0_Earth` (next to `app.py`) | Root of the real geographic folder tree (`folder_connector.py`) |
| `MASTER_JSON_PATH` | tries `/data/`, repo root, then `~/Desktop/0_Earth/` | Path to `Qumanity_Master.json` — see below |
| `QM_SECRET_KEY` | an insecure dev default | Flask session signing key — **must** be set to deploy on Railway (the app refuses to boot there without it) |
| `QM_ADMIN_PRIVATE_IDS` | unset (no admin) | Comma-separated 9-digit Private IDs granted admin rights |

See [ENVIRONMENT.md](ENVIRONMENT.md) for the full list, including variables not needed for a
local boot.

## Becoming an admin

There's no `role` column or admin-signup flow — admin rights are entirely controlled by
`QM_ADMIN_PRIVATE_IDS`. To make your own local account an admin:

1. Register normally through the website and note your 9-digit Private ID.
2. Set `QM_ADMIN_PRIVATE_IDS=<your 9-digit id>` (comma-separate for more than one admin) and
   restart the app.
3. Confirm with `GET /api/admin/pipeline/health` (or any other `/api/admin/*` route) while
   signed in as that account — it should return data instead of 403.

**`tools/seed_admin_only.py` is not a general admin-setup path.** It only copies one specific,
already-existing account (name, zodiac, wallet, etc.) out of a source database into a fresh one —
useful for building a minimal deploy DB that boots with a working admin account, not for turning
an arbitrary account into an admin. Use the `QM_ADMIN_PRIVATE_IDS` steps above for that.

## Production settings

Beyond `QM_SECRET_KEY` (required) and `QM_ADMIN_PRIVATE_IDS`, a production deploy should also set:

- `QM_DEBUG=0` (or leave unset while `QM_HOST` isn't `127.0.0.1`/`localhost`) — the debugger/
  reloader must never run in production.
- `QM_DEV_SHOW_OTP` must stay **unset** — it leaks the OTP code in the API response, meant only
  for local testing without a real SMS/email provider.
- Run under a real WSGI server (e.g. `gunicorn app:app`), not `python3 app.py`'s dev server —
  `QM_HOST`/`PORT` only affect the dev server path.
- Point `QM_DB_PATH` at a persistent volume, not the container's ephemeral filesystem.
- See `scripts/deploy_data_to_railway.sh` for the Railway-specific sequence (uploading
  `Qumanity_Master.json` to the volume, then running the import inside the container).

## Verifying your setup

A few standalone scripts check specific subsystems against the live-configured DB
(`QM_DB_PATH` or its local default) without a test framework:

```bash
python3 tools/verify_lunar_calendar.py
python3 tools/verify_cycle_stamping.py
python3 tools/verify_scheduler.py
python3 tools/verify_archive_writer.py
python3 tools/verify_pipeline.py
```

Each prints `ALL CHECKS PASSED` or a specific failure; run them after any change touching the
lunar-cycle pipeline, cron scheduling, or archival system.

## Sample data

`Qumanity_Master.json` (the India location hierarchy) is **not in this repository** — see the
section below for why and how to get it. In short: supply it either via the `MASTER_JSON_PATH`
environment variable (pointing at the file wherever you've placed it) or by uploading it to
`/data/Qumanity_Master.json` on a server's persistent volume. Without it, the app still boots,
but the Village step of registration has an empty dropdown.

## Qumanity_Master.json

### What it is

The India location hierarchy — Zone → State → District → Tehsil → Village,
~635,000 villages — that both the registration wizard's location dropdowns and the
real on-disk folder tree (`QM_EARTH_ROOT`) are built from. It's the single source of
truth for India's administrative geography in this app (see
`docs/india_location_fix.md` for why that matters: an earlier version of this app
sourced village data from a *different*, incompatibly-numbered source and that
regressed registration — don't reintroduce a second source).

It's **not** in this repo. At ~115MB with no natural way to split it, it doesn't
belong in git history (GitHub itself warns past 50MB and hard-blocks past 100MB for a
single file) — it's distributed as a GitHub Release asset instead, which has no
practical size limit.

### Where to download it

**[Download from the latest Release](https://github.com/sitaram-box/qumanity-web/releases)**
— look for the asset named `Qumanity_Master.json` attached to the most recent release.

*(If no release with this asset exists yet: a maintainer needs to create one —
`gh release create data-v1 Qumanity_Master.json --title "Qumanity_Master.json v1" --notes "India location hierarchy, ~635K villages"`
— from a machine that has the current file.)*

### Where to place it

- **On a server (Railway or similar)**: upload it to the persistent volume at
  `/data/Qumanity_Master.json`. `scripts/deploy_data_to_railway.sh` automates this
  step (`railway volume files upload`) plus the import that follows.
- **On a workstation**: either drop it at `~/Desktop/0_Earth/Qumanity_Master.json`
  (the default search path) or anywhere else and point `MASTER_JSON_PATH` at it.

Then import it into the database (safe to re-run; it's a full replace from the same
source each time):

```bash
python3 scripts/import_india_villages.py --verify
```

`--verify` checks the import against `static/data/subcontinent_districts.json` and
prints `PASS`/`FAIL`. Use `--dry-run` first if you just want a count without writing
anything.

### How it's regenerated / where it comes from

`Qumanity_Master.json` is the maintained, authoritative file — it is **not**
regenerated from `SITAXML.xml` (that source is retired; see
`scripts/_retired/import_india_villages_SITAXML.py`, which refuses to run without an
explicit `--i-know-this-is-retired` flag precisely so it can't be reintroduced by
accident — the two sources number districts/tehsils incompatibly, which is exactly
what broke registration the one time this got mixed up). Both ultimately trace back to
Government of India administrative/census data; `Qumanity_Master.json` is simply the
single file this app has standardized on since `docs/india_location_fix.md`'s fix.

### Licence

Public domain — derived from Government of India administrative/census data, which
carries no copyright restriction on reuse. This is independent of this repository's
own licence (AGPL-3.0, see `LICENSE`), which covers the application code, not this
data file.
