-- Skapar alla tabeller som används av appen

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    password_hash TEXT,
    tenant_id INTEGER,
    role TEXT,
    rig_id INTEGER
);

CREATE TABLE IF NOT EXISTS rigs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    menu_start_index INTEGER,
    menu_start_week INTEGER,
    menu_start_date TEXT
);

CREATE TABLE IF NOT EXISTS menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS menu_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    menu_index INTEGER NOT NULL CHECK(menu_index BETWEEN 1 AND 4),
    UNIQUE(tenant_id, iso_year, iso_week)
);

CREATE TABLE IF NOT EXISTS day_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    work_cycle_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    menu_index INTEGER NOT NULL,
    done INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prep_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_instance_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    done INTEGER DEFAULT 0,
    type TEXT CHECK(type IN ('prep','frysplock')) NOT NULL
);

-- Lägg till fler tabeller här om appen kräver det
