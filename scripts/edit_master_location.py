#!/usr/bin/env python3
"""Safe, narrow, single-record editor for the canonical Qumanity_Master.json, 2026-11.

This is the missing tool identified in docs/location_architecture_decision.md: the existing
one-off correction scripts in this directory (scripts/add_navi_mumbai_locations.py,
scripts/add_ganesh_pura_tri_nagar.py, scripts/migrate_haryana_location_ids.py,
scripts/fix_haryana_districts.py) each write Qumanity_Master.json directly, each with its own
bespoke backup convention -- real, working, but each a fresh one-off. This tool generalizes that
same safety pattern (backup, SHA-256 verify, atomic write, dry-run by default) into one reusable
command, for the common case of adding, renaming, or removing exactly ONE location record.

It does NOT perform or enable bulk deduplication. Removing a duplicate requires the SAME kind of
real, read-only reference audit `scripts/dedupe_bawana_tehsil.py` did for Bawana -- this tool
automates exactly that audit as a safety gate, but still refuses any removal with a live
reference, and still requires a human to have already decided which of a duplicate pair survives
(this tool never picks a survivor). The 74 Tehsil-level and 15 Village-level duplicate groups
found by scripts/audit_all_india_duplicates.py are NOT touched by this tool and are not
authorized for removal here -- see docs/india_dedup_migration_plan.md (AWAITING APPROVAL).

ID CONVENTION (established by inspecting the real Master JSON and the existing add-location
scripts, not invented): a location's own id suffix is hexadecimal, uppercase, 1-indexed (no
leading zero, never "0"), counting 1,2,...,9,A,B,...,F,10,11,...  -- i.e. ordinary hex counting
starting at 1. A new "add" must supply an explicit id; this tool validates it matches
<parent_id>.<hex_suffix> and is not already in use -- it never invents the next free suffix for
you, since picking the "right" next id is a decision, not a mechanical default.

OPERATIONS:
  add     -- insert a new record (State/District/Tehsil/Village) under an existing parent.
  rename  -- change an existing record's own `name` field only. The id, parent, and children are
             never touched by rename.
  remove  -- delete an existing record, ONLY if it has zero children and zero live references
             anywhere in the application database (see --help's own safety-gate description).

Never supports "reparent" (moving a record to a different parent) -- there is no safe, general
way to validate that as an ordinary edit; a genuine reparent is exactly the kind of thing
docs/india_dedup_migration_plan.md's own crosswalk process exists for, not this tool.

Usage:
    python3 scripts/edit_master_location.py add    --category village --id CS.DL.3.4.99 --name "New Village" --parent CS.DL.3.4 [--master PATH] [--apply]
    python3 scripts/edit_master_location.py rename --category tehsil  --id CS.DL.3.4 --name "Bawana (renamed)" [--master PATH] [--apply]
    python3 scripts/edit_master_location.py remove --category village --id CS.DL.3.4.99 [--master PATH] [--apply]

Dry-run by default (prints the full plan and every validation result, writes nothing). Pass
--apply only once the dry-run output looks correct.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import import_india_villages as iiv  # noqa: E402 -- reuses the established Master-path resolver
import audit_all_india_duplicates as audit  # noqa: E402 -- reuses normalize_name(), not reinvented

CATEGORY_CHILD_KEY = {"State": "Districts", "District": "tehsils", "Tehsil": "villages", "Village": None}
CATEGORY_PARENT_OF = {"District": "State", "Tehsil": "District", "Village": "Tehsil"}  # State has no parent category here
ID_SUFFIX_RE = re.compile(r"^[1-9A-F][0-9A-F]*$")  # hex, uppercase, 1-indexed, no leading zero -- see module docstring

REFERENCE_QUERIES = [
    # (description, SQL template with one '?' placeholder for the id)
    ("qpunch_addresses.location_id", "SELECT COUNT(*) FROM qpunch_addresses WHERE location_id = ?"),
    ("qpunch_queue_messages.location_id", "SELECT COUNT(*) FROM qpunch_queue_messages WHERE location_id = ?"),
    ("announcements.location_id", "SELECT COUNT(*) FROM announcements WHERE location_id = ?"),
    ("collective_karma.location_id", "SELECT COUNT(*) FROM collective_karma WHERE location_id = ?"),
    ("collective_karma_log.location_id", "SELECT COUNT(*) FROM collective_karma_log WHERE location_id = ?"),
    ("election_cycles.village_id", "SELECT COUNT(*) FROM election_cycles WHERE village_id = ?"),
    ("location_elements.location_id", "SELECT COUNT(*) FROM location_elements WHERE location_id = ?"),
    ("profile_change_requests.location_id", "SELECT COUNT(*) FROM profile_change_requests WHERE location_id = ?"),
    ("recognition_stars.location_id", "SELECT COUNT(*) FROM recognition_stars WHERE location_id = ?"),
    ("reports.location_id", "SELECT COUNT(*) FROM reports WHERE location_id = ?"),
    ("subgroups.village_id", "SELECT COUNT(*) FROM subgroups WHERE village_id = ?"),
    ("village_council.village_id", "SELECT COUNT(*) FROM village_council WHERE village_id = ?"),
    ("zone_sentiment.zone_id", "SELECT COUNT(*) FROM zone_sentiment WHERE zone_id = ?"),
    ("zone_sentiment_stats.zone_id", "SELECT COUNT(*) FROM zone_sentiment_stats WHERE zone_id = ?"),
    ("admin_export_log.location_id", "SELECT COUNT(*) FROM admin_export_log WHERE location_id = ?"),
    ("india_villages.tehsil_id", "SELECT COUNT(*) FROM india_villages WHERE tehsil_id = ?"),
]


def sha256_of(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_master(master_path: Path) -> dict:
    with open(master_path, encoding="utf-8") as f:
        return json.load(f)


def _india_tree(master: dict) -> dict:
    asia = next(c for c in master["Continents"] if c["name"] == "Asia")
    return next(c for c in asia["Countries"] if c.get("name") == "India")


def find_record(master: dict, category: str, record_id: str):
    """Returns (record_dict, parent_dict_or_None, siblings_list_or_None, zone_dict_or_None) for
    the given category/id, or (None, None, None, None) if not found. Walks only the India tree --
    this tool is India-scoped, matching scripts/audit_all_india_duplicates.py's own scope."""
    india = _india_tree(master)
    if category == "State":
        for zone in india.get("Zones", []):
            for state in zone.get("States", []):
                if state["id"] == record_id:
                    return state, zone, zone["States"], zone
        return None, None, None, None
    if category == "District":
        for zone in india.get("Zones", []):
            for state in zone.get("States", []):
                for d in state.get("Districts") or []:
                    if d["id"] == record_id:
                        return d, state, state.get("Districts"), zone
        return None, None, None, None
    if category == "Tehsil":
        for zone in india.get("Zones", []):
            for state in zone.get("States", []):
                for d in state.get("Districts") or []:
                    for t in d.get("tehsils") or []:
                        if t["id"] == record_id:
                            return t, d, d.get("tehsils"), zone
        return None, None, None, None
    if category == "Village":
        for zone in india.get("Zones", []):
            for state in zone.get("States", []):
                for d in state.get("Districts") or []:
                    for t in d.get("tehsils") or []:
                        for v in t.get("villages") or []:
                            if v["id"] == record_id:
                                return v, t, t.get("villages"), zone
        return None, None, None, None
    raise ValueError(f"Unknown category {category!r}")


