"""The Marquee's religious-text library (2026-11-02, Universal Multi-Religion Marquee).

Replaces the old `RELIGION_MARQUEE_SOURCES` hardcoded Python dict (app.py, now removed) with a
DB-backed registry of traditions -> collections -> per-language text entries, matching the
normalized schema proposed (but never applied) in
docs/audit_multi_religion_marquee_proposal_2026_11.md section 3.6. This module owns that schema
and is the ONLY place that reads/writes it; app.py calls the resolver functions below and never
touches these tables directly, the same separation every other `*_core.py` module in this
codebase already uses (board_core, family_core, karma_core, ...).

Rights gate (hard requirement, not a convention): a collection is only ever eligible to be served
publicly when BOTH `review_status = 'approved'` AND `marquee_eligible = 1`. A collection can exist
fully described in this table -- source, translator, license, even `pending_rights_review` -- and
still never reach a single visitor, which is exactly the point: this module is the enforcement
point for "no unverified copyrighted text may be copied into Qumanity's public content files or
displayed publicly" (see docs/marquee_religious_text_sources.md for the actual research findings
behind every row seeded below).

Reading-religion independence: nothing in this module, or in app.py's resolver that calls it, ever
writes to users.religion_belief. A member's profile religion only ever supplies the INITIAL
reading-religion default (see app.py's _marquee_religion_for_session) -- after that, the reading
selection lives entirely in the browser (poems.js, localStorage) and is passed back to the server
as an explicit, allowlist-checked ?religion=/?lang= query parameter on every request. See
app.py's api_poems_meta()/api_poem() for exactly how that allowlist check works.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS religious_traditions (
    id              TEXT PRIMARY KEY,          -- stable slug, matches a RELIGION_BELIEF_VALUES
                                                -- entry where one exists (e.g. 'hindu', 'muslim')
                                                -- but is NOT the same enum -- a tradition can
                                                -- exist here with zero collections (not yet
                                                -- content-ready), and a religion_belief value
                                                -- with no matching row here just means "no
                                                -- tradition row created yet", not an error.
    display_name    TEXT NOT NULL,
    default_label   TEXT NOT NULL,              -- the gold-box text, e.g. 'सीताराम', 'Jesus'
    default_language TEXT NOT NULL,             -- language_code to select when a member has no
                                                 -- saved reading-language preference yet
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS text_collections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tradition_id    TEXT NOT NULL REFERENCES religious_traditions(id),
    slug            TEXT NOT NULL UNIQUE,       -- e.g. 'hindu_original', 'christian_psalms_kjv'
    display_title   TEXT NOT NULL,              -- shown as poems.js's chip tooltip
    is_original_work INTEGER NOT NULL DEFAULT 0, -- 1 = newly-authored Qumanity content; NEVER
                                                  -- call this scripture or a translation
    source_book     TEXT,                       -- e.g. 'Vinaya Patrika', 'Psalms'
    author_or_translator TEXT,
    publisher       TEXT,
    source_url      TEXT,
    edition         TEXT,
    rights_status   TEXT NOT NULL DEFAULT 'pending_rights_review'
                    CHECK (rights_status IN
                        ('public_domain', 'cc_licensed', 'rights_cleared',
                         'pending_rights_review', 'source_unverified', 'not_permitted')),
    attribution_text TEXT,                      -- the exact credit line this collection requires
    license_notes   TEXT,                       -- short human-readable summary of the finding
    review_status   TEXT NOT NULL DEFAULT 'draft'
                    CHECK (review_status IN ('draft', 'in_review', 'approved', 'suspended', 'retired')),
    marquee_eligible INTEGER NOT NULL DEFAULT 0, -- only review_status='approved' AND this=1 rows
                                                  -- are ever resolvable/servable -- see
                                                  -- resolve_collection() below, the one choke point
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_text_collections_tradition ON text_collections(tradition_id);
CREATE INDEX IF NOT EXISTS idx_text_collections_eligible ON text_collections(marquee_eligible, review_status);

CREATE TABLE IF NOT EXISTS text_collection_languages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id   INTEGER NOT NULL REFERENCES text_collections(id),
    language_code   TEXT NOT NULL,              -- 'hi', 'ar', 'pa', 'en', 'pi' ...
    display_name    TEXT NOT NULL,              -- native-script label, e.g. 'हिन्दी'
    script_direction TEXT NOT NULL DEFAULT 'ltr' CHECK (script_direction IN ('ltr', 'rtl')),
    is_original_language INTEGER NOT NULL DEFAULT 0,
    translator_name TEXT,
    UNIQUE (collection_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_tcl_collection ON text_collection_languages(collection_id);

CREATE TABLE IF NOT EXISTS text_entries (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_language_id INTEGER NOT NULL REFERENCES text_collection_languages(id),
    ordinal                 INTEGER NOT NULL,   -- 0-based position; same meaning as the old
                                                 -- {id,marker,text} JSON files' sorted "id" order
    external_ref            TEXT,               -- canonical citation, e.g. 'Surah 1:1', 'Psalm 23:1'
    marker                  TEXT NOT NULL,       -- short display label (existing JSON field)
    text                    TEXT NOT NULL,
    UNIQUE (collection_language_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_text_entries_cl ON text_entries(collection_language_id);
"""


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    conn.commit()


