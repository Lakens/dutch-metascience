"""Download the full author list of metascience papers whose author list OpenAlex cut off at 100.

Usage: python -I fetch_full_authors.py <raw database.sqlite>
Needs OPENALEX_API_KEY.

When OpenAlex returns many papers in one request, it gives at most the first 100 authors of each paper and marks the
paper as truncated (oa_works.authors_truncated = 1). A request for one paper gives all authors. On large team papers
(Many Labs 2 has 190 authors) the Dutch authors after position 100 were therefore missing. This script asks for each
truncated metascience paper on its own and stores it again (oa_store.store replaces its authorships and institutions).
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oa_store import oa_get, store, FIELDS

sys.stdout.reconfigure(encoding="utf-8")
db = sqlite3.connect(sys.argv[1])
todo = [w for (w,) in db.execute("""SELECT DISTINCT w.work_id FROM oa_works w JOIN llm_metascience m USING (work_id)
                                      WHERE w.authors_truncated = 1 AND m.is_metascience = 1""")]
print("truncated papers judged metascience at least once:", len(todo), flush=True)
for n, wid in enumerate(todo, 1):
    before = db.execute("SELECT count(*) FROM oa_authorships WHERE work_id=?", (wid,)).fetchone()[0]
    w = oa_get("works/" + wid, {"select": FIELDS})
    if not w:
        print(f"  {wid}: not found, left as it was"); continue
    if w.get("is_authors_truncated"):
        print(f"  {wid}: still truncated in a single request, left as it was"); continue
    store(db, w)
    after = db.execute("SELECT count(*) FROM oa_authorships WHERE work_id=?", (wid,)).fetchone()[0]
    print(f"  {n:3d}/{len(todo)} {wid}: {before} -> {after} authors", flush=True)
    db.commit()
print("left truncated:", db.execute("""SELECT count(DISTINCT w.work_id) FROM oa_works w JOIN llm_metascience m
                                       USING (work_id) WHERE w.authors_truncated = 1 AND m.is_metascience = 1""").fetchone()[0])
