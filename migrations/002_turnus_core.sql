-- 002_turnus_core.sql
-- Kärnschema för ny turnusmotor: templates + slots + account-binding
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- 1) Templates (admin definierar mönster här)
CREATE TABLE IF NOT EXISTS turnus_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    rig_id          INTEGER,                      -- valfritt, koppla till specifik rigg om ni vill
    pattern_json    TEXT NOT NULL,                -- beskriver veckomönster/roller etc.
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT,
    FOREIGN KEY(rig_id) REFERENCES rigs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_turnus_templates_rig ON turnus_templates(rig_id);
CREATE INDEX IF NOT EXISTS idx_turnus_templates_active ON turnus_templates(is_active);

-- 2) Slots (daterade arbetspass, kan härledas från template eller skapas manuellt)
CREATE TABLE IF NOT EXISTS turnus_slots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     INTEGER,                       -- null om manuellt skapad
    rig_id          INTEGER NOT NULL,              -- vilket objekt/rigg passet tillhör
    start_ts        TEXT NOT NULL,                 -- ISO8601: 'YYYY-MM-DDTHH:MM'
    end_ts          TEXT NOT NULL,                 -- ISO8601
    role            TEXT,                          -- t.ex. "kock", "mek", "dag", "natt"
    status          TEXT NOT NULL DEFAULT 'planned', -- 'planned' | 'published' | 'cancelled'
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT,
    FOREIGN KEY(template_id) REFERENCES turnus_templates(id) ON DELETE SET NULL,
    FOREIGN KEY(rig_id) REFERENCES rigs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_turnus_slots_rig_start ON turnus_slots(rig_id, start_ts);
CREATE INDEX IF NOT EXISTS idx_turnus_slots_template ON turnus_slots(template_id);
CREATE INDEX IF NOT EXISTS idx_turnus_slots_status ON turnus_slots(status);

-- 3) Account-binding (kopplar användare/konto till slot)
CREATE TABLE IF NOT EXISTS turnus_account_binding (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id         INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    bound_at        TEXT NOT NULL DEFAULT (datetime('now')),
    notes           TEXT,
    FOREIGN KEY(slot_id) REFERENCES turnus_slots(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(slot_id)                                    -- exakt 1 konto per slot
);

CREATE INDEX IF NOT EXISTS idx_turnus_binding_user ON turnus_account_binding(user_id);

COMMIT;
