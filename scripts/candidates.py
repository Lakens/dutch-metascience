"""Make the list of candidate Dutch metascientists from the papers judged as metascience.

Usage: python -I candidates.py <raw database.sqlite> <clean database.sqlite> <combined people list.xlsx> <output.xlsx> [prompt version]

A candidate is an author with a Dutch institution on at least one metascience paper (the user's rule:
one paper is enough), who is not already on our list (by OpenAlex author id, ORCID or name).
Their last known institution is read from OpenAlex. Needs OPENALEX_API_KEY.
"""
import sys, os, re, sqlite3, unicodedata, collections
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oa_store import oa_get, short

sys.stdout.reconfigure(encoding="utf-8")
raw_path, clean_path, people_xlsx, out_xlsx = sys.argv[1:5]
version = sys.argv[5] if len(sys.argv) > 5 else None
db = sqlite3.connect(raw_path)
db.execute("ATTACH DATABASE ? AS clean", (clean_path,))
if version is None:  # metascience = v2 and the stricter check v4 both say so (view metascience_final)
    version = "v2+v4"
print("prompt version:", version)

def key(name):
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", n)

# ---- who is already on the list (both sheets of the combined list). People removed earlier as
#      non-academic are no longer in that file, so they can come back as candidates. ----
known_ids, known_orcids, known_names = set(), set(), set()
for r in db.execute("SELECT name, orcid, openalex_ids FROM oa_people"):
    known_names.add(key(r[0]))
    if r[1]:
        known_orcids.add(r[1].upper())
    known_ids.update(x.strip() for x in (r[2] or "").split(";") if x.strip())
wb = openpyxl.load_workbook(people_xlsx, read_only=True)
for sheet in wb.sheetnames:
    for row in wb[sheet].iter_rows(min_row=2, values_only=True):
        if row and row[0]:
            known_names.add(key(row[0]))

# ---- authorships with a Dutch institution on metascience papers ----
rows = db.execute("""
  SELECT a.author_id, a.author_name, a.orcid, w.work_id, w.title, w.year, w.n_authors, w.type,
         group_concat(i.name, ' | ') AS nl_insts
  FROM metascience_final m
  JOIN oa_works w ON w.work_id = m.work_id
  JOIN oa_authorships a ON a.work_id = w.work_id
  JOIN oa_authorship_institutions ai ON ai.work_id = a.work_id AND ai.position = a.position
  JOIN oa_institutions i ON i.institution_id = ai.institution_id
  WHERE m.prompt_version = ? AND m.is_metascience = 1 AND i.country_code = 'NL' AND a.author_id <> ''
  GROUP BY a.author_id, w.work_id""", (version,)).fetchall()
print("authorships with a Dutch institution on metascience papers:", len(rows))

# co-authors on our list, per work
list_people = {}
for pid, name, orcid, ids in db.execute("SELECT person_id, name, orcid, openalex_ids FROM oa_people"):
    for x in (ids or "").split(";"):
        if x.strip():
            list_people[x.strip()] = name
work_list_authors = collections.defaultdict(set)
for wid, aid in db.execute("""SELECT a.work_id, a.author_id FROM oa_authorships a
                              JOIN metascience_final m ON m.work_id = a.work_id
                              WHERE m.prompt_version = ? AND m.is_metascience = 1""", (version,)):
    if aid in list_people:
        work_list_authors[wid].add(list_people[aid])

cand = {}
for aid, name, orcid, wid, title, year, n_auth, wtype, insts in rows:
    if aid in known_ids or (orcid and orcid.upper() in known_orcids) or key(name) in known_names:
        continue
    c = cand.setdefault(aid, dict(name=name, orcid=orcid, works=[], insts=collections.Counter(), coauth=set()))
    c["works"].append((year or 0, title, n_auth or 0, wtype))
    c["insts"].update(set((insts or "").split(" | ")))
    c["coauth"].update(work_list_authors.get(wid, ()))
    c["orcid"] = c["orcid"] or orcid
print("candidates:", len(cand))

# ---- last known institution from OpenAlex, 50 authors per request ----
ids = list(cand)
for i in range(0, len(ids), 50):
    d = oa_get("authors", {"filter": "openalex:" + "|".join(ids[i:i + 50]), "per-page": 50,
                           "select": "id,display_name,orcid,works_count,last_known_institutions"})
    for a in (d or {}).get("results", []):
        c = cand.get(short(a["id"]))
        if c:
            lki = a.get("last_known_institutions") or []
            c["last_inst"] = "; ".join(x.get("display_name", "") for x in lki)
            c["last_country"] = "; ".join(sorted({x.get("country_code") or "" for x in lki}))
            c["works_count"] = a.get("works_count")
            c["orcid"] = c["orcid"] or short(a.get("orcid"))

# ---- spreadsheet ----
out = []
for aid, c in cand.items():
    works = sorted(c["works"], reverse=True)
    small = [w for w in works if w[2] <= 50]
    out.append([c["name"], c.get("orcid") or "", aid, len(works), len(small), works[0][0] or None,
                works[-1][0] or None, len(c["coauth"]), "; ".join(sorted(c["coauth"])),
                "; ".join(n for n, _ in c["insts"].most_common(3) if n), c.get("last_inst", ""),
                c.get("last_country", ""), c.get("works_count"),
                " | ".join(f"{w[0]}: {w[1]}" for w in works[:3]), ""])
out.sort(key=lambda r: (-r[4], -r[3], -r[7]))
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Candidates"
hdr = ["Name", "ORCID", "OpenAlex author", "Metascience papers with a Dutch affiliation",
       "... of which with at most 50 authors", "Most recent (year)", "First (year)",
       "Co-authors from our list (number)", "Co-authors from our list", "Dutch institutions on these papers",
       "Last known institution (OpenAlex)", "Its country", "All works in OpenAlex", "Most recent metascience papers",
       "Add to list? (yes/no)"]
ws.append(hdr)
for r in out:
    ws.append(r)
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
    c.alignment = Alignment(wrap_text=True, vertical="top")
for i, w in enumerate([26, 21, 13, 11, 11, 8, 8, 10, 40, 45, 40, 8, 9, 90, 10], 1):
    ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
ws.freeze_panes = "B2"; ws.auto_filter.ref = ws.dimensions
wb.save(out_xlsx)
print("saved", out_xlsx, "| with >=1 paper of at most 50 authors:", sum(1 for r in out if r[4] > 0),
      "| last known institution in NL:", sum(1 for r in out if "NL" in r[11]))
