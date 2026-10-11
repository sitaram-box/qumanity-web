#!/usr/bin/env bash
# deploy_data_to_railway.sh — one-command helper to seed production's India location data
# (Qumanity_Master.json -> the Railway volume -> scripts/import_india_villages.py --verify
# run inside the container). Fixes the "production shipped with an empty DB" incident -- see
# docs/india_location_fix.md's "Incident: 2026-10-11 Production DB Never Seeded" section.
#
# Safety: this script only uploads Qumanity_Master.json and runs the (idempotent, additive)
# village import + verify inside the container. It does not touch the DB schema, does not
# delete the existing qumanity_prototype.db.backup_20261011 on the volume, and does not run
# `git push`/`railway up`/any deploy command -- the code must already be deployed (the normal
# `git push origin main` -> Railway auto-deploy path) before this script is useful.
#
# Running this script twice is safe: the upload uses --overwrite (re-uploading the same file
# changes nothing), and the import DELETEs+re-INSERTs india_villages from the same source each
# time, so a second run reproduces the identical table rather than duplicating or corrupting it.
#
# Usage:
#   ./scripts/deploy_data_to_railway.sh
#
# Override the local Master.json path or the Railway volume name if yours differ from the
# defaults below:
#   MASTER_JSON_LOCAL=/some/other/path.json RAILWAY_VOLUME=my-volume ./scripts/deploy_data_to_railway.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

MASTER_JSON_LOCAL="${MASTER_JSON_LOCAL:-$HOME/Desktop/0_Earth/Qumanity_Master.json}"
RAILWAY_VOLUME="${RAILWAY_VOLUME:-web-volume}"
REMOTE_MASTER_JSON_PATH="${REMOTE_MASTER_JSON_PATH:-/data/Qumanity_Master.json}"

echo "=== Qumanity: seed production India location data on Railway ==="
echo

# --- 1. Verify Master.json exists locally -----------------------------------------------
if [ ! -f "$MASTER_JSON_LOCAL" ]; then
  echo "ERROR: Qumanity_Master.json not found at: $MASTER_JSON_LOCAL" >&2
  echo "Set MASTER_JSON_LOCAL to override the path, e.g.:" >&2
  echo "  MASTER_JSON_LOCAL=/path/to/Qumanity_Master.json $0" >&2
  exit 1
fi
MASTER_JSON_SIZE="$(du -h "$MASTER_JSON_LOCAL" | cut -f1)"
echo "[1/7] Found local Master.json ($MASTER_JSON_SIZE): $MASTER_JSON_LOCAL"

# --- 2. Verify the railway CLI is installed and logged in -------------------------------
if ! command -v railway >/dev/null 2>&1; then
  echo "ERROR: railway CLI not found on PATH. Install it first: https://docs.railway.app/guides/cli" >&2
  exit 1
fi
if ! railway whoami >/dev/null 2>&1; then
  echo "ERROR: Not logged in to Railway (railway whoami failed). Run: railway login" >&2
  exit 1
fi
echo "[2/7] Railway CLI installed and logged in: $(railway whoami 2>&1 | head -1)"

# --- 3. Verify this project is linked ----------------------------------------------------
if ! railway status >/dev/null 2>&1; then
  echo "ERROR: No Railway project linked in this directory. Run: railway link" >&2
  exit 1
fi
echo "[3/7] Railway project is linked: $(railway status 2>&1 | grep -m1 'Project:' || true)"

# --- 4. Verify the local DB has data (sanity check before we bother uploading) ----------
LOCAL_USER_COUNT="$(python3 -c "
import sqlite3
from pathlib import Path
db_path = Path('$REPO_ROOT') / 'qumanity_prototype.db'
if not db_path.exists():
    print(0)
else:
    conn = sqlite3.connect(db_path)
    try:
        print(conn.execute('SELECT COUNT(*) FROM users').fetchone()[0])
    except sqlite3.OperationalError:
        print(0)
    conn.close()
")"
if [ "$LOCAL_USER_COUNT" -le 0 ]; then
  echo "ERROR: Local DB has 0 users ($REPO_ROOT/qumanity_prototype.db). Nothing to seed from." >&2
  exit 1
fi
echo "[4/7] Local DB looks real: $LOCAL_USER_COUNT user(s)."

# --- 5. Upload Master.json to the Railway volume -----------------------------------------
echo "[5/7] Uploading Master.json to the Railway volume ($RAILWAY_VOLUME:$REMOTE_MASTER_JSON_PATH) -- this is a ~120MB file, may take a few minutes..."
railway volume files upload "$MASTER_JSON_LOCAL" "$REMOTE_MASTER_JSON_PATH" --volume "$RAILWAY_VOLUME" --overwrite

# --- 6. Run the import (+ verify) inside the container -----------------------------------
echo "[6/7] Running the village import inside the container..."
# No `git pull` here: the container has no git installed, and wouldn't need it anyway --
# the deployed image (built from whatever's on origin/main when Railway last auto-deployed)
# is the source of truth for the code running inside it. If scripts/import_india_villages.py
# has changed since that deploy, push first and let Railway redeploy before re-running this.
if ! railway ssh "cd /app && python3 scripts/import_india_villages.py --verify"; then
  echo "ERROR: Import/verify failed inside the container. See the output above." >&2
  exit 1
fi

# --- 7. Summary ---------------------------------------------------------------------------
echo "[7/7] Fetching post-import counts from the live /healthz endpoint..."
HEALTHZ_URL="${HEALTHZ_URL:-https://qumanity.in/healthz}"
if command -v curl >/dev/null 2>&1; then
  curl -sS "$HEALTHZ_URL" || echo "(could not reach $HEALTHZ_URL -- check it manually)"
  echo
fi

echo
echo "=== Done. Master.json uploaded, village import verified PASS inside the container. ==="
echo "Confirm manually: open $HEALTHZ_URL and check village_count == 635622 and status == \"ok\"."
