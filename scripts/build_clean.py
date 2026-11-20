"""Build the cleaned database of scientific papers from the raw database.

Usage: python -I build_clean.py <raw database.sqlite> <clean database.sqlite> <clean papers.xlsx>
The raw database is only read. The clean database is rebuilt from scratch each run.
"""
import sys, os, sqlite3
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

sys.stdout.reconfigure(encoding="utf-8")
raw_path, clean_path, xlsx_path = sys.argv[1], sys.argv[2], sys.argv[3]
if os.path.exists(clean_path):
    os.replace(clean_path, clean_path + ".previous")  # keep the previous build rather than deleting it

KEEP_TYPES = ("article", "review", "preprint", "book", "book-chapter", "conference-paper", "editorial", "letter")
# Which works count as scientific papers. Every rule is listed so the choice can be checked.
SCIENTIFIC = f"""
    w.type IN ({",".join("'" + t + "'" for t in KEEP_TYPES)})
    AND coalesce(w.doi, '') NOT LIKE '10.17605/%'          -- OSF project and registration pages
    AND coalesce(w.doi, '') NOT LIKE '10.5281/%'           -- Zenodo deposits
    AND coalesce(w.doi, '') NOT LIKE '10.6084/%'           -- Figshare deposits
    AND coalesce(w.venue, '') NOT LIKE 'Zenodo%'
    AND coalesce(w.venue, '') NOT LIKE 'Figshare%'
    AND coalesce(w.venue, '') <> 'Open Science Framework'
    AND NOT (w.type = 'preprint' AND w.doi IS NULL)          -- OSF pages listed as preprints have no DOI
"""

db = sqlite3.connect(clean_path)
db.execute("ATTACH DATABASE ? AS raw", (raw_path,))  # only read from below
db.executescript(f"""
CREATE TABLE people AS SELECT * FROM raw.oa_people;

CREATE TABLE papers AS
  SELECT w.work_id, w.doi, w.title, w.type, w.year, w.publication_date, w.venue, w.venue_type, w.cited_by,
         w.n_authors, w.authors_truncated, w.topic, w.subfield, w.field, w.domain, w.topics, w.keywords,
         w.language, w.is_oa, w.abstract
  FROM raw.oa_works w WHERE {SCIENTIFIC};

-- links from OpenAlex profiles
CREATE TEMP TABLE links AS
  SELECT pw.person_id, pw.work_id, pw.author_position, 'OpenAlex profile' AS source
  FROM raw.oa_person_works pw JOIN papers USING (work_id);

-- Crossref DOI -> OpenAlex work: directly by DOI, or via the lookup (a preprint DOI merged into its journal version)
CREATE TEMP TABLE cr_map AS
  SELECT w.doi, w.work_id FROM raw.oa_works w WHERE w.doi IN (SELECT doi FROM raw.person_works)
  UNION SELECT doi, work_id FROM raw.oa_crossref_lookup WHERE work_id IS NOT NULL;
CREATE INDEX temp.cr_map_doi ON cr_map(doi);

-- links from Crossref (publisher recorded the ORCID); only where the person is an author on the OpenAlex record
INSERT INTO links
  SELECT p.person_id, w.work_id, a.position, 'Crossref ORCID'
  FROM raw.person_works cw
  JOIN raw.oa_people p ON p.orcid = cw.orcid
  JOIN cr_map m ON m.doi = cw.doi
  JOIN papers w ON w.work_id = m.work_id
  JOIN raw.oa_authorships a ON a.work_id = w.work_id AND upper(a.orcid) = upper(cw.orcid)
  WHERE cw.author_position IS NOT NULL;

-- fallback when OpenAlex lacks the ORCID on that authorship: same position and the Crossref surname matches
INSERT INTO links
  SELECT p.person_id, w.work_id, a.position, 'Crossref ORCID'
  FROM raw.person_works cw
  JOIN raw.oa_people p ON p.orcid = cw.orcid
  JOIN cr_map m ON m.doi = cw.doi
  JOIN papers w ON w.work_id = m.work_id
  JOIN raw.work_authors ca ON ca.doi = cw.doi AND ca.position = cw.author_position
  JOIN raw.oa_authorships a ON a.work_id = w.work_id AND a.position = cw.author_position
  WHERE cw.author_position IS NOT NULL AND coalesce(ca.family, '') <> ''
    AND lower(a.author_name) LIKE '%' || lower(ca.family) || '%'
    AND NOT EXISTS (SELECT 1 FROM raw.oa_authorships a2
                    WHERE a2.work_id = w.work_id AND upper(a2.orcid) = upper(cw.orcid));

CREATE TABLE person_papers AS
  SELECT person_id, work_id, min(author_position) AS author_position, group_concat(DISTINCT source) AS sources
  FROM links GROUP BY person_id, work_id;

DELETE FROM papers WHERE work_id NOT IN (SELECT work_id FROM person_papers);

CREATE TABLE authorships AS
  SELECT a.* FROM raw.oa_authorships a WHERE a.work_id IN (SELECT work_id FROM papers);
CREATE TABLE authorship_institutions AS
  SELECT ai.* FROM raw.oa_authorship_institutions ai WHERE ai.work_id IN (SELECT work_id FROM papers);
CREATE TABLE institutions AS
  SELECT i.* FROM raw.oa_institutions i
  WHERE i.institution_id IN (SELECT institution_id FROM authorship_institutions);

CREATE UNIQUE INDEX papers_id ON papers(work_id);
CREATE INDEX papers_doi ON papers(doi);
CREATE UNIQUE INDEX pp_id ON person_papers(person_id, work_id);
CREATE UNIQUE INDEX auth_id ON authorships(work_id, position);
CREATE INDEX auth_author ON authorships(author_id);
CREATE INDEX ai_id ON authorship_institutions(work_id, position);
CREATE UNIQUE INDEX inst_id ON institutions(institution_id);
""")
db.commit()

