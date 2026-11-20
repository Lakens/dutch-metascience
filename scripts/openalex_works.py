"""Fetch every OpenAlex work for each matched person, with all authors and their institutions.

Usage: python -I openalex_works.py <combined list.xlsx> <database.sqlite>
Reads OPENALEX_API_KEY from the environment. Writes oa_* tables into the same SQLite database.
"""
import sys, os, json, time, sqlite3, datetime, urllib.parse
import requests, openpyxl

sys.stdout.reconfigure(encoding="utf-8")
xlsx, db_path = sys.argv[1], sys.argv[2]
KEY = os.environ.get("OPENALEX_API_KEY", "").strip().strip('"').strip("'")
if not KEY:
    raise SystemExit("STOPPED: OPENALEX_API_KEY is not set")
UA = {"User-Agent": "metascience-landscape-script"}
session = requests.Session()
FIELDS = ("id,doi,display_name,publication_year,publication_date,type,primary_location,authorships,"
          "is_authors_truncated,cited_by_count,primary_topic,topics,keywords,abstract_inverted_index,language,"
          "open_access,ids")

def get(params):
    r = None
    for attempt in range(6):
        try:
            r = session.get("https://api.openalex.org/works", params={**params, "api_key": KEY},
                            headers=UA, timeout=90)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            time.sleep(0.1)
            return r.json()
        except requests.RequestException as e:
            print("  retrying after error:", str(e).replace(KEY, "<key>"), flush=True)
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"STOPPED: OpenAlex request kept failing (last status {getattr(r, 'status_code', '?')}): "
                     f"{params.get('filter')}")

def abstract(inv):
    if not inv:
        return None
    pos = {}
    for word, idx in inv.items():
        for i in idx:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))

short = lambda u: (u or "").rsplit("/", 1)[-1]

db = sqlite3.connect(db_path)
db.executescript("""
CREATE TABLE IF NOT EXISTS oa_people (
  person_id TEXT PRIMARY KEY, name TEXT, orcid TEXT, openalex_ids TEXT, list TEXT, in_nl TEXT,
  match_certainty TEXT, current_employer TEXT, current_country TEXT, role TEXT, affiliation TEXT);
CREATE TABLE IF NOT EXISTS oa_works (
  work_id TEXT PRIMARY KEY, doi TEXT, title TEXT, type TEXT, year INTEGER, publication_date TEXT,
  venue TEXT, venue_type TEXT, cited_by INTEGER, n_authors INTEGER, authors_truncated INTEGER,
  topic TEXT, subfield TEXT, field TEXT, domain TEXT, topics TEXT, keywords TEXT, language TEXT,
  is_oa INTEGER, abstract TEXT, raw_json TEXT);
CREATE TABLE IF NOT EXISTS oa_authorships (
  work_id TEXT, position INTEGER, author_id TEXT, author_name TEXT, orcid TEXT, author_position TEXT,
  is_corresponding INTEGER, countries TEXT, raw_affiliations TEXT, PRIMARY KEY (work_id, position));
CREATE TABLE IF NOT EXISTS oa_authorship_institutions (
  work_id TEXT, position INTEGER, institution_id TEXT, PRIMARY KEY (work_id, position, institution_id));
CREATE TABLE IF NOT EXISTS oa_institutions (
  institution_id TEXT PRIMARY KEY, name TEXT, ror TEXT, country_code TEXT, type TEXT, lineage TEXT);
CREATE TABLE IF NOT EXISTS oa_person_works (
  person_id TEXT, work_id TEXT, author_position INTEGER, PRIMARY KEY (person_id, work_id));
CREATE TABLE IF NOT EXISTS oa_fetch_log (person_id TEXT PRIMARY KEY, n_works INTEGER, fetched_at TEXT);
""")

