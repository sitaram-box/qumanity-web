"""Account recovery fallback for members with no usable Family Tree (2026-11-14): a new
`admin_queries` ticket category ('account_recovery') for someone who can neither use Family-Tree
recovery (family_recovery_core.py) nor the OTP self-service path (recovery_core.py), submitted
through a new public, unauthenticated route and worked by an Admin through the existing Admin
Panel ticket architecture -- never a second recovery-ticket table.

`admin_queries` already supports an anonymous submitter (migrations/032_admin_queries_guest.py:
`user_id` nullable, `guest_name`/`guest_contact`) -- `guest_name` already covers the requester's
claimed name, and `guest_contact` already covers the contact VALUE (phone number, email address,
or another member's Private ID, stored as typed, exactly like the existing public AI Support
ticket route already does with its own `guest_contact`). What's missing is everything the Admin
Panel's list/detail views need to show as its OWN field rather than buried in free text:

- `date_of_birth`: the claimed date of birth. No existing column fits (users.dob is a REAL
  member's own account, not a claim from someone who isn't one yet).
- `present_location_json`: the claimed present location, stored in the exact same shape/column
  name convention as users.present_location_json, so every existing location-formatting helper in
  this codebase can read it unchanged.
- `contact_method`: which of the three contact-method shapes `guest_contact` actually holds
  ('phone' | 'email' | 'member_private_id') -- guest_contact itself stays untyped free text, same
  as it already is for the AI Support ticket.
- `verification_status`: a DIFFERENT axis from the ticket's own `status` column. `status`
  (open/answered/closed) means "has an Admin looked at and responded to this ticket"; this new
  column means "has an Admin confirmed this person's claimed identity is real" -- an Admin can
  verify someone without yet resolving the ticket, and the two states must not be conflated.
- `verification_notes`: Admin-internal only, never exposed to the requester. Also carries a plain
  timestamped log line for which recovery action (if any) was completed -- e.g. "Private ID
  revealed" or "Temporary PIN generated" -- rather than a sixth column duplicating what
  id_recovery_reveals (for a Private ID reveal) or this very audit trail already records.

All five columns are nullable and populated ONLY for category='account_recovery' rows -- every
existing row, in every other category, is completely unaffected (reads back as NULL, same as the
'member_private_id' not held). Same additive-nullable-ALTER pattern already used throughout this
project's migration history (e.g. qmail_messages.message_type, family_groups.kind).

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(admin_queries)")}
    added = []
    for col, ddl in (
        ("date_of_birth", "TEXT"),
        ("present_location_json", "TEXT"),
        ("contact_method", "TEXT"),
        ("verification_status", "TEXT"),
        ("verification_notes", "TEXT"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE admin_queries ADD COLUMN {col} {ddl}")
            added.append(col)
    conn.commit()
    if added:
        print(f"    admin_queries.{'/'.join(added)} ready (account_recovery tickets only; NULL for every other category).")
    else:
        print("    admin_queries account-recovery columns already present -- nothing to do.")
