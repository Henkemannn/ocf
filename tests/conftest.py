import os
import sqlite3
import tempfile
import pathlib
import json
import pytest

# Lägg till projektroten i sys.path så att rotation.py hittas
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import rotation  # vi monkeypatchar DB_PATH
# Viktigt: app importeras efter att DB_PATH är satt i varje test via fixture

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- Minimal schema för testerna (rör inte menyerna)
CREATE TABLE IF NOT EXISTS rigs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT
);

CREATE TABLE IF NOT EXISTS turnus_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  rig_id INTEGER,
  pattern_json TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  FOREIGN KEY(rig_id) REFERENCES rigs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS turnus_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER,
  rig_id INTEGER NOT NULL,
  start_ts TEXT NOT NULL,
  end_ts TEXT NOT NULL,
  role TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  FOREIGN KEY(template_id) REFERENCES turnus_templates(id) ON DELETE SET NULL,
  FOREIGN KEY(rig_id) REFERENCES rigs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS turnus_account_binding (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slot_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  bound_at TEXT NOT NULL DEFAULT (datetime('now')),
  notes TEXT,
  FOREIGN KEY(slot_id) REFERENCES turnus_slots(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE(slot_id)
);
"""

@pytest.fixture
def tmp_db_path(tmp_path, monkeypatch):
    """Skapar en temporär sqlite-fil och initierar testschemat."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path.as_posix())
    conn.executescript(SCHEMA_SQL)
    # seed: en rigg + en user
    conn.execute("INSERT INTO rigs(name) VALUES ('TestRig')")
    conn.execute("INSERT INTO users(name) VALUES ('Anna')")
    conn.commit()
    conn.close()

    # Peka rotation mot denna DB
    monkeypatch.setattr(rotation, "DB_PATH", db_path)
    return db_path

@pytest.fixture
def app_client(tmp_db_path):
    """Flask testklient med appen importerad efter DB-patch."""
    # Importera app EFTER att rotation.DB_PATH pekar på temp-db
    import importlib
    app_module = importlib.import_module("app")
    app = app_module.app if hasattr(app_module, "app") else app_module
    app.testing = True
    return app.test_client()