# ---- people with an ORCID or an OpenAlex ID ----
wb = openpyxl.load_workbook(xlsx, read_only=True)
people = []
for sheet in ["In NL", "Check or not NL"]:
    rows = list(wb[sheet].iter_rows(values_only=True))
    col = {h: i for i, h in enumerate(rows[0])}
    for r in rows[1:]:
        orcid = (r[col["ORCID"]] or "").strip()
        oa_ids = [x.strip() for x in (r[col["OpenAlex ID"]] or "").split(";") if x.strip()]
        if not orcid and not oa_ids:
            continue
        pid = orcid or oa_ids[0]
        rec = (pid, r[col["Name"]], orcid, "; ".join(oa_ids), sheet, r[col["In the Netherlands?"]],
               r[col["Match certainty"]], r[col["Current employer (ORCID)"]], r[col["Current employer country"]],
               r[col["Role(s)"]], r[col["Affiliation(s)"]])
        people.append((rec, oa_ids))
        db.execute("INSERT OR REPLACE INTO oa_people VALUES (?,?,?,?,?,?,?,?,?,?,?)", rec)
db.commit()
print("people:", len(people), flush=True)

for i, (rec, oa_ids) in enumerate(people, 1):
    pid, name, orcid = rec[0], rec[1], rec[2]
    filt = []
    if oa_ids:
        filt.append("author.id:" + "|".join(oa_ids))
    else:
        filt.append("author.orcid:" + orcid)
    items, cursor = [], "*"
    while cursor:
        d = get({"filter": filt[0], "per-page": 200, "cursor": cursor, "select": FIELDS})
        items += d.get("results", [])
        cursor = (d.get("meta") or {}).get("next_cursor") if d.get("results") else None
    mine = set(oa_ids)
    db.execute("DELETE FROM oa_person_works WHERE person_id=?", (pid,))
    for w in items:
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
        self_pos = None
        for pos, a in enumerate(auths, 1):
            au = a.get("author") or {}
            aid = short(au.get("id"))
            if aid in mine or (orcid and short(au.get("orcid")).upper() == orcid.upper()):
                self_pos = self_pos or pos
            db.execute("INSERT OR REPLACE INTO oa_authorships VALUES (?,?,?,?,?,?,?,?,?)", (
                wid, pos, aid, au.get("display_name"), short(au.get("orcid")), a.get("author_position"),
                int(bool(a.get("is_corresponding"))), "; ".join(a.get("countries") or []),
                " | ".join(a.get("raw_affiliation_strings") or [])))
            for inst in a.get("institutions") or []:
                iid = short(inst.get("id"))
                if not iid:
                    continue
                db.execute("INSERT OR IGNORE INTO oa_authorship_institutions VALUES (?,?,?)", (wid, pos, iid))
                db.execute("INSERT OR REPLACE INTO oa_institutions VALUES (?,?,?,?,?,?)", (
                    iid, inst.get("display_name"), short(inst.get("ror")), inst.get("country_code"),
                    inst.get("type"), "; ".join(short(x) for x in inst.get("lineage") or [])))
        db.execute("INSERT OR REPLACE INTO oa_person_works VALUES (?,?,?)", (pid, wid, self_pos))
    db.execute("INSERT OR REPLACE INTO oa_fetch_log VALUES (?,?,?)",
               (pid, len(items), datetime.datetime.now().isoformat(timespec="seconds")))
    db.commit()
    print(f"{i}/{len(people)} {name}: {len(items)} works", flush=True)

q = lambda s: db.execute(s).fetchone()
print("distinct works:", q("SELECT count(*) FROM oa_works")[0],
      "| person-work links:", q("SELECT count(*) FROM oa_person_works")[0],
      "| authorships:", q("SELECT count(*) FROM oa_authorships")[0],
      "| with institution:", q("SELECT count(DISTINCT work_id||'-'||position) FROM oa_authorship_institutions")[0],
      "| institutions:", q("SELECT count(*) FROM oa_institutions")[0],
      "| works with truncated author lists:", q("SELECT sum(authors_truncated) FROM oa_works")[0])
