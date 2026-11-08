# Environment variables

One row per variable Qumanity reads. Copy `.env.example` to `.env` and fill in real values;
`.env` itself is gitignored and must never be committed.

| Variable | Purpose | Default (if unset) | Required in production |
|---|---|---|---|
| `QM_SECRET_KEY` | Flask session-signing secret. | An insecure placeholder string ([app.py](../app.py)); the app refuses to boot on Railway with this placeholder. | **Yes** |
| `QM_DB_PATH` | Path to the SQLite database file. | `qumanity_prototype.db` next to `app.py`. | No (recommended — point at a persistent volume) |
| `QM_EARTH_ROOT` | Root of the real-world location folder tree (`Continents/...`), written to at registration and read for the Admin gate's reference material. | `./0_Earth` next to the relevant module. | No (recommended) |
| `MASTER_JSON_PATH` | Path to `Qumanity_Master.json`, the authoritative India location hierarchy. Not shipped in the repo (~115MB) — see "Sample data" in [INSTALL.md](INSTALL.md). | Falls back to `/data/Qumanity_Master.json`, then a repo-relative path, then `~/Desktop/0_Earth/Qumanity_Master.json`. | **Yes** (location import fails without it) |
| `QM_HOST` | Interface Flask binds to when run directly (`python app.py`); `0.0.0.0` lets other devices on the same network (e.g. the phone app) reach it. | `127.0.0.1` | No (a production WSGI server like gunicorn ignores this) |
| `PORT` | Port Flask binds to when run directly. | `5050` | No |
| `QM_DEBUG` | Enables Flask's debugger/reloader. | `1` if `QM_HOST` is `127.0.0.1`/`localhost`, else `0`. | **Yes — must be unset/`0` in production** |
| `QM_DISABLE_SCHEDULER` | Skips registering the daily lunar-pipeline cron tick on import (used by test/verification scripts to avoid double-registration or unwanted background jobs). | Not set (scheduler runs). | No |
| `QM_ADMIN_PRIVATE_IDS` | Comma-separated list of 9-digit Private IDs treated as admin by `_is_admin()`. No `role` column exists; this env var is the entire admin system. | Empty (no admin access). | **Yes** |
| `QM_ADMIN_EMAIL` | Destination address for the registration-notification email (`email_core.py`, 2026-10-18) — see [EMAIL.md](EMAIL.md). Paired with `RESEND_API_KEY` below, which describes *how* to send; this is *who* receives. | Not set (no email is sent — see `RESEND_API_KEY` below). | No |
| `RESEND_API_KEY` / `RESEND_FROM_EMAIL` | Resend HTTPS API credentials for the registration-notification and AI-Support-ticket-reply emails. **Corrected 2026-11-08** — this row previously named `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM_ADDR`, which described an implementation the code was switched away from on 2026-10-20 and no longer reads at all (confirmed by grep: zero matches for any `SMTP_*` name or `smtplib` outside this stale doc history). See [EMAIL.md](EMAIL.md) for the full picture, including why a deployment configured from the old version of this row would silently never send. | `RESEND_API_KEY` empty = notifications off entirely (deliberate no-op, registration never depends on this). `RESEND_FROM_EMAIL` defaults to `"Qumanity <founder@qumanity.in>"`. | No |
| `QM_FOUNDER_PIN` | Only read by the retired one-off script `scripts/_retired/migrate_private_codes.py`; not used by the live app. | Not set. | No |
| `QM_TEST_PIN` | Pre-fills a PIN field on a dev-only helper-registration template. | Empty string. | No |
| `QM_DEV_SHOW_OTP` | Returns the simulated OTP code directly in the API response instead of only printing it to the console. Dev convenience until a real SMS/email provider exists. | Not set (OTP only printed server-side). | **No — must stay unset in production** |
| `QM_MARQUEE_ENABLED` | **Removed 2026-11-08** — the Poems Marquee feature itself was discontinued (owner legal decision, Gita Press denied permission for the Hindi Vinaya Patrika translation) and this flag no longer exists in the code. If still set on Railway, it has no effect and should be removed from that service's Variables. | N/A | N/A |
