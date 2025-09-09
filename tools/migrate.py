import sqlite3, pathlib, sys

DB = pathlib.Path("app.db")
MIG = pathlib.Path("migrations/001_menu_fix.sql")
if not DB.exists():
    print("Hittar inte app.db i projektroten.")
    sys.exit(1)
if not MIG.exists():
    print("Hittar inte migrations/001_menu_fix.sql.")
    sys.exit(1)
conn = sqlite3.connect(DB.as_posix())
with open(MIG, "r", encoding="utf-8") as f:
    sql = f.read()
    conn.executescript(sql)
conn.commit()
conn.close()
print("Klar: migrationen är körd.")
