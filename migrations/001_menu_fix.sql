-- 001_menu_fix.sql
-- Säker uppgradering av meny-schemat utan att förstöra data.

BEGIN TRANSACTION;

-- Fallback för äldre SQLite (används nu):
CREATE TABLE IF NOT EXISTS menus_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    menu_index INTEGER NOT NULL DEFAULT 0
);
INSERT INTO menus_new (id, name, description, active, menu_index)
SELECT id, name, description, COALESCE(active, 1), 0 FROM menus;
DROP TABLE menus;
ALTER TABLE menus_new RENAME TO menus;

-- 2) Skapa 'menu_days' om den saknas.
CREATE TABLE IF NOT EXISTS menu_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    dish TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(menu_id) REFERENCES menus(id) ON DELETE CASCADE
);

COMMIT;
