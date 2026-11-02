#!/usr/bin/env python3
"""~/Desktop/0_Earth/ READ-ONLY inventory and cleanup assessment, 2026-11.

Never moves, renames, deletes, archives, or modifies anything under 0_Earth. Never follows
symlinks outside the tree. Writes only its own new report (docs/0_earth_cleanup_proposal.md,
written by a separate step after this script runs, not by this script itself).

IMPORTANT, established directly this pass (do not assume otherwise): 0_Earth/Continents/ is NOT a
small folder of loose files -- it is a ~493,000-directory, 108 MB scaffold (confirmed this pass via
`find -type d | wc -l`), built by folder_connector.py to mirror the full India location hierarchy
down to village level, PLUS real per-registered-user subfolders already living inside it (e.g.
Continents/0_AS/Countries/0_AS_IND/BORN_HERE/Water/<code>/global_account). Per this project's own
standing rule (never rebuild or alter this tree's structure) and per this task's own instruction
to default to "archive, don't delete" whenever status is uncertain, this script does NOT attempt a
file-by-file classification of all ~493K paths inside Continents/ -- that would be both
impractical and pointless (the vast majority are empty, by-design placeholder directories, not
"clutter"). Instead it: (a) measures Continents/ as a single aggregate (file/dir counts, size,
.DS_Store count) and classifies the whole tree as one unit; (b) gives full, individual,
file-by-file treatment to every LOOSE file directly under 0_Earth/ itself (not inside
Continents/) -- which is where the "backup JSON files cluttering the folder" concern this task
was actually raised about lives.

Usage:
    python3 scripts/audit_0_earth_usage.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EARTH_ROOT = Path(os.environ.get("QM_EARTH_ROOT", Path.home() / "Desktop" / "0_Earth")).expanduser()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def repo_reference_search(name: str) -> list[str]:
    """Greps the repository for any mention of this exact filename -- a direct code/doc
    reference. A miss is NOT proof the file is unused (dynamic paths, external/manual workflows,
    and the live scaffold's own by-design emptiness all exist) -- this is reported as what it is,
    a text-search result, never as a deletion justification on its own."""
    try:
        result = subprocess.run(
            ["grep", "-rlF", "--include=*.py", "--include=*.md", name, str(REPO_ROOT)],  # -F: literal string, not regex
            capture_output=True, text=True, timeout=30,
        )
        hits = [line for line in result.stdout.splitlines() if "/.git/" not in line]
        return hits
    except Exception as e:
        return [f"<search failed: {e}>"]


def inventory_continents_tree(continents_root: Path) -> dict:
    if not continents_root.is_dir():
        return {"exists": False}
    dir_count = 0
    file_count = 0
    ds_store_count = 0
    total_bytes = 0
    max_depth = 0
    base_depth = len(continents_root.parts)
    for root, dirs, files in os.walk(continents_root):
        dir_count += len(dirs)
        depth = len(Path(root).parts) - base_depth
        max_depth = max(max_depth, depth)
        for fn in files:
            file_count += 1
            if fn == ".DS_Store":
                ds_store_count += 1
            try:
                total_bytes += (Path(root) / fn).stat().st_size
            except OSError:
                pass
    return {
        "exists": True, "directory_count": dir_count, "file_count": file_count,
        "ds_store_count": ds_store_count, "total_bytes": total_bytes, "max_depth": max_depth,
    }


def inventory_loose_files(earth_root: Path) -> list[dict]:
    """Every file directly under 0_Earth/ itself (not recursing into Continents/, which is
    handled separately above)."""
    out = []
    if not earth_root.is_dir():
        return out
    for entry in sorted(earth_root.iterdir()):
        if entry.is_file():
            stat = entry.stat()
            out.append({
                "name": entry.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "referenced_in_repo": repo_reference_search(entry.name),
            })
    return out


def main() -> int:
    print(f"0_Earth root (QM_EARTH_ROOT or default): {EARTH_ROOT}")
    if not EARTH_ROOT.is_dir():
        print("BLOCKER: this path does not exist or is not a directory. Nothing to inventory.")
        return 1

    continents = inventory_continents_tree(EARTH_ROOT / "Continents")
    print("\n--- Continents/ tree (the live location-folder scaffold) ---")
    if continents["exists"]:
        print(f"  Directories: {continents['directory_count']:,}")
        print(f"  Files: {continents['file_count']:,} (of which {continents['ds_store_count']} are .DS_Store)")
        print(f"  Total size: {human_size(continents['total_bytes'])}")
        print(f"  Max depth observed: {continents['max_depth']}")
        print("  Classification: CLEARLY LIVE, DO NOT TOUCH (as a single unit) -- matches "
              "folder_connector.py's own documented scaffold, and contains real per-user "
              "subfolders (e.g. BORN_HERE/<element>/<code>/global_account), not just empty "
              "placeholders. Not individually enumerated -- see this script's own module "
              "docstring for why a path-by-path classification of ~493K entries was not attempted.")
    else:
        print("  NOT FOUND.")

    loose = inventory_loose_files(EARTH_ROOT)
    print(f"\n--- Loose files directly under {EARTH_ROOT} ({len(loose)} found) ---")
    for f in loose:
        print(f"  {f['name']}: {human_size(f['size_bytes'])}, modified {f['modified']}, "
              f"referenced in repo by: {f['referenced_in_repo'] or '(no text match found)'}")

    out_json = REPO_ROOT / "docs" / "0_earth_inventory_raw.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"earth_root": str(EARTH_ROOT), "continents": continents, "loose_files": loose}, f, indent=2)
    print(f"\nRaw inventory written to {out_json} (input for docs/0_earth_cleanup_proposal.md).")
    print("\nConfirmed: no file or folder under 0_Earth was moved, deleted, renamed, or modified by this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