# ---- Seeding --------------------------------------------------------------------------------
#
# Every tradition Qumanity's profile religion dropdown accepts (RELIGION_BELIEF_VALUES in app.py)
# gets a `religious_traditions` row here so the Religion Selector/gold-box-label lookup never has
# a gap -- a tradition with no approved collection yet simply has none, and resolve_collection()
# returns None for it (api_poems_meta's existing "coming_soon" path, unchanged).
_TRADITIONS = [
    # (id, display_name, default_label, default_language, sort_order)
    ("hindu", "Hindu", "सीताराम", "hi", 0),
    ("christian", "Christian", "Jesus", "en", 1),
    ("muslim", "Muslim", "الله", "ar", 2),
    ("sikh", "Sikh", "ਵਾਹਿਗੁਰੂ", "pa", 3),
    ("buddhist", "Buddhist", "Buddha", "en", 4),
]

BASE_DIR = Path(__file__).resolve().parent


def _load_json_poems(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return sorted(json.load(f), key=lambda p: p["id"])


def _seed_collection(conn, *, tradition_id, slug, display_title, is_original_work, source_book,
                      author_or_translator, publisher, source_url, edition, rights_status,
                      attribution_text, license_notes, review_status, marquee_eligible, sort_order,
                      languages):
    """languages: list of dicts {code, display_name, script_direction, is_original_language,
    translator_name, entries_path (Path to a {id,marker,text} JSON file, or None for a
    rights-pending placeholder with no servable text yet)}. Idempotent on `slug` AND, separately,
    on each language's own `code` within that collection (2026-11-02, added for the Christian
    Hindi/Biblica addition): re-running this on an already-seeded collection never duplicates the
    collection row or any language it already has, but DOES add any language in `languages` the
    existing row doesn't have yet (and refreshes the collection's own metadata columns to the
    caller's current values -- e.g. an attribution_text that now needs to describe two languages'
    distinct rights instead of one). This is what lets a later task add a new language to an
    already-live collection without a one-off migration, the same `CREATE TABLE IF NOT EXISTS`-
    style idempotent-seed pattern every other `*_core.py` module in this codebase already uses."""
    existing = conn.execute("SELECT id FROM text_collections WHERE slug = ?", (slug,)).fetchone()
    if existing:
        collection_id = existing["id"]
        conn.execute(
            """UPDATE text_collections SET display_title=?, is_original_work=?, source_book=?,
               author_or_translator=?, publisher=?, source_url=?, edition=?, rights_status=?,
               attribution_text=?, license_notes=?, review_status=?, marquee_eligible=?,
               sort_order=?, updated_at=datetime('now') WHERE id=?""",
            (display_title, int(is_original_work), source_book, author_or_translator, publisher,
             source_url, edition, rights_status, attribution_text, license_notes, review_status,
             int(marquee_eligible), sort_order, collection_id),
        )
    else:
        cur = conn.execute(
            """INSERT INTO text_collections
               (tradition_id, slug, display_title, is_original_work, source_book, author_or_translator,
                publisher, source_url, edition, rights_status, attribution_text, license_notes,
                review_status, marquee_eligible, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tradition_id, slug, display_title, int(is_original_work), source_book, author_or_translator,
             publisher, source_url, edition, rights_status, attribution_text, license_notes,
             review_status, int(marquee_eligible), sort_order),
        )
        collection_id = cur.lastrowid
    for lang in languages:
        already = conn.execute(
            "SELECT id FROM text_collection_languages WHERE collection_id = ? AND language_code = ?",
            (collection_id, lang["code"]),
        ).fetchone()
        if already:
            continue  # this language (and its entries) was already seeded in an earlier run
        lcur = conn.execute(
            """INSERT INTO text_collection_languages
               (collection_id, language_code, display_name, script_direction, is_original_language, translator_name)
               VALUES (?,?,?,?,?,?)""",
            (collection_id, lang["code"], lang["display_name"], lang.get("script_direction", "ltr"),
             int(lang.get("is_original_language", False)), lang.get("translator_name")),
        )
        cl_id = lcur.lastrowid
        entries_path = lang.get("entries_path")
        if entries_path and entries_path.exists():
            for poem in _load_json_poems(entries_path):
                conn.execute(
                    """INSERT INTO text_entries (collection_language_id, ordinal, external_ref, marker, text)
                       VALUES (?,?,?,?,?)""",
                    (cl_id, poem["id"], poem.get("external_ref"), poem["marker"], poem["text"]),
                )
    conn.commit()
    return collection_id


def seed_builtin_collections(conn):
    """Registers every tradition row, then imports the collections this repository has ACTUAL
    rights-verified text for on disk, from Poems/<dir>/*.json (same files/shape the old
    RELIGION_MARQUEE_SOURCES dict read directly) -- never invented content, never a collection
    marked approved without a corresponding `docs/marquee_religious_text_sources.md` entry.
    Called from ensure_tables()'s one caller in tools/run_migrations.py, so it runs on every app
    boot; every INSERT below is slug-keyed and idempotent (see _seed_collection)."""
    for tid, display_name, default_label, default_language, sort_order in _TRADITIONS:
        if not conn.execute("SELECT 1 FROM religious_traditions WHERE id = ?", (tid,)).fetchone():
            conn.execute(
                "INSERT INTO religious_traditions (id, display_name, default_label, default_language, sort_order) "
                "VALUES (?,?,?,?,?)",
                (tid, display_name, default_label, default_language, sort_order),
            )
    conn.commit()

    poems_dir = BASE_DIR / "Poems"

    # Hindu: original Qumanity Ram-bhakti poems (2026-11-01) -- NOT a translation of anything,
    # see Poems/hindu_original/README.md. The reserved Poems/hindu/ rights-cleared-edition slot
    # remains empty; no Gita Press/Vinaya Patrika collection is seeded here because no verified
    # publication permission exists anywhere in this repository (confirmed again this task --
    # see docs/marquee_religious_text_sources.md's Hindu section).
    _seed_collection(
        conn, tradition_id="hindu", slug="hindu_original",
        display_title="मौलिक राम-भक्ति कविताएँ", is_original_work=True,
        source_book=None, author_or_translator="Qumanity", publisher="Qumanity",
        source_url=None, edition="2026-11-01",
        rights_status="public_domain",  # original authorship, not third-party text at all
        attribution_text="Original Qumanity Hindi poetry, composed 2026-11-01.",
        license_notes="Newly-written original composition; not a translation or adaptation of any copyrighted work.",
        review_status="approved", marquee_eligible=True, sort_order=0,
        languages=[
            {"code": "hi", "display_name": "हिन्दी", "script_direction": "ltr", "is_original_language": True,
             "entries_path": poems_dir / "hindu_original" / "poems_hindi.json"},
        ],
    )

    # Christian: Psalms, King James Version (English, public domain, 1611) + a short Hindi
    # selection from Biblica's Open Hindi Contemporary Version (CC BY-SA 4.0, added 2026-11-02).
    # One collection row, two languages -- same "one collection, multiple language editions"
    # pattern already used for Buddhist's Pali+English Dhammapada, not a second Christian
    # collection row (which resolve_collection() would never reach, since it resolves exactly one
    # collection per religion by sort_order). English remains sort-order/`is_original_language`
    # first, so it stays the Christian default language -- selecting Hindi is an explicit reader
    # choice, never automatic. attribution_text/license_notes below cover BOTH languages' own,
    # genuinely different rights situations explicitly, since those two columns are per-collection,
    # not per-language, and must never understate either one.
    _seed_collection(
        conn, tradition_id="christian", slug="christian_psalms_kjv",
        # display_title is collection-level, not per-language (the schema's own real limit -- see
        # this task's own "do not redesign the database" boundary), so it stays the existing,
        # already-tested English edition name exactly as before this change; the Hindi edition's
        # own name is fully disclosed in attribution_text instead, which the API also returns.
        display_title="Psalms, King James Version", is_original_work=False,
        source_book="Psalms", author_or_translator="King James Version (1611); Biblica Open Hindi Contemporary Version",
        publisher=None, source_url="https://ebible.org/hincv/copyright.htm", edition="1611 KJV (English); Biblica Open Hindi CV, © 1978/2009/2016/2019 (Hindi)",
        rights_status="cc_licensed",  # the stricter of the two languages' own terms -- see license_notes
        attribution_text="English: Psalms, King James Version (1611) -- public domain, no attribution required. "
                          "Hindi: Biblica Open Hindi Contemporary Version, licensed CC BY-SA 4.0 "
                          "(creativecommons.org/licenses/by-sa/4.0/). The original work by Biblica, Inc. is "
                          "available for free at www.biblica.com and open.bible. Eight verses selected and "
                          "reformatted by Qumanity -- a derivative use under that license, so this text is "
                          "credited with the license's own derivative-work wording above rather than the "
                          "Biblica trademark symbol, which is deliberately not reproduced here.",
        license_notes="English (KJV): public domain worldwide, no conditions. Hindi (Biblica Open Hindi CV): "
                       "CC BY-SA 4.0, re-verified directly at ebible.org/hincv/copyright.htm 2026-11-02 -- "
                       "conditions are attribution, share-alike on any redistribution of this JSON file, and "
                       "(since this is a derivative/selected-and-reformatted use, not a verbatim full copy) "
                       "using the license's own derivative-work attribution wording in place of the Biblica "
                       "trademark symbol, which this project deliberately never reproduces. See "
                       "Poems/christian/README.md and Poems/christian/hindi_biblica/README.md.",
        review_status="approved", marquee_eligible=True, sort_order=0,
        languages=[
            {"code": "en", "display_name": "English", "script_direction": "ltr", "is_original_language": True,
             "entries_path": poems_dir / "christian" / "psalms_kjv_en.json"},
            {"code": "hi", "display_name": "हिन्दी", "script_direction": "ltr", "is_original_language": False,
             "translator_name": "Biblica, Inc. (Open Hindi Contemporary Version)",
             "entries_path": poems_dir / "christian" / "hindi_biblica" / "poems_hindi.json"},
        ],
    )

    # Buddhist: Dhammapada, Ch. 1 (Yamakavagga) vv. 1-5 -- Pali root text (public domain) and
    # F. Max Muller's 1881 English translation (public domain, Project Gutenberg eBook #2017).
    # A Hindi translation was researched and explicitly NOT included: no genuinely public-domain
    # or openly-licensed Hindi Dhammapada translation could be confirmed -- see
    # docs/marquee_religious_text_sources.md. The Pali finding carries one open condition (manual
    # re-confirmation of suttacentral.net/licensing, a JS page that could not be fetched directly
    # this session) -- recorded in license_notes below and in docs/marquee_religious_text_sources.md,
    # not hidden by marking this collection approved outright without that caveat on record.
    _seed_collection(
        conn, tradition_id="buddhist", slug="buddhist_dhammapada",
        display_title="Dhammapada", is_original_work=False,
        source_book="Dhammapada, Ch. 1 Yamakavagga", author_or_translator="F. Max Müller (English); Pali root text",
        publisher="Project Gutenberg eBook #2017 (English); SuttaCentral.net (Pali)",
        source_url="https://www.gutenberg.org/ebooks/2017 ; https://suttacentral.net/",
        edition="Müller 1881 (Sacred Books of the East Vol. X); SuttaCentral Mahāsaṅgīti/Chaṭṭha Saṅgāyana Pali edition",
        rights_status="public_domain",
        attribution_text="Pali text: Mahāsaṅgīti (Chaṭṭha Saṅgāyana) edition, via SuttaCentral.net — public domain. "
                          "English translation: F. Max Müller (1881), Sacred Books of the East Vol. X — public domain "
                          "(Project Gutenberg eBook #2017).",
        license_notes="English (Müller/Gutenberg): high confidence, no open conditions. Pali (SuttaCentral): "
                       "public-domain claim corroborated via SuttaCentral's own bilara-data GitHub README and a "
                       "mirror of their copyright page, but the live suttacentral.net/licensing page is a "
                       "JS single-page app that could not be fetched directly this session -- condition: a human "
                       "should open it directly once before this collection is treated as fully closed-out.",
        review_status="approved", marquee_eligible=True, sort_order=0,
        languages=[
            {"code": "pi", "display_name": "Pāli", "script_direction": "ltr", "is_original_language": True,
             "entries_path": poems_dir / "buddhist" / "dhammapada_pi" / "pali.json"},
            {"code": "en", "display_name": "English", "script_direction": "ltr", "is_original_language": False,
             "translator_name": "F. Max Müller (1881)",
             "entries_path": poems_dir / "buddhist" / "dhammapada_en" / "english_muller.json"},
        ],
    )

    # Muslim: Quran, Surah Al-Fatiha (Surah 1), all 7 ayahs, Arabic Uthmani Mushaf script only.
    # Tanzil Project's own license page (tanzil.net/docs/Text_License, fetched directly this
    # session): CC BY 3.0, verbatim-only (no modification), attribution + link to tanzil.net
    # required -- all satisfied by this collection's own attribution_text and Poems/muslim/README.md.
    # Urdu translation was explicitly NOT included: Tanzil's translations terms page carries an
    # ambiguous redistribution clause that was not resolved this session -- see
    # docs/marquee_religious_text_sources.md. No filesystem path or JSON file exists for Urdu.
    _seed_collection(
        conn, tradition_id="muslim", slug="muslim_quran_tanzil_arabic",
        display_title="القرآن الكريم — سورة الفاتحة", is_original_work=False,
        source_book="Quran, Surah 1 (Al-Fatiha)", author_or_translator="Uthmani Mushaf (original Arabic)",
        publisher="Tanzil Project", source_url="https://tanzil.net/docs/Text_License",
        edition="Tanzil Uthmani Mushaf text",
        rights_status="cc_licensed",
        attribution_text="Quran text: Tanzil Project (tanzil.net), Uthmani Mushaf, CC BY 3.0.",
        license_notes="CC BY 3.0 per tanzil.net/docs/Text_License, fetched directly this session. Conditions: "
                       "verbatim text only (no modification/re-segmentation), visible 'Tanzil Project' credit, "
                       "a clickable link to tanzil.net, standing (not one-time) attribution -- all met by this "
                       "collection's attribution_text and Poems/muslim/README.md. High confidence.",
        review_status="approved", marquee_eligible=True, sort_order=0,
        languages=[
            {"code": "ar", "display_name": "العربية", "script_direction": "rtl", "is_original_language": True,
             "entries_path": poems_dir / "muslim" / "quran_ar" / "alfatiha.json"},
        ],
    )

    # Sikh: research came back pending_rights_review (no confirmed-safe source found for either
    # the Gurmukhi text or any named translation; one source explicitly states "all rights
    # reserved", another explicitly states they withhold open redistribution rights) -- no
    # collection row is created for Sikh at all, so list_available_traditions() correctly omits it
    # from the Religion Selector and resolve_collection("sikh", ...) correctly returns None
    # (api_poems_meta's "coming_soon" path, same as any other content-less tradition). See
    # docs/marquee_religious_text_sources.md.


def resolve_collection(conn, religion: str, requested_language: str | None = None):
    """The ONE place `religion` (always server-trusted or allowlist-checked -- see app.py) is
    turned into real, servable content. Returns None if this tradition has no eligible collection
    yet (api_poems_meta's existing "coming_soon" path). Returns a dict:
        {collection_id, title, is_original_work, attribution, languages: [...], resolved_language}
    `languages` is the collection's own real available languages (content-driven, exactly what the
    Language Selector may offer) -- NEVER padded with a signed-in member's account languages the
    way the pre-2026-11-02 code did, since that would let the selector claim a language exists
    when no collection backs it (2.3's own explicit rule)."""
    row = conn.execute(
        """SELECT id, display_title, is_original_work, attribution_text FROM text_collections
           WHERE tradition_id = ? AND review_status = 'approved' AND marquee_eligible = 1
           ORDER BY sort_order LIMIT 1""",
        (religion,),
    ).fetchone()
    if not row:
        return None
    langs = conn.execute(
        """SELECT language_code, display_name, script_direction, is_original_language
           FROM text_collection_languages WHERE collection_id = ? ORDER BY is_original_language DESC, language_code""",
        (row["id"],),
    ).fetchall()
    lang_list = [{"code": l["language_code"], "label": l["display_name"], "dir": l["script_direction"],
                  "available": True} for l in langs]
    codes = {l["code"] for l in lang_list}
    resolved_language = requested_language if requested_language in codes else None
    if not resolved_language:
        # lang_list is already ordered original-language-first (the SQL query's own ORDER BY) --
        # take its first entry, never `next(iter(codes))`, since `codes` is a set and Python sets
        # do NOT preserve insertion order, which silently broke this exact original-language-first
        # guarantee (caught live in browser verification, 2026-11-02).
        resolved_language = lang_list[0]["code"] if lang_list else None
    return {
        "collection_id": row["id"], "title": row["display_title"],
        "is_original_work": bool(row["is_original_work"]), "attribution": row["attribution_text"],
        "languages": lang_list, "resolved_language": resolved_language,
    }


def entries(conn, collection_id: int, language_code: str):
    """[{id, marker, text}], ordinal-ordered -- same shape the old _poems() returned from JSON, so
    app.py's api_poem()/api_poems_meta() callers need no shape change."""
    cl = conn.execute(
        "SELECT id FROM text_collection_languages WHERE collection_id = ? AND language_code = ?",
        (collection_id, language_code),
    ).fetchone()
    if not cl:
        return None
    rows = conn.execute(
        "SELECT ordinal AS id, marker, text, external_ref FROM text_entries "
        "WHERE collection_language_id = ? ORDER BY ordinal", (cl["id"],),
    ).fetchall()
    return [{"id": r["id"], "marker": r["marker"], "text": r["text"], "external_ref": r["external_ref"]} for r in rows]


def list_available_traditions(conn):
    """[{code, display_name, default_label, default_language}] -- ONLY traditions with at least
    one approved+eligible collection, ordered for the Religion Selector dropdown. A tradition the
    profile religion dropdown accepts but with no eligible collection yet (e.g. muslim/sikh/
    buddhist until their own research clears) is deliberately absent here -- 2.3's own rule that a
    user can never select a religion with no real content behind it."""
    rows = conn.execute(
        """SELECT DISTINCT rt.id, rt.display_name, rt.default_label, rt.default_language, rt.sort_order
           FROM religious_traditions rt
           JOIN text_collections tc ON tc.tradition_id = rt.id
           WHERE tc.review_status = 'approved' AND tc.marquee_eligible = 1
           ORDER BY rt.sort_order""",
    ).fetchall()
    return [{"code": r["id"], "display_name": r["display_name"], "default_label": r["default_label"],
             "default_language": r["default_language"]} for r in rows]


def tradition_label(conn, religion: str) -> str | None:
    row = conn.execute("SELECT default_label FROM religious_traditions WHERE id = ?", (religion,)).fetchone()
    return row["default_label"] if row else None
