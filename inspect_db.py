import sqlite3, os, json
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jobs.db")
c = sqlite3.connect(p)
tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print("tables:", tables)
for t in tables:
    try:
        n = c.execute(f"select count(*) from {t}").fetchone()[0]
        print(f"{t}: {n}")
    except Exception as e:
        print(t, "err", e)
print("--- sample jobs ---")
try:
    cols = [r[1] for r in c.execute("PRAGMA table_info(jobs)")]
    print("cols:", cols)
    for row in c.execute("select id,title,company,location,score,status from jobs limit 10"):
        print(row)
except Exception as e:
    print("jobs err", e)
