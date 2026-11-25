"""Download the reference lists of all papers on the site, and details of the works they cite most, from OpenAlex.

Usage: python -I fetch_references.py <site data folder> <out.json>
Needs the environment variable OPENALEX_API_KEY.
1. For every paper in <site data folder>/papers.json: its list of referenced works (OpenAlex ids), 100 papers per request.
2. For every cited work that at least MIN_CITING site papers cite: title, year, authors, venue, type, total citations,
   OpenAlex's citation percentile compared with works of the same field and year, and its main OpenAlex topic.
Resumable: what was downloaded is kept in <out.json>.partial.
"""
import sys, os, json, time, collections
import requests

sys.stdout.reconfigure(encoding="utf-8")
data_dir, out = sys.argv[1:3]
KEY = os.environ.get("OPENALEX_API_KEY", "").strip().strip('"').strip("'")
if not KEY:
    raise SystemExit("STOPPED: OPENALEX_API_KEY is not set")
MIN_CITING = 5
part = out + ".partial"
store = json.load(open(part, encoding="utf-8")) if os.path.exists(part) else {"refs": {}, "works": {}}
s = requests.Session()
s.headers["User-Agent"] = "dutch-metascience-script"

def get(ids, select):
    for attempt in range(5):
        try:
            r = s.get("https://api.openalex.org/works", timeout=120,
                      params={"filter": "openalex:" + "|".join(ids), "select": select, "per-page": 100, "api_key": KEY})
            r.raise_for_status()
            return r.json()["results"]
        except (requests.RequestException, ValueError) as e:
            print(f"  {type(e).__name__}, retry {attempt + 1}", flush=True)
            time.sleep(5 * (attempt + 1))
    json.dump(store, open(part, "w", encoding="utf-8"))
    raise SystemExit("STOPPED after 5 failed attempts; run again to continue")
def short(u):
    return (u or "").rstrip("/").split("/")[-1]

papers = [p["id"] for p in json.load(open(os.path.join(data_dir, "papers.json"), encoding="utf-8"))]
todo = [p for p in papers if p not in store["refs"]]
for i in range(0, len(todo), 100):
    chunk = todo[i:i + 100]
    for w in get(chunk, "id,referenced_works"):
        store["refs"][short(w["id"])] = [short(x) for x in w.get("referenced_works") or []]
    for p in chunk:                      # works OpenAlex did not return (merged ids): an empty list, so we do not ask again
        store["refs"].setdefault(p, [])
    if (i // 100) % 10 == 0:
        json.dump(store, open(part, "w", encoding="utf-8"))
        print(f"  reference lists: {min(i + 100, len(todo))}/{len(todo)}", flush=True)
    time.sleep(0.1)
json.dump(store, open(part, "w", encoding="utf-8"))
with_refs = sum(1 for p in papers if store["refs"].get(p))
print(f"papers with a reference list: {with_refs} of {len(papers)}", flush=True)

citing = collections.Counter(r for p in papers for r in set(store["refs"].get(p, [])))
wanted = [w for w, n in citing.items() if n >= MIN_CITING and w not in store["works"]]
print(f"cited works: {len(citing)} | cited by at least {MIN_CITING} site papers: "
      f"{sum(1 for n in citing.values() if n >= MIN_CITING)} | still to fetch: {len(wanted)}", flush=True)
SEL = ("id,doi,display_name,publication_year,type,authorships,primary_location,cited_by_count,"
       "citation_normalized_percentile,fwci,primary_topic")
for i in range(0, len(wanted), 100):
    chunk = wanted[i:i + 100]
    for w in get(chunk, SEL):
        auth = [a["author"]["display_name"] for a in (w.get("authorships") or []) if a.get("author")]
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        pct = (w.get("citation_normalized_percentile") or {}).get("value")
        tp = w.get("primary_topic") or {}
        store["works"][short(w["id"])] = dict(
            t=w.get("display_name") or "", y=w.get("publication_year"), doi=(w.get("doi") or "").replace("https://doi.org/", ""),
            ty=w.get("type") or "", a=auth[:3], na=len(auth), v=src, c=w.get("cited_by_count") or 0, pct=pct,
            fwci=w.get("fwci"), tp=tp.get("display_name") or "", sf=(tp.get("subfield") or {}).get("display_name") or "",
            fd=(tp.get("field") or {}).get("display_name") or "")
    for w in chunk:
        store["works"].setdefault(w, None)
    if (i // 100) % 10 == 0:
        json.dump(store, open(part, "w", encoding="utf-8"))
        print(f"  cited works: {min(i + 100, len(wanted))}/{len(wanted)}", flush=True)
    time.sleep(0.1)
json.dump(store, open(out, "w", encoding="utf-8"))
os.remove(part)
print("written", out, f"{os.path.getsize(out) / 1e6:.1f} MB")
