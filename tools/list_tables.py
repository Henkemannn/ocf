import sqlite3, pathlib
db = pathlib.Path("app.db")
conn = sqlite3.connect(db.as_posix())
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(sorted([r[0] for r in cur.fetchall()]))
conn.close()
