"""Download every OpenAlex work found by the Dutch metascience search (terms.py) into the raw database.

Usage: python -I fetch_search.py <raw database.sqlite>
Stores the works in the oa_* tables and their ids in oa_search_hits. Safe to run again: works already in the
database are not stored again (storing replaces a paper's authors, which would undo the full author lists that
fetch_full_authors.py fetched for papers with more than 100 authors); only their ids are added to oa_search_hits.
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terms
from oa_store import oa_get, store, FIELDS

sys.stdout.reconfigure(encoding="utf-8")
db = sqlite3.connect(sys.argv[1])
db.execute("CREATE TABLE IF NOT EXISTS oa_search_hits (work_id TEXT PRIMARY KEY)")
cursor, n, total = "*", 0, None
known, n_known = {r[0] for r in db.execute("SELECT work_id FROM oa_works")}, 0
while cursor:
    d = oa_get("works", {"filter": terms.search_filter(), "per-page": 200, "cursor": cursor, "select": FIELDS})
    total = d["meta"]["count"]
    for w in d.get("results", []):
        wid = w["id"].split("/")[-1]
        if wid in known:
            n_known += 1
        else:
            wid = store(db, w)
            known.add(wid)
        db.execute("INSERT OR IGNORE INTO oa_search_hits VALUES (?)", (wid,))
        n += 1
    db.commit()
    cursor = d["meta"].get("next_cursor") if d.get("results") else None
    if n % 2000 < 200:
        print(f"  {n}/{total}", flush=True)
print("found:", n, "of", total, "| already in the database:", n_known, "| distinct in oa_search_hits:", db.execute("SELECT count(*) FROM oa_search_hits").fetchone()[0])