def validate_id_format(record_id: str, parent_id: str | None) -> str | None:
    """Returns an error string, or None if valid. Checks the hex-suffix convention and (for a
    child category) that the id is genuinely <parent_id>.<suffix>."""
    if parent_id is not None:
        prefix = parent_id + "."
        if not record_id.startswith(prefix):
            return f"id {record_id!r} does not start with the required parent prefix {prefix!r}"
        suffix = record_id[len(prefix):]
    else:
        suffix = record_id.rsplit(".", 1)[-1]
    if not ID_SUFFIX_RE.match(suffix):
        return (f"id suffix {suffix!r} does not match the established convention (hex, "
                f"uppercase, 1-indexed, e.g. 1, 2, ..., 9, A, B, ..., F, 10, 11, ...)")
    return None


def check_duplicate_would_result(siblings: list, new_name: str, exclude_id: str | None = None) -> str | None:
    """Reuses audit_all_india_duplicates.normalize_name() -- the one duplicate definition this
    project uses, not a second one. Returns an error string, or None if no duplicate would
    result."""
    norm = audit.normalize_name(new_name)
    for sib in siblings or []:
        if exclude_id is not None and sib["id"] == exclude_id:
            continue
        if audit.normalize_name(sib.get("name", "")) == norm:
            return (f"would create a duplicate: sibling {sib['id']!r} is already named "
                    f"{sib['name']!r} (normalized: {norm!r})")
    return None


