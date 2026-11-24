"""Fetch every Crossref work linked to each ORCID in the combined list.

Usage: python -I crossref_works.py <combined list.xlsx> <database.sqlite> <papers.xlsx>
Stores results in SQLite and exports one row per person-paper to a spreadsheet.
"""
import sys, json, time, sqlite3, datetime
import requests, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

sys.stdout.reconfigure(encoding="utf-8")
xlsx, db_path, out_xlsx = sys.argv[1], sys.argv[2], sys.argv[3]
UA = {"User-Agent": "metascience-community-script"}
session = requests.Session()

def get(url, params):
    r = None
    for attempt in range(6):
        try:
            r = session.get(url, params=params, headers=UA, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            time.sleep(0.25)  # Crossref public pool: stay well under its rate limit
            return r.json()
        except requests.RequestException as e:
            print("  retrying after error:", e, flush=True)
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"STOPPED: Crossref request kept failing (last status {getattr(r, 'status_code', '?')}): {params}")

db = sqlite3.connect(db_path)
db.executescript("""
CREATE TABLE IF NOT EXISTS people (
  orcid TEXT PRIMARY KEY, name TEXT, list TEXT, in_nl TEXT, match_certainty TEXT,
  openalex_ids TEXT, current_employer TEXT, current_country TEXT, role TEXT, affiliation TEXT);
CREATE TABLE IF NOT EXISTS works (
  doi TEXT PRIMARY KEY, title TEXT, type TEXT, year INTEGER, container_title TEXT, publisher TEXT,
  n_authors INTEGER, cited_by INTEGER, abstract TEXT, raw_json TEXT);
CREATE TABLE IF NOT EXISTS work_authors (
  doi TEXT, position INTEGER, given TEXT, family TEXT, name TEXT, orcid TEXT, orcid_authenticated INTEGER,
  affiliations TEXT, sequence TEXT, PRIMARY KEY (doi, position));
CREATE TABLE IF NOT EXISTS person_works (
  orcid TEXT, doi TEXT, author_position INTEGER, PRIMARY KEY (orcid, doi));
CREATE TABLE IF NOT EXISTS fetch_log (orcid TEXT PRIMARY KEY, n_works INTEGER, fetched_at TEXT);
""")

# ---- people with an ORCID ----
wb = openpyxl.load_workbook(xlsx, read_only=True)
people = []
for sheet in ["In NL", "Check or not NL"]:
    rows = list(wb[sheet].iter_rows(values_only=True))
    col = {h: i for i, h in enumerate(rows[0])}
    for r in rows[1:]:
        orcid = (r[col["ORCID"]] or "").strip()
        if not orcid:
            continue
        rec = (orcid, r[col["Name"]], sheet, r[col["In the Netherlands?"]], r[col["Match certainty"]],
               r[col["OpenAlex ID"]], r[col["Current employer (ORCID)"]], r[col["Current employer country"]],
               r[col["Role(s)"]], r[col["Affiliation(s)"]])
        people.append(rec)
        db.execute("INSERT OR REPLACE INTO people VALUES (?,?,?,?,?,?,?,?,?,?)", rec)
db.commit()
print("people with ORCID:", len(people), flush=True)

def year_of(it):
    for k in ("issued", "published", "published-print", "published-online", "created"):
        dp = (it.get(k) or {}).get("date-parts") or [[None]]
        if dp and dp[0] and dp[0][0]:
            return dp[0][0]
    return None

# ---- fetch works ----
for i, p in enumerate(people, 1):
    orcid, name = p[0], p[1]
    items, cursor = [], "*"
    while True:
        d = get("https://api.crossref.org/works", {"filter": f"orcid:{orcid}", "rows": 1000, "cursor": cursor})
        msg = d["message"]
        items += msg.get("items", [])
        if not msg.get("items") or len(items) >= msg.get("total-results", 0):
            break
        cursor = msg.get("next-cursor")
    for it in items:
        doi = it["DOI"].lower()
        it.pop("reference", None)  # reference lists are large and not needed
        authors = it.get("author") or []
        db.execute("INSERT OR REPLACE INTO works VALUES (?,?,?,?,?,?,?,?,?,?)", (
            doi, (it.get("title") or [""])[0], it.get("type"), year_of(it), (it.get("container-title") or [""])[0],
            it.get("publisher"), len(authors), it.get("is-referenced-by-count"), it.get("abstract"),
            json.dumps(it, ensure_ascii=False)))
        db.execute("DELETE FROM work_authors WHERE doi=?", (doi,))
        pos_self = None
        for pos, a in enumerate(authors, 1):
            a_orcid = (a.get("ORCID") or "").rsplit("/", 1)[-1]
            nm = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name") or ""
            db.execute("INSERT INTO work_authors VALUES (?,?,?,?,?,?,?,?,?)", (
                doi, pos, a.get("given"), a.get("family"), nm, a_orcid,
                int(bool(a.get("authenticated-orcid"))),
                "; ".join(af.get("name", "") for af in a.get("affiliation") or []), a.get("sequence")))
            if a_orcid.upper() == orcid.upper():
                pos_self = pos
        db.execute("INSERT OR REPLACE INTO person_works VALUES (?,?,?)", (orcid, doi, pos_self))
    db.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?)",
               (orcid, len(items), datetime.datetime.now().isoformat(timespec="seconds")))
    db.commit()
    print(f"{i}/{len(people)} {name}: {len(items)} works", flush=True)

# ---- spreadsheet export ----
q = """
SELECT p.name, p.orcid, p.list, w.doi, w.title, w.year, w.type, w.container_title, w.n_authors, pw.author_position,
       (SELECT group_concat(name, '; ') FROM (SELECT name FROM work_authors wa WHERE wa.doi = w.doi ORDER BY position LIMIT 25))
FROM person_works pw JOIN people p USING (orcid) JOIN works w USING (doi)
ORDER BY p.name, w.year DESC
"""
out = openpyxl.Workbook()
ws = out.active
ws.title = "Papers per person"
hdr = ["Person", "ORCID", "List", "DOI", "Title", "Year", "Type", "Journal / container", "Number of authors",
       "Person's author position", "Authors (first 25)"]
ws.append(hdr)
for row in db.execute(q):
    ws.append([("https://doi.org/" + v if j == 3 else v) for j, v in enumerate(row)])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
    c.alignment = Alignment(wrap_text=True, vertical="top")
for letter, w in zip("ABCDEFGHIJK", [26, 21, 16, 34, 70, 7, 16, 36, 10, 10, 80]):
    ws.column_dimensions[letter].width = w
ws.freeze_panes = "B2"; ws.auto_filter.ref = ws.dimensions

ws2 = out.create_sheet("Works per person")
ws2.append(["Person", "ORCID", "List", "Crossref works"])
for row in db.execute("SELECT p.name, p.orcid, p.list, f.n_works FROM fetch_log f JOIN people p USING (orcid) ORDER BY f.n_works DESC"):
    ws2.append(list(row))
for c in ws2[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
ws2.column_dimensions["A"].width = 28; ws2.column_dimensions["B"].width = 22; ws2.column_dimensions["C"].width = 16
out.save(out_xlsx)

tot = db.execute("SELECT count(*) FROM works").fetchone()[0]
links = db.execute("SELECT count(*) FROM person_works").fetchone()[0]
nopos = db.execute("SELECT count(*) FROM person_works WHERE author_position IS NULL").fetchone()[0]
print(f"distinct works: {tot}; person-work links: {links}; links where the ORCID was not found in the author list: {nopos}")
