"""Look up in OpenAlex, by DOI, the Crossref works that are not yet in the OpenAlex tables.

Usage: python -I crossref_lookup.py <raw database.sqlite>
Adds the records to oa_works / oa_authorships / oa_authorship_institutions / oa_institutions,
and records which DOI was found under which OpenAlex work in oa_crossref_lookup.
Blog posts (publisher 'Front Matter'), peer reviews, datasets, grants etc. are not looked up.
"""
import sys, os, json, time, sqlite3
import requests

sys.stdout.reconfigure(encoding="utf-8")
db_path = sys.argv[1]
KEY = os.environ.get("OPENALEX_API_KEY", "").strip().strip('"').strip("'")
if not KEY:
    raise SystemExit("STOPPED: OPENALEX_API_KEY is not set")

# store() below stores records in the same way as openalex_works.py
FIELDS = ("id,doi,display_name,publication_year,publication_date,type,primary_location,authorships,"
          "is_authors_truncated,cited_by_count,primary_topic,topics,keywords,abstract_inverted_index,language,"
          "open_access,ids")
short = lambda u: (u or "").rsplit("/", 1)[-1]
session = requests.Session()

def get(params):
    r = None
    for attempt in range(6):
        try:
            r = session.get("https://api.openalex.org/works", params={**params, "api_key": KEY},
                            headers={"User-Agent": "dutch-metascience-script"}, timeout=90)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            time.sleep(0.1)
            return r.json()
        except requests.RequestException as e:
            print("  retrying after error:", str(e).replace(KEY, "<key>"), flush=True)
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"STOPPED: OpenAlex request kept failing (last status {getattr(r, 'status_code', '?')})")

def get_one(doi):
    r = None
    for attempt in range(6):
        try:
            r = session.get(f"https://api.openalex.org/works/doi:{doi}", params={"select": FIELDS, "api_key": KEY},
                            headers={"User-Agent": "dutch-metascience-script"}, timeout=90)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            time.sleep(0.1)
            return r.json()
        except requests.RequestException as e:
            print("  retrying after error:", str(e).replace(KEY, "<key>"), flush=True)
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"STOPPED: OpenAlex request kept failing (last status {getattr(r, 'status_code', '?')}): {doi}")

def abstract(inv):
    if not inv:
        return None
    pos = {i: w for w, idx in inv.items() for i in idx}
    return " ".join(pos[i] for i in sorted(pos))

def store(db, w):
    wid = short(w["id"])
    pt = w.get("primary_topic") or {}
    loc = (w.get("primary_location") or {}).get("source") or {}
    auths = w.get("authorships") or []
    db.execute("INSERT OR REPLACE INTO oa_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        wid, (w.get("doi") or "").replace("https://doi.org/", "").lower() or None,
        w.get("display_name"), w.get("type"), w.get("publication_year"), w.get("publication_date"),
        loc.get("display_name"), loc.get("type"), w.get("cited_by_count"), len(auths),
        int(bool(w.get("is_authors_truncated"))), pt.get("display_name"),
        (pt.get("subfield") or {}).get("display_name"), (pt.get("field") or {}).get("display_name"),
        (pt.get("domain") or {}).get("display_name"),
        "; ".join(t.get("display_name", "") for t in w.get("topics") or []),
        "; ".join(k.get("display_name", "") for k in w.get("keywords") or []), w.get("language"),
        int(bool((w.get("open_access") or {}).get("is_oa"))), abstract(w.get("abstract_inverted_index")),
        json.dumps({k: v for k, v in w.items() if k != "abstract_inverted_index"}, ensure_ascii=False)))
    db.execute("DELETE FROM oa_authorships WHERE work_id=?", (wid,))
    db.execute("DELETE FROM oa_authorship_institutions WHERE work_id=?", (wid,))
    for pos, a in enumerate(auths, 1):
        au = a.get("author") or {}
        db.execute("INSERT OR REPLACE INTO oa_authorships VALUES (?,?,?,?,?,?,?,?,?)", (
            wid, pos, short(au.get("id")), au.get("display_name"), short(au.get("orcid")), a.get("author_position"),
            int(bool(a.get("is_corresponding"))), "; ".join(a.get("countries") or []),
            " | ".join(a.get("raw_affiliation_strings") or [])))
        for inst in a.get("institutions") or []:
            iid = short(inst.get("id"))
            if iid:
                db.execute("INSERT OR IGNORE INTO oa_authorship_institutions VALUES (?,?,?)", (wid, pos, iid))
                db.execute("INSERT OR REPLACE INTO oa_institutions VALUES (?,?,?,?,?,?)", (
                    iid, inst.get("display_name"), short(inst.get("ror")), inst.get("country_code"),
                    inst.get("type"), "; ".join(short(x) for x in inst.get("lineage") or [])))
    return wid

db = sqlite3.connect(db_path)
db.execute("CREATE TABLE IF NOT EXISTS oa_crossref_lookup (doi TEXT PRIMARY KEY, work_id TEXT)")
dois = [r[0] for r in db.execute("""
    SELECT doi FROM works
    WHERE doi NOT IN (SELECT doi FROM oa_works WHERE doi IS NOT NULL)
      AND doi NOT IN (SELECT doi FROM oa_crossref_lookup WHERE work_id IS NOT NULL)
      AND type IN ('journal-article','proceedings-article','book-chapter','book','monograph','edited-book',
                   'posted-content')
      AND coalesce(publisher,'') <> 'Front Matter'
      AND doi NOT LIKE '10.17605/%'""")]
print("DOIs to look up:", len(dois), flush=True)
found = 0
for i in range(0, len(dois), 50):
    batch = dois[i:i + 50]
    d = get({"filter": "doi:" + "|".join(batch), "per-page": 200, "select": FIELDS})
    got = {}
    for w in d.get("results", []):
        got[(w.get("doi") or "").replace("https://doi.org/", "").lower()] = store(db, w)
    # OpenAlex merges a preprint into its published version, which then carries the journal DOI,
    # so look up each unmatched DOI on its own to learn which work it belongs to
    for doi in batch:
        if doi not in got:
            w = get_one(doi)
            if w:
                got[doi] = store(db, w)
    for doi in batch:
        db.execute("INSERT OR REPLACE INTO oa_crossref_lookup VALUES (?,?)", (doi, got.get(doi)))
    found += sum(1 for doi in batch if doi in got)
    db.commit()
    print(f"  {min(i + 50, len(dois))}/{len(dois)} looked up, {found} found", flush=True)
print("found in OpenAlex:", found, "of", len(dois))
