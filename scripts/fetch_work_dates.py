"""Publication dates of the papers on the History timeline, so they can be placed in their month.

Usage: python -I fetch_work_dates.py <site data folder> <raw database.sqlite> <work_dates.json>
Needs OPENALEX_API_KEY (only for papers that are not in the raw database).

Reads the works on the timeline from <site data folder>/history.json (run build_history.py first). Papers in the raw
database take their publication_date from there; the others (landmark papers, known only from reference lists) are
asked from OpenAlex, 50 per request. Dates already in <work_dates.json> are kept, so a rebuild asks only for new works.
Writes {work id: "YYYY-MM-DD"}. Afterwards run build_history.py again, with <work_dates.json> as its fifth argument.
OpenAlex gives the earliest publication date, which is often the online-first date. build_history.py decides which
dates give a month (not 1 January, and the same year as shown on the timeline).
"""
import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oa_store import oa_get

sys.stdout.reconfigure(encoding="utf-8")
data_dir, raw_path, out_path = sys.argv[1:4]
ids = sorted(json.load(open(os.path.join(data_dir, "history.json"), encoding="utf-8"))["works"])
dates = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
db = sqlite3.connect(raw_path)
for k in ids:
    r = db.execute("SELECT publication_date FROM oa_works WHERE work_id = ?", (k,)).fetchone()
    if r and r[0]:
        dates[k] = r[0]
todo = [k for k in ids if k not in dates]
print(f"works on the timeline: {len(ids)} | date known: {len(ids) - len(todo)} | to ask OpenAlex: {len(todo)}", flush=True)
for i in range(0, len(todo), 50):
    chunk = todo[i:i + 50]
    res = oa_get("works", {"filter": "openalex:" + "|".join(chunk), "select": "id,publication_date", "per-page": 50})
    for w in (res or {}).get("results", []):
        if w.get("publication_date"):
            dates[w["id"].rsplit("/", 1)[-1]] = w["publication_date"]
missing = [k for k in ids if k not in dates]
print(f"still without a date: {len(missing)} {missing[:10]}")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(dict(sorted(dates.items())), f, ensure_ascii=False, indent=0)
