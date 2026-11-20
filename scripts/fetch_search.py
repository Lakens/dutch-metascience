"""Download every OpenAlex work found by the Dutch metascience search (terms.py) into the raw database.

Usage: python -I fetch_search.py <raw database.sqlite>
Stores the works in the oa_* tables and their ids in oa_search_hits. Safe to run again.
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terms
from oa_store import oa_get, store, FIELDS

sys.stdout.reconfigure(encoding="utf-8")
db = sqlite3.connect(sys.argv[1])
db.execute("CREATE TABLE IF NOT EXISTS oa_search_hits (work_id TEXT PRIMARY KEY)")
cursor, n, total = "*", 0, None
while cursor:
    d = oa_get("works", {"filter": terms.search_filter(), "per-page": 200, "cursor": cursor, "select": FIELDS})
    total = d["meta"]["count"]
    for w in d.get("results", []):
        wid = store(db, w)
        db.execute("INSERT OR IGNORE INTO oa_search_hits VALUES (?)", (wid,))
        n += 1
    db.commit()
    cursor = d["meta"].get("next_cursor") if d.get("results") else None
    if n % 2000 < 200:
        print(f"  {n}/{total}", flush=True)
print("stored:", n, "of", total, "| distinct in oa_search_hits:", db.execute("SELECT count(*) FROM oa_search_hits").fetchone()[0])
