# Reference datasets

Checked-in, independently verifiable reference data used by research/classification scripts.
Never the canonical source of truth for anything Qumanity itself serves to members — see each
file's own provenance below. Nothing here is read by `app.py` at runtime.

## `lok_sabha_constituencies_543.csv`

All 543 Lok Sabha (Parliamentary) constituencies, used by
`scripts/classify_india_electoral_vs_revenue_geography.py` to directly name-match Master JSON
"district" records against known electoral-geography names, rather than guessing from a regex
pattern.

**Source:** Local Government Directory (LGD), Government of India (`lgdirectory.gov.in` /
`data.gov.in`) Parliamentary-Constituency-to-Assembly-Constituency mapping, republished in
structured CSV form at
<https://gist.github.com/planemad/96a5a3644a6fed2a43ddf579f6a9612d> (the gist's own stated as-of
date: March 2024). **This was not a live fetch of LGD's own site this session** — the gist was
used because LGD's own CSV export has been reported broken since 2011 (noted in the companion
[`india-local-government-directory`](https://github.com/planemad/india-local-government-directory)
project, which points to the same underlying LGD codes). This is disclosed explicitly rather than
claimed as a direct primary-source fetch.

**Independent cross-check performed this session:** state-wise constituency counts derived from
this CSV were compared against a *separately* sourced reference (Ministry of External Affairs'
published state-wise Lok Sabha seat table, PIB, the Election Commission of India's own 2024 Atlas,
and Wikipedia's ECI-delimitation-order-cited constituency list) — **34 of 36 states matched
exactly**, with the remaining 2 "mismatches" being a naming-convention artifact, not a real
discrepancy (see the Dadra and Nagar Haveli / Daman and Diu note below). Total: **543** in both
sources independently. This two-source agreement is the actual evidence of correctness; neither
source alone was treated as sufficient.

**Known structural difference, handled as a documented alias, not a silent merge:** the source
dataset reflects the 2020 Dadra and Nagar Haveli + Daman and Diu UT merger (one shared Lok Sabha
seat, one combined state record). Qumanity's own `Qumanity_Master.json` still lists these as two
separate states/UTs (pre-merger structure). This CSV's `alias_note` column documents, for the two
affected rows, exactly why the same constituency appears once under each Master.json state name —
the underlying constituency count (543) is never inflated by this; only the CSV's *row* count
(545) reflects it, and that is explained inline.

**What is NOT in this dataset:** reservation category (General/SC/ST) — the source CSV does not
carry this field, and it was left blank rather than guessed (`reservation_category` column, empty
for every row). A future pass could source this separately from the ECI's own delimitation order
if needed.

**Validated (2026-11), per `scripts/classify_india_electoral_vs_revenue_geography.py`'s own test
suite:** exactly 543 unique `constituency_number` values; 0 empty constituency names; 0 empty
state/UT names; 0 duplicate `(state_ut, constituency_number)` pairs; 37 unique states/UTs
(matching Master.json's own state count, via the documented DNH/DD alias above).

**File checksum (SHA-256):** see the classification script's own JSON report output, which
records the exact checksum of this file at the time each classification run used it.

**Recommended next step, not done this session:** a true primary-source fetch directly from
`lgdirectory.gov.in` or the ECI's own constituency publication, to remove the one remaining
dependency on a community-republished mirror.