def _structured_user_location_refs(db_path: Path, record_id: str) -> dict:
    """Read-only, structured (never substring) check against users/account_ids -- same method
    scripts/dedupe_bawana_tehsil.py already validated against the real denormalization false-
    positive this project has. Returns counts; never prints a user's own data."""
    if not db_path.is_file():
        return {"error": f"database not found at {db_path}"}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = {"users_eligible": 0, "users_ineligible": 0, "account_ids": 0, "provisional_locations": 0}
    for row in conn.execute("SELECT present_location_json, birth_location_json, is_demo, is_removed FROM users"):
        hit = False
        for blob_name in ("present_location_json", "birth_location_json"):
            raw = row[blob_name]
            if not raw:
                continue
            try:
                loc = json.loads(raw)
            except Exception:
                continue
            for level in ("village", "tehsil", "district", "state"):
                node = loc.get(level) or {}
                if isinstance(node, dict) and node.get("id") == record_id:
                    hit = True
        if hit:
            if row["is_demo"] or row["is_removed"]:
                out["users_ineligible"] += 1
            else:
                out["users_eligible"] += 1
    for row in conn.execute("SELECT present_location_json FROM account_ids"):
        raw = row["present_location_json"]
        if not raw:
            continue
        try:
            loc = json.loads(raw)
        except Exception:
            continue
        for level in ("village", "tehsil", "district", "state"):
            node = loc.get(level) or {}
            if isinstance(node, dict) and node.get("id") == record_id:
                out["account_ids"] += 1
    try:
        out["provisional_locations"] = conn.execute(
            "SELECT COUNT(*) FROM provisional_locations WHERE parent_verified_tehsil_id = ? OR parent_verified_state_id = ?",
            (record_id, record_id),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        pass  # table may not exist in every environment this tool could run against
    conn.close()
    return out


def audit_references(db_path: Path, record_id: str) -> dict:
    """The full, read-only reference audit a 'remove' must pass. mode=ro -- physically cannot
    write. Returns {"total_references": int, "detail": {...}}."""
    result = {"structured": _structured_user_location_refs(db_path, record_id), "plain_columns": {}}
    if not db_path.is_file():
        return result
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    for label, sql in REFERENCE_QUERIES:
        try:
            count = conn.execute(sql, (record_id,)).fetchone()[0]
        except sqlite3.OperationalError:
            count = None  # table/column not present in this environment -- reported, not hidden
        result["plain_columns"][label] = count
    conn.close()
    structured = result["structured"]
    total = (0 if "error" in structured else
              structured["users_eligible"] + structured["account_ids"] + structured["provisional_locations"])
    total += sum(c for c in result["plain_columns"].values() if isinstance(c, int))
    result["total_eligible_references"] = total
    result["total_ineligible_references"] = structured.get("users_ineligible", 0) if "error" not in structured else 0
    return result


def plan_add(master: dict, args) -> dict:
    existing, _, _, _ = find_record(master, args.category, args.id)
    if existing is not None:
        return {"ok": False, "reason": f"id {args.id!r} already exists"}
    if args.category == "State":
        return {"ok": False, "reason": "adding a new State/UT is not supported by this tool -- that is a structural change, not a narrow edit"}
    parent_category = CATEGORY_PARENT_OF[args.category]
    parent, _, _, _ = find_record(master, parent_category, args.parent)
    if parent is None:
        return {"ok": False, "reason": f"parent {args.parent!r} ({parent_category}) not found"}
    id_err = validate_id_format(args.id, args.parent)
    if id_err:
        return {"ok": False, "reason": id_err}
    child_key = CATEGORY_CHILD_KEY[parent_category]
    siblings = parent.get(child_key) or []
    dup_err = check_duplicate_would_result(siblings, args.name)
    if dup_err:
        return {"ok": False, "reason": dup_err}
    new_record = {"id": args.id, "name": args.name}
    if args.category != "Village":
        new_record[CATEGORY_CHILD_KEY[args.category]] = []
    return {"ok": True, "op": "add", "category": args.category, "parent": parent,
            "parent_child_key": child_key, "new_record": new_record}


def plan_rename(master: dict, args) -> dict:
    record, parent, siblings, _ = find_record(master, args.category, args.id)
    if record is None:
        return {"ok": False, "reason": f"id {args.id!r} ({args.category}) not found"}
    dup_err = check_duplicate_would_result(siblings, args.name, exclude_id=args.id)
    if dup_err:
        return {"ok": False, "reason": dup_err}
    return {"ok": True, "op": "rename", "category": args.category, "record": record,
            "old_name": record["name"], "new_name": args.name}


def plan_remove(master: dict, args, db_path: Path) -> dict:
    record, parent, siblings, _ = find_record(master, args.category, args.id)
    if record is None:
        return {"ok": False, "reason": f"id {args.id!r} ({args.category}) not found"}
    child_key = CATEGORY_CHILD_KEY[args.category]
    children = (record.get(child_key) or []) if child_key else []
    if children:
        return {"ok": False, "reason": f"refuses to remove: {len(children)} child record(s) still exist "
                                        f"under {args.id!r} -- reconcile children first (see docs/india_dedup_migration_plan.md)"}
    refs = audit_references(db_path, args.id)
    if refs["total_eligible_references"] > 0:
        return {"ok": False, "reason": f"refuses to remove: {refs['total_eligible_references']} real, eligible "
                                        f"reference(s) found -- see detail below", "reference_detail": refs}
    return {"ok": True, "op": "remove", "category": args.category, "record": record,
            "parent": parent, "siblings": siblings, "reference_detail": refs}


def apply_change(master: dict, plan: dict) -> None:
    if plan["op"] == "add":
        plan["parent"].setdefault(plan["parent_child_key"], []).append(plan["new_record"])
    elif plan["op"] == "rename":
        plan["record"]["name"] = plan["new_name"]
    elif plan["op"] == "remove":
        plan["siblings"].remove(plan["record"])
    else:
        raise ValueError(f"unknown op {plan['op']!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("op", choices=["add", "rename", "remove"])
    ap.add_argument("--category", required=True, choices=["State", "District", "Tehsil", "Village"])
    ap.add_argument("--id", required=True, help="The record's own dotted id (for 'add', the NEW id to create)")
    ap.add_argument("--name", help="Required for 'add' and 'rename'")
    ap.add_argument("--parent", help="Required for 'add' -- the immediate parent's own id")
    ap.add_argument("--master", help="Override the Master JSON path (for tests, point at a fixture file)")
    ap.add_argument("--db-path", help="Override the application database path (defaults to db.DB_PATH)")
    ap.add_argument("--apply", action="store_true", help="Write the change. Without this, dry-run only.")
    args = ap.parse_args()

    if args.op in ("add", "rename") and not args.name:
        print("BLOCKER: --name is required for add/rename", file=sys.stderr)
        return 2
    if args.op == "add" and not args.parent:
        print("BLOCKER: --parent is required for add", file=sys.stderr)
        return 2

    master_path = Path(args.master).expanduser() if args.master else iiv.resolve_master_json_path()
    print(f"Master JSON: {master_path}")
    if not master_path.is_file():
        print(f"BLOCKER: {master_path} not found", file=sys.stderr)
        return 2
    before_hash = sha256_of(master_path)
    print(f"SHA-256 before: {before_hash}")
    master = load_master(master_path)

    sys.path.insert(0, str(ROOT))
    import db as dbmod
    db_path = Path(args.db_path) if args.db_path else dbmod.DB_PATH

    if args.op == "add":
        plan = plan_add(master, args)
    elif args.op == "rename":
        plan = plan_rename(master, args)
    else:
        plan = plan_remove(master, args, db_path)

    print(f"\nOperation: {args.op} {args.category} {args.id!r}")
    if not plan["ok"]:
        print(f"BLOCKER: {plan['reason']}")
        if "reference_detail" in plan:
            print(f"  Reference detail: {plan['reference_detail']}")
        print("\nNo file was modified.")
        return 1

    if plan["op"] == "add":
        print(f"Would add under parent {args.parent!r}: {plan['new_record']}")
    elif plan["op"] == "rename":
        print(f"Would rename: {plan['old_name']!r} -> {plan['new_name']!r}")
    elif plan["op"] == "remove":
        print(f"Would remove: {plan['record']} (0 children, 0 eligible references confirmed)")
        print(f"  Reference audit: {plan['reference_detail']}")

    if not args.apply:
        print("\nDry-run complete (no --apply given). No file was modified.")
        return 0

    # Re-read and re-hash immediately before writing -- refuses if the file changed since we
    # first read it (optimistic concurrency control against a concurrent editor).
    current_hash = sha256_of(master_path)
    if current_hash != before_hash:
        print(f"\nBLOCKER: {master_path} changed on disk since this tool read it "
              f"(before={before_hash}, now={current_hash}) -- another process may have edited it. "
              f"Refusing to proceed. Re-run from scratch.", file=sys.stderr)
        return 2

    backup_path = master_path.with_name(
        f"{master_path.stem}.before_edit_master_location_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}{master_path.suffix}")
    shutil.copy2(master_path, backup_path)
    if sha256_of(backup_path) != before_hash:
        print(f"BLOCKER: backup checksum mismatch -- refusing to proceed.", file=sys.stderr)
        return 2
    print(f"\nBackup written to: {backup_path}")

    apply_change(master, plan)

    tmp_path = master_path.with_suffix(master_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(master, ensure_ascii=False))  # matches the real file's own on-disk format exactly

    # Validate the temp file before replacing the original.
    with open(tmp_path, encoding="utf-8") as f:
        reparsed = json.load(f)
    reparsed_record, _, _, _ = find_record(reparsed, args.category, args.id)
    if plan["op"] in ("add", "rename") and reparsed_record is None:
        tmp_path.unlink(missing_ok=True)
        print("BLOCKER: re-parsed temp file does not contain the expected change -- refusing to replace the original.", file=sys.stderr)
        return 2
    if plan["op"] == "remove" and reparsed_record is not None:
        tmp_path.unlink(missing_ok=True)
        print("BLOCKER: re-parsed temp file still contains the record meant to be removed -- refusing to replace the original.", file=sys.stderr)
        return 2

    tmp_path.replace(master_path)  # atomic on the same filesystem
    after_hash = sha256_of(master_path)
    print(f"SHA-256 after:  {after_hash}")
    print(f"Wrote: {master_path}")
    print(f"\nNOTE: derived files (static/data/subcontinent_districts.json, "
          f"static/data/india_districts_tehsils.json, india_villages) are now stale relative to "
          f"this change. Regenerate them via the project's established process once this change "
          f"is reviewed -- this tool deliberately does not do that automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
