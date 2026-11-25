"""Download all NWO projects from the public NWOpen API (CC0) into one local JSON file.

Usage: python -I fetch_nwo.py <out.json>
API: https://nwopen-api.nwo.nl/NWOpen-API/api/Projects (documentation: https://doi.org/10.5281/zenodo.14918287).
Per project: title, funding scheme, start and end date, award amount, summaries, and project members (name, role,
organisation with ROR id; rarely an ORCID). Resumable: pages already downloaded are kept in <out.json>.partial.
"""
import sys, json, time, os
import requests

out = sys.argv[1]
URL = "https://nwopen-api.nwo.nl/NWOpen-API/api/Projects"
PER = 500
part = out + ".partial"
pages = json.load(open(part, encoding="utf-8")) if os.path.exists(part) else {}
s = requests.Session()
s.headers["User-Agent"] = "dutch-metascience (research project; python requests)"
first = s.get(URL, params={"per_page": PER, "page": 1}, timeout=120).json()
n_pages = first["meta"]["pages"]
print("projects:", first["meta"]["count"], "| pages:", n_pages, flush=True)
pages.setdefault("1", first["projects"])
for pg in range(1, n_pages + 1):
    if str(pg) in pages:
        continue
    for attempt in range(5):
        try:
            r = s.get(URL, params={"per_page": PER, "page": pg}, timeout=120)
            r.raise_for_status()
            pages[str(pg)] = r.json()["projects"]
            break
        except (requests.RequestException, ValueError) as e:
            print(f"  page {pg}: {type(e).__name__}, retry {attempt + 1}", flush=True)
            time.sleep(5 * (attempt + 1))
    else:
        json.dump(pages, open(part, "w", encoding="utf-8"))
        raise SystemExit(f"STOPPED at page {pg}; run again to continue")
    if pg % 10 == 0:
        json.dump(pages, open(part, "w", encoding="utf-8"))
        print(f"  {pg}/{n_pages}", flush=True)
    time.sleep(0.3)
projects = [p for k in sorted(pages, key=int) for p in pages[k]]
json.dump(projects, open(out, "w", encoding="utf-8"), ensure_ascii=False)
if os.path.exists(part):
    os.remove(part)
print("saved", len(projects), "projects to", out)
