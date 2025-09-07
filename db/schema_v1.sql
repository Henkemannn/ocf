-- Table: menus
CREATE TABLE IF NOT EXISTS menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    menu_index INTEGER NOT NULL DEFAULT 0  -- ny kolumn för sorteringsordning
);

CREATE TABLE IF NOT EXISTS menu_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_id INTEGER NOT NULL,
    day TEXT NOT NULL,      -- t.ex. 'monday' eller datumsträng
    dish TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(menu_id) REFERENCES menus(id) ON DELETE CASCADE
);

-- Table: turnus_templates
CREATE TABLE IF NOT EXISTS turnus_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    rig_id          INTEGER,
    pattern_json    TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT,
    FOREIGN KEY(rig_id) REFERENCES rigs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_turnus_templates_rig ON turnus_templates(rig_id);
CREATE INDEX IF NOT EXISTS idx_turnus_templates_active ON turnus_templates(is_active);

-- Table: turnus_slots
CREATE TABLE IF NOT EXISTS turnus_slots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     INTEGER,
    rig_id          INTEGER NOT NULL,
    start_ts        TEXT NOT NULL,
    end_ts          TEXT NOT NULL,
    role            TEXT,
    status          TEXT NOT NULL DEFAULT 'planned',
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT,
    FOREIGN KEY(template_id) REFERENCES turnus_templates(id) ON DELETE SET NULL,
    FOREIGN KEY(rig_id) REFERENCES rigs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_turnus_slots_rig_start ON turnus_slots(rig_id, start_ts);
CREATE INDEX IF NOT EXISTS idx_turnus_slots_template ON turnus_slots(template_id);
CREATE INDEX IF NOT EXISTS idx_turnus_slots_status ON turnus_slots(status);

-- Table: turnus_account_binding
CREATE TABLE IF NOT EXISTS turnus_account_binding (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id         INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    bound_at        TEXT NOT NULL DEFAULT (datetime('now')),
    notes           TEXT,
    FOREIGN KEY(slot_id) REFERENCES turnus_slots(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(slot_id)
);
CREATE INDEX IF NOT EXISTS idx_turnus_binding_user ON turnus_account_binding(user_id);

