import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("app.db")

def connect():
    if not DB_PATH.exists():
        raise SystemExit("Hittar inte app.db i projektroten.")
    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def count(conn, table, where=None, params=()):
    q = f"SELECT COUNT(*) AS n FROM {table}"
    if where:
        q += f" WHERE {where}"
    return conn.execute(q, params).fetchone()["n"]

def delete(conn, table, where=None, params=()):
    if where:
        q = f"DELETE FROM {table} WHERE {where}"
    else:
        q = f"DELETE FROM {table}"
    cur = conn.execute(q, params)
    return cur.rowcount

def parse_args():
    p = argparse.ArgumentParser(
        description="Reset av turnusdata (rör inte menyer).",
        epilog=(
            "Exempel:\n"
            "  # Torka allt turnus (kräver --yes)\n"
            "  python tools/turnus_reset.py --all --yes\n\n"
            "  # Rensa bara framtida slots (från och med idag), per rigg\n"
            "  python tools/turnus_reset.py --only-future --rig-id 1 --yes\n\n"
            "  # Rensa slots men behåll publicerade\n"
            "  python tools/turnus_reset.py --slots --keep-published --yes\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="Rensa ALL turnusdata (bindings, slots, templates).")
    scope.add_argument("--slots", action="store_true", help="Rensa endast slots (+ bindings).")
    scope.add_argument("--bindings", action="store_true", help="Rensa endast bindings.")
    scope.add_argument("--templates", action="store_true", help="Rensa endast templates (kräver tomma/inga slots).")

    p.add_argument("--rig-id", type=int, help="Begränsa rensning till en specifik rigg.")
    p.add_argument("--only-future", action="store_true", help="Rensa bara framtida slots (start_ts >= idag 00:00).")
    p.add_argument("--from", dest="from_date", help="Rensa slots med start_ts >= YYYY-MM-DD (överskriver --only-future).")
    p.add_argument("--keep-published", action="store_true", help="Behåll publicerade slots (status='published').")
    p.add_argument("--yes", action="store_true", help="Kräv inte interaktiv bekräftelse.")
    p.add_argument("--dry-run", action="store_true", help="Visa vad som skulle rensas, ändra inget.")
    return p.parse_args()

def main():
    args = parse_args()
    conn = connect()

    # Bygg filter
    slot_where = []
    params = []

    if args.rig_id is not None:
        slot_where.append("rig_id = ?")
        params.append(args.rig_id)

    if args.from_date:
        # validera datum
        try:
            datetime.strptime(args.from_date, "%Y-%m-%d")
        except ValueError:
            raise SystemExit("Fel format på --from, använd YYYY-MM-DD")
        slot_where.append("start_ts >= ?")
        params.append(args.from_date + "T00:00")
    elif args.only_future:
        today = datetime.now().strftime("%Y-%m-%d")
        slot_where.append("start_ts >= ?")
        params.append(today + "T00:00")

    if args.keep_published:
        slot_where.append("status <> 'published'")

    # Räkna vad som påverkas
    slot_filter = " AND ".join(slot_where) if slot_where else None

    # Bindings påverkas indirekt via slots (CASCADE), men vi kan även rikta dem specifikt
    bind_where = None
    bind_params = ()
    if slot_filter:
        # Bindings per slot i urvalet (subquery)
        bind_where = f"slot_id IN (SELECT id FROM turnus_slots WHERE {slot_filter})"
        bind_params = tuple(params)

    # Templates tas bara om --all eller --templates, och endast säkert om inga slots hänger på dem (CASCADE ej satt)
    # Vi låter dem stå kvar om det finns slots kopplade.

    # Summering:
    total_bindings = count(conn, "turnus_account_binding")
    total_slots = count(conn, "turnus_slots")
    total_templates = count(conn, "turnus_templates")

    if args.bindings or args.slots or args.all:
        eff_bindings = count(conn, "turnus_account_binding", bind_where, bind_params) if bind_where else total_bindings
        eff_slots = count(conn, "turnus_slots", slot_filter, tuple(params)) if (args.slots or args.all) else 0
    else:
        eff_bindings = 0
        eff_slots = 0

    if args.templates or args.all:
        # Endast templates utan slots (samma riggfilter om satt)
        tmpl_where = "id NOT IN (SELECT DISTINCT template_id FROM turnus_slots WHERE template_id IS NOT NULL)"
        tmpl_params = []
        if args.rig_id is not None:
            tmpl_where += " AND (rig_id = ? OR rig_id IS NULL)"
            tmpl_params.append(args.rig_id)
        eff_templates = count(conn, "turnus_templates", tmpl_where, tuple(tmpl_params))
    else:
        eff_templates = 0

    print("=== RESET PLAN ===")
    print(f"Bindings total: {total_bindings}  -> rensas: {eff_bindings}")
    print(f"Slots    total: {total_slots}      -> rensas: {eff_slots}")
    print(f"Templates total: {total_templates} -> rensas: {eff_templates}")
    if args.rig_id is not None:
        print(f"Filter: rig_id = {args.rig_id}")
    if args.from_date:
        print(f"Filter: start_ts >= {args.from_date}T00:00")
    elif args.only_future:
        print("Filter: only future (start_ts >= idag 00:00)")
    if args.keep_published:
        print("Filter: keep_published = True (publicerade behålls)")
    if args.dry_run:
        print("DRY RUN: Ingen förändring kommer göras.")

    if not args.yes:
        resp = input("Bekräfta reset (skriv 'JA' för att fortsätta): ").strip()
        if resp != "JA":
            print("Avbrutet.")
            return

    if args.dry_run:
        print("Avslutar (dry run).")
        return

    # Utför rensning (ordning: bindings -> slots -> templates)
    with conn:
        # Bindings
        if args.bindings or args.slots or args.all:
            if bind_where:
                n = delete(conn, "turnus_account_binding", bind_where, bind_params)
            else:
                n = delete(conn, "turnus_account_binding")
            print(f"Raderade bindings: {n}")

        # Slots
        if args.slots or args.all:
            n = delete(conn, "turnus_slots", slot_filter, tuple(params)) if slot_filter else delete(conn, "turnus_slots")
            print(f"Raderade slots: {n}")

        # Templates (endast de som saknar slots)
        if args.templates or args.all:
            # Radera endast templates utan slots
            tmpl_where = "id NOT IN (SELECT DISTINCT template_id FROM turnus_slots WHERE template_id IS NOT NULL)"
            tmpl_params = []
            if args.rig_id is not None:
                tmpl_where += " AND (rig_id = ? OR rig_id IS NULL)"
                tmpl_params.append(args.rig_id)
            n = delete(conn, "turnus_templates", tmpl_where, tuple(tmpl_params))
            print(f"Raderade templates (utan slots): {n}")

    print("Klar.")

if __name__ == "__main__":
    main()
