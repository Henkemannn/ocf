import sqlite3, sys, pathlib

# Backup
import shutil
shutil.copy('app.db', 'app_backup_before_step2.db')

# Run SQL
db = pathlib.Path("app.db")
sqlfile = pathlib.Path("sql/step2_remove_legacy_turnus.sql")
if not db.exists(): raise SystemExit("Hittar inte app.db i projektroten.")
if not sqlfile.exists(): raise SystemExit("Hittar inte SQL-filen.")
conn = sqlite3.connect(db.as_posix())
with open(sqlfile, "r", encoding="utf-8") as f:
    conn.executescript(f.read())
conn.commit()
conn.close()
print("Klar: DROP körd utan fel.")
