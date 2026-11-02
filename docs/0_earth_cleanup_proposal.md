# `~/Desktop/0_Earth/` Cleanup Proposal

**READ-ONLY ASSESSMENT. No file or folder under `0_Earth` has been moved, renamed, archived, or
deleted by this document or by `scripts/audit_0_earth_usage.py`, which produced the raw data
behind it (`docs/0_earth_inventory_raw.json`). No structure was rebuilt.**

2026-11-02. `0_Earth` is a live, structurally-significant folder tree — it is never casually
rebuilt or restructured, and an untracked `folder_export/Earth/` directory inside the git working
tree is a separate, legitimate, project-local mirror (`folder_sync.py`'s own daily export target),
not evidence that anything under `0_Earth` itself is clutter. This assessment defaults to
"archive, don't delete, needs a human" whenever genuinely uncertain.

## What `0_Earth` actually is (established this pass, not assumed)

`0_Earth` has two very different parts, and conflating them would be a mistake:

1. **`Continents/`** — a ~493,302-directory, 216-file, 107.8 MB scaffold
   (`scripts/audit_0_earth_usage.py`'s own measured output), built and maintained by
   `folder_connector.py`/`archive_writer.py` to mirror the full India location hierarchy down to
   village level, plus a per-country skeleton for the rest of the world. It already contains real
   per-registered-user subfolders (e.g. `Continents/0_AS/Countries/0_AS_IND/BORN_HERE/Water/
   <code>/global_account`), not just empty placeholders. **This entire tree is classified
   CLEARLY LIVE, DO NOT TOUCH, as a single unit.** It was not enumerated path-by-path (see the
   next section for why), and nothing proposed here touches it.
2. **Seven loose files directly under `0_Earth/`** — the actual subject of "backup JSON files
   cluttering the folder," reviewed individually below.

## Why `Continents/` was not inventoried file-by-file

A ~493,000-directory tree is both impractical to classify individually (the report would be
useless) and, more importantly, the vast majority of those directories are *empty by design* —
they are the scaffold itself, not clutter that accumulated. Treating an empty placeholder
directory as "unclear, needs review" 493,000 times would not serve the owner; it was measured and
classified as one unit instead. If a future, narrower cleanup question arises inside this tree
(e.g. "are there orphaned per-user folders for removed accounts?"), that is a different, much more
targeted question than this task asked, and would need its own careful, separately-scoped pass —
explicitly **not** attempted here.

## The seven loose files — individually reviewed

| File | Size | Modified | Referenced in repo (text search) | Category |
|---|---|---|---|---|
| `Qumanity_Master.json` | 32.5 MB | 2026-10-28 | 30+ files (tests, docs, every location script, `folder_connector.py`) | **Clearly live, do not touch** — the canonical source this whole audit is about |
| `Qumanity_Master.before_haryana_fix_20261025_194513.json` | 32.4 MB | 2026-10-25 | `docs/audit_india_location_data_2026_11.md` (cited as historical evidence) | **Unclear, needs a human decision** — a named, dated, purposeful pre-edit backup, still referenced by name in an existing audit doc; whether it's still needed depends on confidence the Haryana fix is stable, which is not this pass's call |
| `Qumanity_Master.before_ganesh_pura_fix_20261028_173803.json` | 32.4 MB | 2026-10-28 | none found | **Unclear, needs a human decision** — same reasoning; no text reference doesn't mean unneeded (backups are typically never read back by code, only by a human restoring from them) |
| `Qumanity_Master.before_navi_mumbai_fix_20261028_173822.json` | 32.4 MB | 2026-10-28 | none found | **Unclear, needs a human decision** — same reasoning, and notably made the same day as the Ganesh Pura backup above (two separate fixes, same day) |
| `Qumanity_Master.before_haryana_fix_manual_20261025_194439.json` | 115.0 MB | 2026-10-25 | none found | **Unclear, needs a human decision** — more than 3x the size of every other Master-JSON snapshot here (115 MB vs ~32.4 MB each); the size difference itself is worth the owner's attention before any decision, since it suggests a materially different structure or an intermediate, not-yet-cleaned-up state, not just a timestamped copy of the same file |
| `O.json` | 24.3 KB | 2026-09-03 | none found | **Unclear, needs a human decision** — a small, standalone Earth/Continents/Countries skeleton (names/ids/codes only, no deeper hierarchy); no code reference found, but its age (oldest file in the folder) and distinct shape suggest it may be an early reference/seed file rather than disposable clutter — not confidently classifiable either way from repository evidence alone |
| `.DS_Store` | 8.0 KB | 2026-09-05 | only this assessment's own script, which merely names the file | **Clearly dead weight, safe to archive** — a macOS Finder metadata file with no functional role anywhere in this project; the same applies to the 34 `.DS_Store` files found scattered inside `Continents/` (counted, not individually listed, as part of that tree's aggregate above). Even here, "safe to archive" means only that archiving may be considered — no deletion is authorized by this document. |

## What this proposal does NOT do

No folder or file was moved. No file was deleted. No structure was rebuilt. No content was
modified. The only write this pass made anywhere near `0_Earth` was `scripts/
audit_0_earth_usage.py`'s own report file, `docs/0_earth_inventory_raw.json`, written to the
**repository's** `docs/` folder, not to `0_Earth` itself.

## Summary for the owner

- One category is genuinely safe to consider archiving with no real risk: `.DS_Store` files
  (35 total, 1 loose + 34 inside `Continents/`) — these regenerate automatically and carry zero
  data.
- Five files (`O.json` and the four `Qumanity_Master.before_*` backups) are "unclear" by this
  pass's own honest assessment — not because they look dangerous, but because deciding whether a
  backup is still needed requires confidence about whether its corresponding fix is final, which
  only the owner can judge. The unusually large `Qumanity_Master.before_haryana_fix_manual_
  20261025_194439.json` (115 MB vs. the ~32.4 MB norm) is flagged for particular attention.
- `Continents/` and `Qumanity_Master.json` itself are unambiguously live and were not touched or
  individually enumerated.
