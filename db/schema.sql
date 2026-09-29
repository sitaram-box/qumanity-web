-- Qumanity prototype DB — zodiac, kundali, and elemental architecture.
-- SQLite. Registration wasn't persisted before this; `users` is the
-- minimal table this phase needs it to be, not the full account system.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    gender TEXT NOT NULL,
    dob TEXT NOT NULL,              -- ISO date "YYYY-MM-DD"
    tob TEXT NOT NULL,              -- "HH:MM", 24h
    language TEXT,
    birth_location_json TEXT NOT NULL,   -- {continent, country, state?, zone?, lat, lng}
    present_location_json TEXT NOT NULL, -- same shape
    private_id TEXT,                -- placeholder until Part 4's ID format is implemented
    account_id TEXT,
    email TEXT,                     -- for communication only (password reset, notifications) — NOT the login identifier
    phone TEXT,                     -- for communication only, same as email — optional
    password_hash TEXT,             -- werkzeug generate_password_hash; login is by private_id + password
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS zodiac_signs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,      -- Aries, Taurus, ...
    element TEXT NOT NULL,          -- Fire, Earth, Air, Water
    symbol TEXT,
    start_date TEXT,                -- "03-21" (tropical, MM-DD)
    end_date TEXT,                  -- "04-19"
    nakshatras TEXT,                -- JSON list of nakshatra names starting in this sign
    ruling_planet TEXT
);

CREATE TABLE IF NOT EXISTS nakshatras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,      -- Ashwini, Bharani, ...
    nakshatra_index INTEGER NOT NULL, -- 0-26, in zodiac order
    zodiac_id INTEGER,              -- sign the nakshatra STARTS in (sidereal); some straddle a sign boundary
    start_degree REAL,              -- sidereal longitude, 0-360
    end_degree REAL,
    ruling_planet TEXT,             -- Vimshottari dasha lord
    FOREIGN KEY (zodiac_id) REFERENCES zodiac_signs(id)
);

CREATE TABLE IF NOT EXISTS user_zodiac (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    sun_sign TEXT NOT NULL,         -- tropical (Western date-range convention, per spec Part 3)
    sun_element TEXT NOT NULL,
    moon_sign TEXT,                 -- sidereal (Lahiri), from kundali
    moon_nakshatra TEXT,
    moon_nakshatra_pada INTEGER,
    ascendant_sign TEXT,            -- sidereal
    birth_chart JSON,               -- full generate_kundali() output
    kundali_summary TEXT,
    planetary_positions JSON,
    ephemeris_mode TEXT DEFAULT 'moshier-sidereal-lahiri',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS user_elemental_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    fire_balance INTEGER DEFAULT 0,
    earth_balance INTEGER DEFAULT 0,
    air_balance INTEGER DEFAULT 0,
    water_balance INTEGER DEFAULT 0,
    space_balance INTEGER DEFAULT 0, -- always 0 for an individual; Space has no zodiac signs (see elemental_core.py)
    dominant_element TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS location_elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,      -- e.g. "CS.DL", "O_AS_IND", "O_AS", "EARTH"
    location_type TEXT NOT NULL,    -- village, tehsil, district, state, zone, country, continent, earth
    fire_count INTEGER DEFAULT 0,
    earth_count INTEGER DEFAULT 0,
    air_count INTEGER DEFAULT 0,
    water_count INTEGER DEFAULT 0,
    space_count INTEGER DEFAULT 0,
    total_users INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (location_id, location_type)
);

-- Populated separately by scripts/import_india_villages.py (621,057 rows —
-- too large to ship as one static JSON like india_districts_tehsils.json,
-- so it's queried per-tehsil, indexed, on demand instead).
CREATE TABLE IF NOT EXISTS india_villages (
    id TEXT PRIMARY KEY,             -- e.g. "CS.DL.1.1.1"
    tehsil_id TEXT NOT NULL,         -- e.g. "CS.DL.1.1"
    name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_india_villages_tehsil ON india_villages(tehsil_id);

CREATE TABLE IF NOT EXISTS lunar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,       -- New Moon, Full Moon, Solar Eclipse, Lunar Eclipse
    date TEXT NOT NULL,             -- ISO date, UTC
    time TEXT,                      -- "HH:MM", UTC
    zodiac_sign TEXT,               -- sidereal sign the Moon/eclipse occupies
    nakshatra TEXT,
    description TEXT,
    is_visible_in_india BOOLEAN DEFAULT 0
);

-- Karma Qoins wallets: one per user (owner_type='user', owner_id=users.id as
-- text) and one per location at every tier from Earth to Village
-- (owner_type=location_elements.location_type, owner_id=location_elements.
-- location_id — same id values, so a location's wallet and its demographic
-- row share a key). 1 Qoin = ₹1 (see wallet_core.py; the old prototype's
-- encrypted per-denomination coin breakdown is intentionally not carried
-- over — flat integer balance is enough for this prototype).
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL,       -- 'user' | earth | continent | country | zone | state | district | tehsil | village
    owner_id TEXT NOT NULL,
    balance_qoins INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_type, owner_id)
);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    amount_qoins INTEGER NOT NULL,  -- signed
    reason TEXT NOT NULL,           -- donation_self | donation_referrer | donation_location | admin_adjustment
    locked INTEGER NOT NULL DEFAULT 0, -- 1 = not yet added to balance_qoins (a new user's own donation share, held until their first election vote — see wallet_core.unlock_user_share)
    related_user_id INTEGER,        -- the user whose donation/action caused this entry, if any
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wallet_id) REFERENCES wallets(id),
    FOREIGN KEY (related_user_id) REFERENCES users(id)
);

-- Village Council elections — piloted on ONE village (election_core.
-- PILOT_VILLAGE_ID) for this pass. Each zodiac sign gets its own ~1-month
-- cycle (nomination week, then a voting window) electing one Male "Nayak"
-- and one Female "Nayika" for that sign's council seat.
CREATE TABLE IF NOT EXISTS election_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id TEXT NOT NULL,
    zodiac_sign TEXT NOT NULL,
    element TEXT NOT NULL,
    year INTEGER NOT NULL,          -- the year the cycle's nomination window starts in
    nomination_start TEXT NOT NULL, -- ISO date
    nomination_end TEXT NOT NULL,
    voting_start TEXT NOT NULL,
    voting_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'nomination', -- nomination | voting | closed
    male_winner_user_id INTEGER,
    female_winner_user_id INTEGER,
    UNIQUE (village_id, zodiac_sign, year),
    FOREIGN KEY (male_winner_user_id) REFERENCES users(id),
    FOREIGN KEY (female_winner_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS election_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    election_cycle_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    gender TEXT NOT NULL,
    manifest TEXT,                  -- why they want to stand / what they'd change
    status TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (election_cycle_id, user_id),
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS election_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    election_cycle_id INTEGER NOT NULL,
    voter_user_id INTEGER NOT NULL,
    candidate_user_id INTEGER NOT NULL,
    gender TEXT NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (election_cycle_id, voter_user_id, gender), -- one vote per voter per gender-slot per cycle
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id),
    FOREIGN KEY (voter_user_id) REFERENCES users(id),
    FOREIGN KEY (candidate_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS village_council (
    village_id TEXT NOT NULL,
    zodiac_sign TEXT NOT NULL,
    year INTEGER NOT NULL,
    male_head_user_id INTEGER,
    female_head_user_id INTEGER,
    election_cycle_id INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (village_id, zodiac_sign, year),
    FOREIGN KEY (male_head_user_id) REFERENCES users(id),
    FOREIGN KEY (female_head_user_id) REFERENCES users(id),
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id)
);
