# Location ID Crosswalk: Proposed Schema

**Status: PROPOSAL ONLY — not implemented, not approved.** This document proposes a schema for
recording retired/merged location IDs. It does not populate any survivor mapping for the 73
remaining Tehsil groups or 15 Village groups found by `scripts/audit_all_india_duplicates.py` —
those decisions are a separate approval gate, per `docs/india_dedup_migration_plan.md`.

## Why this is needed

`docs/location_architecture_decision.md` §3 identified the gap directly: dotted location IDs are
load-bearing (they appear in `users.present_location_json`/`birth_location_json`,
`india_villages.tehsil_id`, and 15 other columns catalogued in the migration plan's §3.2), and
neither the JSON-canonical nor a hypothetical SQLite-canonical architecture currently has anywhere
to record "this id was retired, and this is what replaced it." Without that record, a future
reader of an old export, log, or backup has no way to resolve a retired ID back to a current one.

## Proposed table

```sql
CREATE TABLE location_id_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retired_id TEXT NOT NULL UNIQUE,         -- the ID being retired; never reused for anything else
    surviving_id TEXT NOT NULL,              -- the ID that replaces it
    category TEXT NOT NULL,                  -- 'State' | 'District' | 'Tehsil' | 'Village'
    historical_name TEXT NOT NULL,           -- the retired record's own name, preserved verbatim
    historical_parent_id TEXT,               -- the retired record's own parent id at retirement time
    surviving_parent_id TEXT,                -- the surviving record's parent id (usually the same; recorded explicitly in case it differs)
    reason TEXT NOT NULL,                    -- short human-readable reason, e.g. "duplicate tehsil, same name, same district"
    evidence_ref TEXT,                       -- path/row reference into the audit that justified this, e.g. "india_duplicate_audit_2026-11-01.csv#group=65"
    approval_status TEXT NOT NULL DEFAULT 'proposed',  -- 'proposed' | 'approved' | 'rejected'
    approved_by TEXT,                        -- the approving owner's identifier
    approved_at TEXT,                        -- ISO timestamp
    effective_at TEXT,                       -- ISO timestamp the mapping actually took effect (NULL until applied)
    reference_update_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'complete'
    aliases_json TEXT,                       -- JSON array of any OTHER historical ids/names this same real place has carried, if known
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_location_id_history_surviving ON location_id_history(surviving_id);
CREATE UNIQUE INDEX idx_location_id_history_retired ON location_id_history(retired_id);
```

## Required invariants

- **No ID reuse**: `retired_id` is `UNIQUE` — once an id appears here, it can never be assigned to
  a new, unrelated record by `scripts/edit_master_location.py` or any future tool (that tool
  would need to check this table before accepting an `add` with a given id — **not yet wired up**,
  since the table doesn't exist yet; this is a follow-up once the table is approved and built).
- **No cycles**: `surviving_id` must never itself appear as a `retired_id` elsewhere in a way that
  would form a chain back to the original `retired_id`. A future write path must check this before
  inserting.
- **No cross-category mapping**: a `Tehsil` never maps to a `Village`'s surviving id, or vice
  versa — `category` on both sides of a mapping must match (enforced in application logic, since
  SQLite's own `CHECK` can't easily cross-reference `surviving_id`'s own category without a
  lookup).
- **No cross-incompatible-parent mapping without explicit evidence**: a mapping where
  `historical_parent_id != surviving_parent_id` is not, by itself, forbidden (a record can
  legitimately be found to belong under a *different* correct parent than it was first filed
  under), but it must carry a non-empty `evidence_ref`, and this is exactly the case
  `docs/india_dedup_migration_plan.md` §3.5 says needs the most caution.
- **Unapproved means invisible to production**: any resolution logic that might read this table
  must filter on `approval_status = 'approved'` — a `'proposed'` row is a draft, not a live
  redirect, and must never be silently consumed. This is the single most important invariant: a
  proposal sitting in this table is not itself an authorization to act on it.
- **Historical IDs are never deleted**: once a row exists, it stays, even if its `approval_status`
  ends up `'rejected'` — the fact that a mapping was *considered* and rejected is itself useful
  history, and silently deleting a rejected proposal would make it look like it was never
  evaluated.

## What this schema does NOT do

- It does not resolve a retired ID automatically anywhere in the live application — building that
  resolution layer (e.g., a lookup the registration/search routes consult) is a separate,
  not-yet-scoped follow-up, once there is at least one `'approved'` row to resolve.
- It does not replace `scripts/edit_master_location.py`'s own refusal to remove a referenced
  record — removal still requires zero live references first (per that tool's own safety gate);
  this table is where the *decision* that a removal is correct gets recorded, once references have
  genuinely reached zero (or been migrated elsewhere by a separate, approved process).
- It is not populated with any real survivor mapping by this task. Every row described above is
  illustrative schema design, not a proposed real row.

## Approval status

🔵 **Proposed, not approved, not built.** Requires owner sign-off on the schema above before a
migration creates this table.
