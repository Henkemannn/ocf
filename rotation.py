# rotation.py
# Ny, fristående modul för turnus-logik.
# Använder SQLite (app.db) och tabeller som skapades i Steg 4:
#   turnus_templates, turnus_slots, turnus_account_binding
#
# OBS: Denna modul rör INTE menydelen.

import sqlite3
import json
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any, Iterable
from pathlib import Path

DB_PATH = Path("app.db")

# ---------- Hjälpfunktioner ----------
def _conn():
    if not DB_PATH.exists():
        raise RuntimeError("Hittar inte app.db i projektroten.")
    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    # Säkerställ FK-stöd i SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def _iso(dt: datetime) -> str:
    # ISO8601 utan timezone (vi antar lokal/UTC-hantering i appen)
    return dt.strftime("%Y-%m-%dT%H:%M")

def _parse_date(d: str) -> date:
    # Tillåt 'YYYY-MM-DD'
    return datetime.strptime(d, "%Y-%m-%d").date()

def _parse_time(t: str) -> timedelta:
    # 'HH:MM' -> timedelta
    hh, mm = t.split(":")
    return timedelta(hours=int(hh), minutes=int(mm))

def _daterange(d0: date, d1: date) -> Iterable[date]:
    # Inklusive d1
    cur = d0
    while cur <= d1:
        yield cur
        cur = cur + timedelta(days=1)

# ---------- Templates ----------
def create_template(name: str, pattern: Dict[str, Any], rig_id: Optional[int] = None, is_active: bool = True) -> int:
    """
    Skapa en template.
    pattern: JSON-struktur, ex:
    {
      "weekly": [
        {"weekday": 0, "start": "07:00", "end": "19:00", "role": "dag"},
        {"weekday": 1, "start": "19:00", "end": "07:00", "role": "natt"},
        ...
      ]
    }
    weekday: 0=måndag ... 6=söndag
    """
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO turnus_templates (name, rig_id, pattern_json, is_active, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (name, rig_id, json.dumps(pattern), 1 if is_active else 0)
        )
    return cur.lastrowid if cur.lastrowid is not None else -1

def update_template(template_id: int, *, name: Optional[str] = None,
                    pattern: Optional[Dict[str, Any]] = None,
                    rig_id: Optional[int] = None,
                    is_active: Optional[bool] = None) -> None:
    fields = []
    values = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if rig_id is not None:
        fields.append("rig_id = ?")
        values.append(rig_id)
    if pattern is not None:
        fields.append("pattern_json = ?")
        values.append(json.dumps(pattern))
    if is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if is_active else 0)
    if not fields:
        return
    fields.append("updated_at = datetime('now')")
    with _conn() as conn:
        conn.execute(f"UPDATE turnus_templates SET {', '.join(fields)} WHERE id = ?", (*values, template_id))

def set_template_active(template_id: int, active: bool) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE turnus_templates SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if active else 0, template_id)
        )