q = lambda s: db.execute(s).fetchall()
print("raw OpenAlex works:", q("SELECT count(*) FROM raw.oa_works")[0][0])
print("kept papers:", q("SELECT count(*) FROM papers")[0][0])
print("by type:", q("SELECT type, count(*) FROM papers GROUP BY 1 ORDER BY 2 DESC"))
print("person-paper links:", q("SELECT count(*) FROM person_papers")[0][0],
      "| by source:", q("SELECT sources, count(*) FROM person_papers GROUP BY 1"))
print("people with papers:", q("SELECT count(DISTINCT person_id) FROM person_papers")[0][0])
print("authorships:", q("SELECT count(*) FROM authorships")[0][0],
      "| institutions:", q("SELECT count(*) FROM institutions")[0][0])

# ---- spreadsheet ----
out = openpyxl.Workbook()
def sheet(ws, hdr, rows, widths):
    ws.append(hdr)
    for r in rows:
        ws.append(list(r))
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, w in enumerate(widths):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = w
    ws.freeze_panes = "B2"; ws.auto_filter.ref = ws.dimensions

sheet(out.active, ["Person", "ORCID", "List", "Year", "Type", "Title", "Journal / venue", "DOI", "Number of authors",
                   "Person's author position", "Field (OpenAlex)", "Topic (OpenAlex)", "Found via", "OpenAlex work"],
      q("""SELECT p.name, p.orcid, p.list, w.year, w.type, w.title, w.venue,
                  CASE WHEN w.doi IS NOT NULL THEN 'https://doi.org/' || w.doi END, w.n_authors, pp.author_position,
                  w.field, w.topic, pp.sources, w.work_id
           FROM person_papers pp JOIN people p USING (person_id) JOIN papers w USING (work_id)
           ORDER BY p.name, w.year DESC"""),
      [26, 21, 14, 7, 14, 70, 36, 34, 9, 9, 22, 30, 22, 14])
out.active.title = "Papers per person"
sheet(out.create_sheet("Papers per person (count)"), ["Person", "ORCID", "List", "Match certainty", "Papers"],
      q("""SELECT p.name, p.orcid, p.list, p.match_certainty, count(pp.work_id)
           FROM people p LEFT JOIN person_papers pp USING (person_id) GROUP BY p.person_id ORDER BY 5 DESC"""),
      [28, 22, 16, 20, 9])
out.save(xlsx_path)
print("saved", clean_path, "and", xlsx_path)
