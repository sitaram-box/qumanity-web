# Rollback plan — Phase 3-5 deployment (2026-10-05)

Three independent rollback paths, matched to failure type. They can be combined (e.g. A + C) if
a problem spans both code and runtime behavior.

## Rollback A: revert the code

**When to use**: the new code itself is misbehaving (a route 500s, a migration logic error, the
scheduler firing wrong) and reverting is faster than a forward-fix.

```bash
cd ~/Desktop/Qumanity_DPG
git revert HEAD
git push
```
Railway auto-redeploys the reverted commit. Note: this reverts the *code*, not the DB schema —
migrations 001-011 will already have been applied and are NOT rolled back automatically (they're
additive; leaving the new columns/tables in place after a code revert is harmless, since the
reverted code simply doesn't reference them).

## Rollback B: restore the DB from backup

**When to use**: the live DB itself is in a bad state (corrupted, wrong data uploaded, a migration
somehow damaged something) and needs to be replaced wholesale.

```bash
railway volume files --volume web-volume upload ./<your-backup>.db /data/qumanity_prototype.db --overwrite
railway redeploy --yes
```
The redeploy after upload is required — see "A note on the DB-swap timing bug" below; the running
process needs a fresh boot to re-sync its one-time initialization (bootstrap row, etc.) against
whichever file now sits on disk.

**Known-good backup points as of this deployment**: none yet exist from the LIVE service, because
the volume was completely empty (0MB) before this deploy — there was no prior production data to
back up. The first real backup opportunity is whenever you choose to take one going forward (e.g.
before the Year 2 pipeline activation in April 2027): `railway volume files --volume web-volume
download /data/qumanity_prototype.db ./backup_<label>.db`.

## Rollback C: disable the scheduler only (code stays deployed)

**When to use**: the code is fine, but you want the automation (cron tick) to stop firing without
reverting anything — e.g. to investigate a suspicious log line, or before a planned maintenance
window.

In the Railway dashboard (Variables tab for the `web` service): add `QM_DISABLE_SCHEDULER=1`,
then redeploy (or it takes effect on the next natural redeploy). This skips
`pipeline_scheduler.init_scheduler()` entirely — no cron job gets registered, but every route,
including the manual `POST /api/admin/pipeline/tick` endpoint, keeps working normally. Remove the
variable (or set it to empty) and redeploy again to re-enable.

## A note on the DB-swap timing bug (encountered during this deployment)

If you ever upload a new DB file directly (`railway volume files upload`) to an already-running
service, the row `ensure_database_ready()`/`pipeline_scheduler.init_bootstrap()` creates at boot
targets the file that existed *at that boot*, not whatever file is on disk afterward. Swapping
the file underneath a running process leaves tables that depend on a one-time INSERT (currently
just `pipeline_bootstrap`) empty until the next real boot. **Always follow a volume file upload
with `railway redeploy --yes`** so the app's own startup sequence re-runs cleanly against the
file that's actually there. This happened once already, during this deployment, and was fixed
exactly this way.

## What NOT to do

- Do not run `UPDATE`/`DELETE`/ad-hoc write scripts against the live DB over `railway ssh` as a
  "quick fix" — if the app's own code can create the needed state (migrations, `init_bootstrap`,
  seed scripts), prefer triggering that through a redeploy or the admin API instead of hand-editing
  production data directly.
- Do not set `QM_DISABLE_SCHEDULER` as a way to "pause" real pipeline activity once Year 2 is
  live and cycles are mid-transfer — a transfer that's already started (`transfer_log` status
  `in_progress`) should be allowed to finish; disabling the scheduler only stops *new* daily ticks
  from firing, it doesn't pause an in-flight one.