def get_template(template_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM turnus_templates WHERE id = ?", (template_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["pattern"] = json.loads(d.pop("pattern_json") or "{}")
        return d

def list_templates(rig_id: Optional[int] = None, active_only: bool = False) -> List[Dict[str, Any]]:
    q = "SELECT * FROM turnus_templates"
    where = []
    params: List[Any] = []
    if rig_id is not None:
        where.append("rig_id = ?")
        params.append(rig_id)
    if active_only:
        where.append("is_active = 1")
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC"
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["pattern"] = json.loads(d.pop("pattern_json") or "{}")
            out.append(d)
        return out

# ---------- Slots ----------
def generate_slots_from_template(template_id: int, start_date: str, end_date: str, rig_id_override: Optional[int] = None) -> int:
    """
    Generera slots från en template över ett datumintervall (inklusive end_date).
    Returnerar antal skapade slots.
    """
    tmpl = get_template(template_id)
    if not tmpl:
        raise ValueError("Template saknas")
    pattern = tmpl.get("pattern") or {}
    weekly = pattern.get("weekly") or []
    if not weekly:
        return 0

    rig_id = rig_id_override if rig_id_override is not None else tmpl.get("rig_id")
    if rig_id is None:
        raise ValueError("rig_id krävs (i template eller override)")

    d0 = _parse_date(start_date)
    d1 = _parse_date(end_date)

    to_insert: List[tuple] = []
    for d in _daterange(d0, d1):
        wd = (d.weekday())  # måndag=0..söndag=6 (matchar vårt antagande)
        # matcha alla regler för veckodagen
        for rule in weekly:
            if int(rule.get("weekday", -1)) != wd:
                continue
            start_td = _parse_time(rule["start"])
            end_td = _parse_time(rule["end"])

            start_dt = datetime(d.year, d.month, d.day) + start_td
            end_dt = datetime(d.year, d.month, d.day) + end_td
            # Om sluttiden är före start (t.ex. natt), rulla till nästa dag
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            role = rule.get("role")
            to_insert.append((
                template_id,
                rig_id,
                _iso(start_dt),
                _iso(end_dt),
                role or None,
                "planned",
                None  # notes
            ))

    if not to_insert:
        return 0

    with _conn() as conn:
        conn.executemany(
            """INSERT INTO turnus_slots
               (template_id, rig_id, start_ts, end_ts, role, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            to_insert
        )
        return conn.total_changes

def list_slots(*,
               template_id: Optional[int] = None,
               rig_id: Optional[int] = None,
               status: Optional[str] = None,
               from_ts: Optional[str] = None,
               to_ts: Optional[str] = None) -> List[Dict[str, Any]]:
    q = "SELECT * FROM turnus_slots"
    where = []
    params: List[Any] = []
    if template_id is not None:
        where.append("template_id = ?")
        params.append(template_id)
    if rig_id is not None:
        where.append("rig_id = ?")
        params.append(rig_id)
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if from_ts is not None:
        where.append("start_ts >= ?")
        params.append(from_ts)
    if to_ts is not None:
        where.append("end_ts <= ?")
        params.append(to_ts)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY start_ts ASC"
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

def publish_slots(slot_ids: List[int]) -> int:
    if not slot_ids:
        return 0
    placeholders = ",".join("?" for _ in slot_ids)
    with _conn() as conn:
        conn.execute(
            f"UPDATE turnus_slots SET status='published', updated_at=datetime('now') WHERE id IN ({placeholders})",
            slot_ids
        )
        return conn.total_changes

def delete_slots(slot_ids: List[int]) -> int:
    if not slot_ids:
        return 0
    placeholders = ",".join("?" for _ in slot_ids)
    with _conn() as conn:
        conn.execute(
            f"DELETE FROM turnus_slots WHERE id IN ({placeholders})",
            slot_ids
        )
        return conn.total_changes

# ---------- Binding (user ↔ slot) ----------
def bind_user_to_slot(slot_id: int, user_id: int, notes: Optional[str] = None) -> None:
    """
    Unik binding per slot (enligt schema UNIQUE(slot_id)).
    Om det redan finns en binding för slot: ta bort den först och skapa ny.
    """
    with _conn() as conn:
        conn.execute("DELETE FROM turnus_account_binding WHERE slot_id = ?", (slot_id,))
        conn.execute(
            """INSERT INTO turnus_account_binding (slot_id, user_id, notes, bound_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (slot_id, user_id, notes)
        )

def unbind_user_from_slot(slot_id: int) -> int:
    with _conn() as conn:
        conn.execute("DELETE FROM turnus_account_binding WHERE slot_id = ?", (slot_id,))
        return conn.total_changes

# ---------- Query för preview & view ----------
def preview(rig_id: int, start_ts: str, end_ts: str) -> List[Dict[str, Any]]:
        """
        Hämtar slots (alla status) i intervallet för en rigg.
        Används för /turnus/preview i Steg 6.
        """
        q = """
SELECT s.*, b.user_id, u.name AS user_name
FROM turnus_slots s
LEFT JOIN turnus_account_binding b ON b.slot_id = s.id
LEFT JOIN users u ON u.id = b.user_id
WHERE s.rig_id = ?
    AND s.start_ts < ?
    AND s.end_ts > ?
ORDER BY s.start_ts ASC
        """
        with _conn() as conn:
                rows = conn.execute(q, (rig_id, end_ts, start_ts)).fetchall()
                return [dict(r) for r in rows]

def view(rig_id: int, start_ts: str, end_ts: str) -> List[Dict[str, Any]]:
    """
    Hämtar endast publicerade slots i intervallet för en rigg.
    Används för /turnus/view i Steg 6.
    """
    q = """
    SELECT s.*, b.user_id, u.name AS user_name
    FROM turnus_slots s
    LEFT JOIN turnus_account_binding b ON b.slot_id = s.id
    LEFT JOIN users u ON u.id = b.user_id
    WHERE s.rig_id = ?
      AND s.status = 'published'
      AND s.start_ts >= ?
      AND s.end_ts <= ?
    ORDER BY s.start_ts ASC
    """
    with _conn() as conn:
        rows = conn.execute(q, (rig_id, start_ts, end_ts)).fetchall()
        return [dict(r) for r in rows]
def generate_turnus_for_cooks(
    rig_id: int,
    start_date: str,
    end_date: str,
    cook_names: list,
    snu_days: list = None,
    gap_days: list = None
) -> int:
    """
    Genererar och skriver hela turnusen för 6 kockar till databasen.
    cook_names: lista med 6 namn (virtuella kockar, kan mappas till riktiga användare)
    snu_days: lista med datumsträngar (YYYY-MM-DD) för snu-dagar
    gap_days: lista med datumsträngar (YYYY-MM-DD) för glapp (ingen kock)
    Returnerar antal skapade slots.
    """
    if len(cook_names) != 6:
        raise ValueError("Exakt 6 kockar krävs")
    snu_days = set(snu_days or [])
    gap_days = set(gap_days or [])
    d0 = _parse_date(start_date)
    d1 = _parse_date(end_date)
    days = list(_daterange(d0, d1))
    slots = []
    cook_idx = 0
    for d in days:
        ds = d.strftime('%Y-%m-%d')
        if ds in gap_days:
            continue  # Ingen kock denna dag
        if ds in snu_days:
            # Snu-dag: rotera kockarna (t.ex. hoppa till nästa)
            cook_idx = (cook_idx + 1) % 6
        cook = cook_names[cook_idx]
        start_dt = datetime(d.year, d.month, d.day, 7, 0)
        end_dt = datetime(d.year, d.month, d.day, 19, 0)
        slots.append((
            None,  # template_id
            rig_id,
            _iso(start_dt),
            _iso(end_dt),
            cook,
            "planned",
            None
        ))
        cook_idx = (cook_idx + 1) % 6
    if not slots:
        return 0
    with _conn() as conn:
        conn.executemany(
            """INSERT INTO turnus_slots
               (template_id, rig_id, start_ts, end_ts, role, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            slots
        )
        return conn.total_changes