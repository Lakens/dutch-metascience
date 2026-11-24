"""Yearly number of all publications with an author at a Dutch institution, the denominator of the overview chart.

Usage: python -I fetch_publication_totals.py <site data folder>
Needs OPENALEX_API_KEY. Run after build_site_data.py (reads the years from meta.json).

Counts works in OpenAlex with an author at an institution in the Netherlands, per publication year, with the same rules
as the papers on the site (build_site_data.py): the same work types; preprints only with a DOI; no deposits on OSF,
Zenodo or Figshare. Deposits are left out by their repository here, where build_site_data.py uses the DOI prefix; they
are well under 1% of the total. OpenAlex counts each work once, but does not join a preprint with its journal version,
as the site does. Two requests (one per year grouping), not one per paper.
Writes <site data folder>/publication_totals.json: {"rule": text, "fetched": date, "n": {year: count}}.
"""
import sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oa_store import oa_get

sys.stdout.reconfigure(encoding="utf-8")
data_dir = sys.argv[1]
years = json.load(open(os.path.join(data_dir, "meta.json"), encoding="utf-8"))["years"]

# must stay the same as KEEP_TYPES in build_site_data.py
KEEP_TYPES = ("article", "review", "preprint", "book", "book-chapter", "conference-paper", "editorial", "letter")
DEPOSITS = ("S7407050956", "S4306400562", "S4377196282")   # Open Science Framework, Zenodo, Figshare
base = (f"authorships.institutions.country_code:NL,publication_year:{years[0]}-{years[1]},"
        + ",".join(f"primary_location.source.id:!{s}" for s in DEPOSITS))


def per_year(extra):
    res = oa_get("works", {"filter": base + "," + extra, "group_by": "publication_year", "per-page": 200})
    if not res or "group_by" not in res:
        raise SystemExit("STOPPED: no answer from OpenAlex")
    return {int(g["key"]): g["count"] for g in res["group_by"]}


other = per_year("type:" + "|".join(t for t in KEEP_TYPES if t != "preprint"))
pre = per_year("type:preprint,has_doi:true")
n = {y: other.get(y, 0) + pre.get(y, 0) for y in range(years[0], years[1] + 1)}
out = dict(rule="works in OpenAlex with an author at a Dutch institution; types " + ", ".join(KEEP_TYPES)
           + "; preprints only with a DOI; deposits on OSF, Zenodo and Figshare left out",
           fetched=datetime.date.today().isoformat(), n={str(y): c for y, c in n.items()})
with open(os.path.join(data_dir, "publication_totals.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print("publications per year:", {y: n[y] for y in n if y % 5 == 0 or y >= years[1] - 1})
