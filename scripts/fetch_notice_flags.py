"""Which candidate papers are notices (retraction, correction, ...) and which papers were retracted.

Usage: python -I fetch_notice_flags.py <raw database.sqlite> <notice_flags.json>
Needs OPENALEX_API_KEY. Run before build_site_data.py, which leaves out the works marked here.

For every paper that the classification judged metascience (view metascience_final), asks
- Crossref (50 DOIs per request): "update-to", set on a notice and naming the paper it retracts or corrects, and
  "updated-by", set on a paper and naming the notices about it;
- OpenAlex (50 works per request): is_retracted (from the Retraction Watch database).
A work is a notice when Crossref gives it an "update-to" of any type other than a new version or new edition.
A work is retracted when OpenAlex says so, or when Crossref lists a retraction, withdrawal or removal notice for it.
Partial retractions, corrections and expressions of concern do not remove a paper.
Everything is asked again on every run, because papers can be retracted at any time.
Writes {"checked": date, "n_checked": n, "ids": [every work checked], "flags": {work id: {"notice": [types],
"updated_by": [types], "openalex_retracted": bool}}} (flags only for works with a mark).
"""
import sys, os, json, time, datetime, sqlite3
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oa_store import oa_get

sys.stdout.reconfigure(encoding="utf-8")
raw_path, out_path = sys.argv[1:3]
db = sqlite3.connect(raw_path)
rows = db.execute("""SELECT DISTINCT w.work_id, w.doi FROM metascience_final m JOIN oa_works w USING (work_id)
                     WHERE m.prompt_version = 'v2+v4' AND m.is_metascience = 1""").fetchall()
ids = sorted({w for w, _ in rows})
doi_work = {}
for w, d in rows:
    d = (d or "").lower().replace("https://doi.org/", "").strip()
    if d:
        doi_work.setdefault(d, set()).add(w)
print(f"works to check: {len(ids)} | with a DOI: {len(doi_work)}", flush=True)

flags = {}
def mark(w, key, value):
    f = flags.setdefault(w, dict(notice=[], updated_by=[], openalex_retracted=False))
    if key == "openalex_retracted":
        f[key] = value
    elif value not in f[key]:
        f[key].append(value)

# ---- Crossref
session = requests.Session()
session.headers["User-Agent"] = "metascience-site-check (python requests)"
def crossref(params):
    for attempt in range(6):
        try:
            r = session.get("https://api.crossref.org/works", params=params, timeout=60)
            if r.status_code == 200:
                return r.json()["message"]["items"]
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    raise SystemExit(f"STOPPED: Crossref gave no answer for {params['filter'][:120]}")

dois = sorted(doi_work)
plain = [d for d in dois if "," not in d]        # a comma would split the filter
for i in range(0, len(plain), 50):
    chunk = plain[i:i + 50]
    items = crossref({"filter": ",".join("doi:" + d for d in chunk), "select": "DOI,update-to,updated-by", "rows": 100})
    for it in items:
        for w in doi_work.get(it["DOI"].lower(), ()):
            for u in it.get("update-to", []):
                if u.get("type") not in ("new_version", "new_edition"):
                    mark(w, "notice", u.get("type"))
            for u in it.get("updated-by", []):
                mark(w, "updated_by", u.get("type"))
    if i % 2000 == 0:
        print(f"  Crossref {i}/{len(plain)}", flush=True)
for d in [d for d in dois if "," in d]:
    try:
        it = session.get("https://api.crossref.org/works/" + requests.utils.quote(d, safe="/"), timeout=60).json()["message"]
    except Exception:
        continue
    for w in doi_work[d]:
        for u in it.get("update-to", []):
            if u.get("type") not in ("new_version", "new_edition"):
                mark(w, "notice", u.get("type"))
        for u in it.get("updated-by", []):
            mark(w, "updated_by", u.get("type"))

# ---- OpenAlex
answered = set()
for i in range(0, len(ids), 50):
    chunk = ids[i:i + 50]
    res = oa_get("works", {"filter": "openalex:" + "|".join(chunk), "select": "id,is_retracted", "per-page": 50})
    for w in (res or {}).get("results", []):
        k = w["id"].rsplit("/", 1)[-1]
        answered.add(k)
        if w.get("is_retracted"):
            mark(k, "openalex_retracted", True)
missing = [k for k in ids if k not in answered]
print(f"OpenAlex gave no record for {len(missing)} works (merged or removed there): {missing[:10]}")

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(dict(checked=datetime.date.today().isoformat(), n_checked=len(ids), ids=ids,
                   flags=dict(sorted(flags.items()))), f, ensure_ascii=False, indent=0)
RETRACTED = ("retraction", "withdrawal", "removal")
print(f"notices: {sum(1 for f in flags.values() if f['notice'])} | retracted: "
      f"{sum(1 for f in flags.values() if f['openalex_retracted'] or set(f['updated_by']) & set(RETRACTED))}")
