-- 001b_add_description_to_menus.sql
-- Lägg till kolumnen 'description' i tabellen 'menus' om den saknas
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;
ALTER TABLE menus ADD COLUMN description TEXT;
COMMIT;
