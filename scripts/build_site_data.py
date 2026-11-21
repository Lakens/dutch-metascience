"""Prepare the JSON data for the website from the databases.

Usage: python -I build_site_data.py <raw database.sqlite> <output data folder>
Needs OPENALEX_API_KEY (institution coordinates and parents). Publishes only public bibliographic data and the
AI judgements: never emails, roles or community memberships from the source spreadsheet.
"""
import sys, os, re, json, collections, itertools, math, sqlite3
import requests
import networkx as nx
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oa_store import oa_get, short

sys.stdout.reconfigure(encoding="utf-8")
raw_path, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
db = sqlite3.connect(raw_path)
VERSION = "v2+v4"  # metascience = v2 and the stricter check v4 both say so (view metascience_final)
MAX_AUTHORS_FOR_LINKS = 30

def dump(name, obj):
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {name}: {os.path.getsize(os.path.join(out_dir, name)) / 1e6:.2f} MB", flush=True)

# ---------------------------------------------------------------- people on our list
listed = {}          # openalex author id -> person key
person_info = {}     # person key -> dict
for pid, name, orcid, ids, lst in db.execute("SELECT person_id, name, orcid, openalex_ids, list FROM oa_people"):
    if lst != "In NL":
        continue
    pk = "P:" + pid
    person_info[pk] = dict(name=name, orcid=orcid or "", listed=True)
    for x in (ids or "").split(";"):
        if x.strip():
            listed[x.strip()] = pk

# ---------------------------------------------------------------- metascience papers
cands = db.execute("""
  SELECT w.work_id, w.title, w.year, w.venue, w.doi, w.n_authors, w.cited_by, w.type, w.keywords,
         w.field, w.topic, m.category, m.explanation, pm.x, pm.y, pm.cluster
  FROM metascience_final m JOIN oa_works w USING (work_id)
  LEFT JOIN paper_map pm USING (work_id)
  WHERE m.prompt_version = ? AND m.is_metascience = 1""", (VERSION,)).fetchall()
# papers that a hand check found not to be metascience are left out (scripts/excluded_by_hand.csv)
import csv
EXCLUDED = {r["work_id"] for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                   "excluded_by_hand.csv"), encoding="utf-8"))}
n_before = len(cands)
cands = [c for c in cands if c[0] not in EXCLUDED]
n_excluded_by_hand = n_before - len(cands)
print(f"left out by hand check: {n_excluded_by_hand} papers")
# only scientific papers: the same rules as build_clean.py (SCIENTIFIC), which the publication lists of the people on
# our list already passed; papers found by the OpenAlex search must pass them too
KEEP_TYPES = ("article", "review", "preprint", "book", "book-chapter", "conference-paper", "editorial", "letter")
def is_scientific(wtype, doi, venue):
    doi, venue = (doi or "").lower(), venue or ""
    return (wtype in KEEP_TYPES
            and not doi.startswith(("10.17605/", "10.5281/", "10.6084/"))      # OSF pages, Zenodo and Figshare deposits
            and not venue.startswith(("Zenodo", "Figshare")) and venue != "Open Science Framework"
            and not (wtype == "preprint" and not doi))                       # OSF pages listed as preprints have no DOI
n_before_sci = len(cands)
cands = [c for c in cands if is_scientific(c[7], c[4], c[3])]
n_not_paper = n_before_sci - len(cands)
print(f"left out as not a scientific paper (deposits, reports, datasets and the like): {n_not_paper}")

auth_rows = collections.defaultdict(list)
raw_aff = {}                                # (work, position) -> the affiliation text as the publisher gave it
for wid, pos, aid, aname, orcid, countries, raw in db.execute("""
    SELECT a.work_id, a.position, a.author_id, a.author_name, a.orcid, a.countries, a.raw_affiliations
    FROM oa_authorships a
    JOIN metascience_final m ON m.work_id = a.work_id AND m.prompt_version = ? AND m.is_metascience = 1""", (VERSION,)):
    auth_rows[wid].append((pos, aid, aname, orcid, countries or ""))
    raw_aff[(wid, pos)] = (raw or "").strip()
inst_rows = collections.defaultdict(list)   # (work, position) -> institution ids
for wid, pos, iid in db.execute("""
    SELECT ai.work_id, ai.position, ai.institution_id FROM oa_authorship_institutions ai
    JOIN metascience_final m ON m.work_id = ai.work_id AND m.prompt_version = ? AND m.is_metascience = 1""", (VERSION,)):
    inst_rows[(wid, pos)].append(iid)
inst_meta = {r[0]: dict(name=r[1], country=r[2], type=r[3], lineage=[x.strip() for x in (r[4] or "").split(";") if x.strip()])
             for r in db.execute("SELECT institution_id, name, country_code, type, lineage FROM oa_institutions")}

def shared_mixed(wid):
    """True when the publisher gave every author one and the same affiliation text, and that text names institutions
    in the Netherlands and in other countries (for example "From University of Oxford ... and University Medical
    Center Utrecht ..."). OpenAlex then gives every author all of those institutions, so the paper cannot tell which
    authors were Dutch (the PRISMA 2009 statement in Annals of Internal Medicine made 9 foreign authors Dutch)."""
    rows = auth_rows.get(wid, [])
    texts = {raw_aff.get((wid, r[0]), "") for r in rows}
    if len(rows) < 2 or len(texts) != 1 or not next(iter(texts)):
        return False
    ctys = {inst_meta.get(i, {}).get("country") for r in rows for i in inst_rows.get((wid, r[0]), [])}
    return "NL" in ctys and len(ctys - {"NL", None}) > 0

def is_dutch_inst(i):
    return inst_meta.get(i, {}).get("country") == "NL"

def combined_block(wid):
    """Authorships with a combined address block in the style of some medical journals: the text starts with "From",
    at least two authors have a text that starts the same way (first 80 characters), and the institutions OpenAlex
    took from it are in the Netherlands and other countries. The texts can differ slightly between authors, so
    shared_mixed misses them (Journal of Clinical Oncology 2010: "From the Memorial Sloan-Kettering Cancer Center,
    New York, NY; Lund University ...; and Erasmus Medical Center, Rotterdam" for all 9 authors)."""
    rows = auth_rows.get(wid, [])
    starts = collections.Counter(raw_aff.get((wid, r[0]), "")[:80] for r in rows)
    out = set()
    for r in rows:
        t = raw_aff.get((wid, r[0]), "")
        ctys = {inst_meta.get(i, {}).get("country") for i in inst_rows.get((wid, r[0]), [])}
        if t.startswith("From ") and starts[t[:80]] >= 2 and "NL" in ctys and len(ctys - {"NL", None}) > 0:
            out.add((wid, r[0]))
    return out

# authorships whose Dutch institution may belong to a co-author (shared_mixed or combined_block); such a Dutch
# institution counts only for authors who are at a Dutch institution on another paper with their own text
mixed_papers = {c[0] for c in cands if shared_mixed(c[0])}
weak = {(w, r[0]) for w in mixed_papers for r in auth_rows.get(w, [])} | {a for c in cands for a in combined_block(c[0])}
dutch_on_own_text = {aid for c in cands for pos, aid, *_ in auth_rows.get(c[0], [])
                     if aid and (c[0], pos) not in weak and any(is_dutch_inst(i) for i in inst_rows.get((c[0], pos), []))}
print(f"papers with one shared affiliation text naming the Netherlands and other countries: {len(mixed_papers)}; "
      f"papers with such authorships (also combined blocks starting with 'From'): {len({w for w, _ in weak})}")

papers, paper_people, paper_nl_insts, paper_countries = [], {}, {}, {}
n_abroad = 0
for (wid, title, year, venue, doi, n_auth, cited, wtype, kw, field, topic, cat, expl, x, y, cl) in cands:
    people, nl_insts, countries = [], set(), set()
    listed_unknown = False       # someone from our list has no institution on this paper
    for pos, aid, aname, orcid, ctry in sorted(auth_rows.get(wid, [])):
        insts = inst_rows.get((wid, pos), [])
        listed_unknown = listed_unknown or (aid in listed and not insts)
        dutch_here = any(is_dutch_inst(i) for i in insts)
        countries.update(c for c in ctry.split("; ") if c)
        nl_insts.update(i for i in insts if is_dutch_inst(i))
        pk = listed.get(aid)
        if pk is None and dutch_here and aid and ((wid, pos) not in weak or aid in dutch_on_own_text):
            pk = "A:" + aid
            if pk not in person_info:
                person_info[pk] = dict(name=aname, orcid=orcid or "", listed=False)
        if pk and pk not in people:
            people.append(pk)
    if not people:      # no Dutch author and no one from our list: not part of the Dutch landscape
        continue
    if not nl_insts and not listed_unknown:
        # no Dutch institution, and the institutions of the people from our list on it are known (for example a paper
        # from before someone on our list moved to the Netherlands). Papers where their institution is unknown are
        # kept: they are mostly Dutch preprints and theses
        n_abroad += 1
        continue
    paper_people[wid], paper_nl_insts[wid], paper_countries[wid] = people, nl_insts, countries
    papers.append(dict(id=wid, t=title, y=year, v=venue or "", doi=doi or "", na=n_auth or 0, c=cited or 0,
                       ty=wtype, cat=cat, ex=expl or "", kw=[k for k in (kw or "").split("; ") if k][:8],
                       f=field or "", tp=topic or "", x=None if x is None else round(x, 3),
                       yy=None if y is None else round(y, 3), cl=cl, p=people,
                       co=sorted(countries - {"NL"})))
print(f"left out because every known institution is abroad: {n_abroad} papers")

# copies of one paper (a preprint and its journal version, preprint versions, or a statement published in several
# journals) are shown once: same title (letters and digits only), at least one shared person, and at least 5 words in
# the title, so that titles such as "Editorial" or "Authors' reply" are never joined. The copy kept is the journal
# version (not a preprint), and among those the most cited; its own citation count is used, not a sum.
def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())
by_title = collections.defaultdict(list)
for p in papers:
    if len((p["t"] or "").split()) >= 5:
        by_title[norm_title(p["t"])].append(p)
dropped, copy_of = set(), {}   # copy_of: removed copy -> the paper kept (written to copies.json, for goals.json)
for group in by_title.values():
    rest = sorted(group, key=lambda p: (p["ty"] == "preprint", -p["c"], p["id"]))
    while rest:
        keep, rest = rest[0], rest[1:]
        copies = [p for p in rest if set(p["p"]) & set(keep["p"])]
        dropped.update(p["id"] for p in copies)
        copy_of.update((p["id"], keep["id"]) for p in copies)
        rest = [p for p in rest if p not in copies]
papers = [p for p in papers if p["id"] not in dropped]
for wid in dropped:
    del paper_people[wid], paper_nl_insts[wid], paper_countries[wid]
print(f"left out as copies of another paper: {len(dropped)} papers")
print("papers in the Dutch metascience landscape:", len(papers), flush=True)

# ---------------------------------------------------------------- institutions: parents and coordinates
needed = set()
for s in paper_nl_insts.values():
    for i in s:
        needed.add(i); needed.update(inst_meta.get(i, {}).get("lineage", []))
geo = {}
ids = sorted(needed)
for i in range(0, len(ids), 50):
    d = oa_get("institutions", {"filter": "openalex:" + "|".join(ids[i:i + 50]), "per-page": 50,
                                "select": "id,display_name,country_code,type,lineage,geo"})
    for r in (d or {}).get("results", []):
        g = r.get("geo") or {}
        geo[short(r["id"])] = dict(name=r["display_name"], country=r.get("country_code"), type=r.get("type"),
                                   lineage=[short(x) for x in r.get("lineage") or []],
                                   lat=g.get("latitude"), lon=g.get("longitude"), city=g.get("city"))

def is_nl(x):
    return (geo.get(x, {}).get("country") or inst_meta.get(x, {}).get("country")) == "NL"

# Research institutes of a medical centre that OpenAlex records only as "related", not as part of it, so the
# lineage rule below cannot merge them (checked 20 Nov 2026: most of their papers also list the medical centre:
# Amsterdam Public Health 170 of 196, Amsterdam Neuroscience 28 of 30, Radboud Institute for Health Sciences 40 of 46).
# Checked 21 Nov 2026, papers that also list Amsterdam UMC: Amsterdam Movement Sciences 23 of 33, Amsterdam
# Reproduction Development 11 of 11, Cancer Center Amsterdam 5 of 6, Amsterdam Gastroenterology Endocrinology
# Metabolism 2 of 4, Amsterdam institute for Immunology and Infectious Diseases 4 of 4, Amsterdam Cardiovascular
# Sciences 2 of 2 (without the merge, these institutes won ties against Amsterdam UMC in main_institution).
MERGE_INTO = {
    "Amsterdam Public Health": "Amsterdam University Medical Centers",
    "Amsterdam Neuroscience": "Amsterdam University Medical Centers",
    "Amsterdam Movement Sciences": "Amsterdam University Medical Centers",
    "Amsterdam Reproduction Development": "Amsterdam University Medical Centers",
    "Cancer Center Amsterdam": "Amsterdam University Medical Centers",
    "Amsterdam Gastroenterology Endocrinology Metabolism": "Amsterdam University Medical Centers",
    "Amsterdam institute for Immunology and Infectious Diseases": "Amsterdam University Medical Centers",
    "Amsterdam Cardiovascular Sciences": "Amsterdam University Medical Centers",
    "Radboud Institute for Health Sciences": "Radboud University Medical Center",
}
_name_to_id = {}
for _i, _g in geo.items():
    _name_to_id.setdefault(_g.get("name"), _i)
_missing = [n for pair in MERGE_INTO.items() for n in pair if n not in _name_to_id]
assert not _missing, f"institutions to merge not found in the data: {_missing}"
MERGE_IDS = {_name_to_id[a]: _name_to_id[b] for a, b in MERGE_INTO.items()}

def top_level(iid):
    """the highest Dutch parent (e.g. Donders Institute -> Radboud University). A parent in another country is
    skipped, so a Dutch branch stays itself (Elsevier Amsterdam is not counted as RELX Group, United Kingdom).
    Institutes in MERGE_INTO are counted under their medical centre."""
    lin = geo.get(iid, {}).get("lineage") or [iid]
    dutch = [x for x in lin if is_nl(x)] or [iid]
    tops = [x for x in dutch if not any(y != x and is_nl(y) for y in geo.get(x, {}).get("lineage") or [x])]
    top = tops[0] if tops else dutch[0]
    return MERGE_IDS.get(top, top)

paper_tops = {wid: sorted({top_level(i) for i in s}) for wid, s in paper_nl_insts.items()}
for p in papers:
    p["in"] = paper_tops[p["id"]]

# ---------------------------------------------------------------- people: aggregate
G = nx.Graph()
pp = collections.defaultdict(list)
for p in papers:
    for pk in p["p"]:
        pp[pk].append(p)
    if p["na"] <= MAX_AUTHORS_FOR_LINKS:
        for a, b in itertools.combinations(sorted(set(p["p"])), 2):
            G.add_edge(a, b, weight=G[a][b]["weight"] + 1 if G.has_edge(a, b) else 1)
G.add_nodes_from(pp)
comms = nx.community.louvain_communities(G, weight="weight", seed=42, resolution=1.0)
comm_of = {n: i for i, c in enumerate(sorted(comms, key=len, reverse=True)) for n in c}

person_inst = collections.defaultdict(collections.Counter)         # person -> institution -> number of papers
person_inst_shared = collections.defaultdict(collections.Counter)   # from shared texts (shared_mixed): used only
person_inst_last = collections.defaultdict(dict)                    # when a person has no other Dutch institution
paper_year = {p["id"]: p["y"] or 0 for p in papers}                 # person -> institution -> latest year
for wid, people in paper_people.items():
    for pos, aid, *_ in auth_rows.get(wid, []):
        pk = listed.get(aid) or ("A:" + aid if ("A:" + aid) in person_info else None)
        if pk in people:
            for t in {top_level(i) for i in inst_rows.get((wid, pos), []) if is_dutch_inst(i)}:   # once per paper
                (person_inst_shared if (wid, pos) in weak else person_inst)[pk][t] += 1
                person_inst_last[pk][t] = max(person_inst_last[pk].get(t, 0), paper_year[wid])

def inst_info(i):
    return geo.get(i, {}) or inst_meta.get(i, {})

def main_institution(pk):
    """The Dutch institution on most of the person's papers. A tie between a medical centre and a university in the
    same city (UMC Groningen and the University of Groningen are often both in one address) goes to the medical
    centre; any other tie goes to the institution on the person's most recent paper, then to the name."""
    cnt = person_inst[pk] or person_inst_shared[pk]
    if not cnt:
        return [], 0
    top = max(cnt.values())
    tied = sorted(i for i, c in cnt.items() if c == top)
    if len(tied) > 1:
        cities = {inst_info(i).get("city") for i in tied if inst_info(i).get("type") == "education"}
        med = [i for i in tied if inst_info(i).get("type") == "healthcare" and inst_info(i).get("city") in cities]
        if med:
            tied = med
        tied.sort(key=lambda i: (-person_inst_last[pk].get(i, 0), inst_info(i).get("name") or i))
    return tied[:1], len([i for i, c in cnt.items() if c == top])

_ties = collections.Counter()
for pk in pp:
    shown, n_tied = main_institution(pk)
    if n_tied > 1:
        _ties[inst_info(shown[0]).get("name")] += 1
print(f"people whose top institution is tied: {sum(_ties.values())} of {len(pp)}; shown after breaking the tie:",
      ", ".join(f"{k} {n}" for k, n in _ties.most_common(8)), flush=True)

people_out = []
for pk, plist in pp.items():
    info = person_info[pk]
    years = [p["y"] for p in plist if p["y"]]
    kws = collections.Counter(k for p in plist for k in p["kw"])
    people_out.append(dict(
        id=pk, n=info["name"], o=info["orcid"], l=info["listed"], k=len(plist),
        y0=min(years) if years else None, y1=max(years) if years else None,
        cats=dict(collections.Counter(p["cat"] for p in plist)),
        cls=dict(collections.Counter(str(p["cl"]) for p in plist if p["cl"] is not None)),
        # only the institution on most of the person's papers (main_institution): OpenAlex sometimes gives an author
        # a co-author's institution (when the publisher's affiliation text runs two addresses together), so a second
        # institution is often wrong
        ins=main_institution(pk)[0],
        kw=[k for k, _ in kws.most_common(8)], cm=comm_of.get(pk, -1),
        deg=G.degree(pk) if pk in G else 0))
people_out.sort(key=lambda r: -r["k"])
edges_out = [[a, b, d["weight"]] for a, b, d in G.edges(data=True)]
print("people:", len(people_out), "| listed:", sum(r["l"] for r in people_out), "| links:", len(edges_out), flush=True)

# ---------------------------------------------------------------- institutions out
inst_papers = collections.defaultdict(list)
for p in papers:
    for t in p["in"]:
        inst_papers[t].append(p)
insts_out = []
for t, plist in inst_papers.items():
    g = geo.get(t, {})
    insts_out.append(dict(id=t, n=g.get("name") or inst_meta.get(t, {}).get("name", t), ty=g.get("type"),
                          lat=g.get("lat"), lon=g.get("lon"), city=g.get("city"), k=len(plist),
                          years=dict(collections.Counter(str(p["y"]) for p in plist if p["y"])),
                          cats=dict(collections.Counter(p["cat"] for p in plist))))
insts_out.sort(key=lambda r: -r["k"])
# the 14 Dutch universities (for the flow diagram "which institution works on what")
DUTCH_UNIVERSITIES = ["University of Amsterdam", "Leiden University", "Utrecht University", "Vrije Universiteit Amsterdam",
                      "University of Groningen", "Maastricht University", "Radboud University Nijmegen",
                      "Tilburg University", "Erasmus University Rotterdam", "Delft University of Technology",
                      "Eindhoven University of Technology", "University of Twente", "Wageningen University & Research",
                      "Open University of the Netherlands"]
uni_ids = [r["id"] for r in insts_out if r["n"] in DUTCH_UNIVERSITIES]
missing = set(DUTCH_UNIVERSITIES) - {r["n"] for r in insts_out}
assert not missing, f"universities not found in the data: {missing}"
foreign = [r["n"] for r in insts_out if not is_nl(r["id"])]
print("institutions:", len(insts_out), "| not in the Netherlands (should be none):", foreign[:5], flush=True)
top_inst = [r["id"] for r in insts_out[:16]]
chord = [[0] * len(top_inst) for _ in top_inst]
for p in papers:
    s = [top_inst.index(t) for t in p["in"] if t in top_inst]
    for a, b in itertools.combinations(sorted(set(s)), 2):
        chord[a][b] += 1; chord[b][a] += 1

# ---------------------------------------------------------------- countries (ISO2 -> ISO3 and name)
wc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_countries.json")
if not os.path.exists(wc_path):
    r = requests.get("https://cdn.jsdelivr.net/npm/world-countries@5.1.0/countries.json", timeout=60)
    r.raise_for_status()
    open(wc_path, "w", encoding="utf-8").write(r.text)
wc = {c["cca2"]: (c["cca3"], c["name"]["common"]) for c in json.load(open(wc_path, encoding="utf-8"))}
ctry = collections.Counter(c for p in papers for c in p["co"])
countries_out = [dict(iso2=c, iso3=wc.get(c, ("", c))[0], n=wc.get(c, ("", c))[1], k=k) for c, k in ctry.most_common()]

# ---------------------------------------------------------------- terms over time
TERMS = {"preregistration": r"pre-?regist", "registered report": r"registered reports?",
         "open science": r"open science", "replication crisis": r"replication crisis|reproducibility crisis",
         "p-hacking": r"p-hack", "questionable research practices": r"questionable research practice",
         "publication bias": r"publication bias", "data sharing": r"data sharing|open data",
         "Bayes factor": r"bayes factor", "equivalence test": r"equivalence test",
         "research integrity": r"research integrity", "peer review": r"peer review",
         "research assessment": r"research assessment|research evaluation|recognition and rewards",
         "statcheck": r"statcheck", "many labs": r"many labs|multi-?lab", "reproducibility": r"reproducib"}
abstracts = dict(db.execute("""SELECT w.work_id, lower(coalesce(w.title,'') || ' ' || coalesce(w.abstract,''))
                               FROM oa_works w JOIN metascience_final m USING (work_id)
                               WHERE m.prompt_version = ? AND m.is_metascience = 1""", (VERSION,)))
terms_out = {t: collections.Counter() for t in TERMS}
year_total = collections.Counter(p["y"] for p in papers if p["y"])
for p in papers:
    txt = abstracts.get(p["id"], "")
    for t, rx in TERMS.items():
        if p["y"] and re.search(rx, txt):
            terms_out[t][p["y"]] += 1
terms_json = {t: {str(y): c for y, c in sorted(cnt.items())} for t, cnt in terms_out.items()}

# ---------------------------------------------------------------- keywords: counts, co-occurrence, periods
kw_count = collections.Counter(k for p in papers for k in p["kw"])
top_kw = [k for k, _ in kw_count.most_common(150)]
co = collections.Counter()
for p in papers:
    ks = sorted(set(k for k in p["kw"] if k in top_kw))
    co.update(itertools.combinations(ks, 2))
periods = [(2005, 2008), (2009, 2012), (2013, 2016), (2017, 2020), (2021, 2023), (2024, 2026)]
kw_period = {f"{a}-{b}": collections.Counter(k for p in papers if p["y"] and a <= p["y"] <= b for k in p["kw"])
             for a, b in periods}
keywords_out = dict(
    nodes=[dict(k=k, n=kw_count[k]) for k in top_kw],
    links=[[a, b, n] for (a, b), n in co.items() if n >= 3],
    periods={per: [[k, c] for k, c in cnt.most_common(40)] for per, cnt in kw_period.items()})

# cluster sizes: papers of that cluster that are on the site
cl_count = collections.Counter(p["cl"] for p in papers if p["cl"] is not None)
clusters = [dict(id=c, name=n, desc=d, k=cl_count.get(c, 0)) for c, n, d, k in
            db.execute("SELECT cluster, name, description, n_papers FROM cluster_names ORDER BY cluster")] \
    if db.execute("SELECT name FROM sqlite_master WHERE name='cluster_names'").fetchone() else []
# revised names (cluster_names.json), used only for clusters whose model name is unchanged (same clustering)
_names_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cluster_names.json")
if os.path.exists(_names_path):
    _rev = {r["id"]: r for r in json.load(open(_names_path, encoding="utf-8"))["clusters"]}
    for c in clusters:
        r = _rev.get(c["id"])
        if r and r["model_name"] == c["name"]:
            c["name"], c["desc"] = r["name"], r["desc"]
        else:
            print(f"  WARNING: cluster {c['id']} ({c['name']}) has no revised name in cluster_names.json", flush=True)

meta = dict(n_papers=len(papers), n_people=len(people_out), n_listed=sum(r["l"] for r in people_out),
            n_institutions=len(insts_out), n_countries=len(countries_out), n_links=len(edges_out),
            years=[min(year_total), max(year_total)], year_total={str(y): c for y, c in sorted(year_total.items())},
            categories=sorted(set(p["cat"] for p in papers)), max_authors_for_links=MAX_AUTHORS_FOR_LINKS,
            model="gpt-oss:20b (Ollama, SURF Research Cloud)", prompt_version=VERSION, built="November 2026",
            n_excluded_by_hand=n_excluded_by_hand, n_not_paper=n_not_paper, n_abroad=n_abroad, n_copies=len(dropped),
            n_mixed_affiliation_papers=len({w for w, _ in weak}), n_no_abstract=sum(1 for p in papers if not db.execute(
                "SELECT abstract FROM oa_works WHERE work_id=?", (p["id"],)).fetchone()[0]))

dump("meta.json", meta)
dump("papers.json", papers)
dump("people.json", people_out)
dump("edges.json", edges_out)
dump("institutions.json", dict(list=insts_out, chord_ids=top_inst, chord=chord, universities=uni_ids))
dump("countries.json", countries_out)
dump("terms.json", dict(terms=terms_json, totals={str(y): c for y, c in sorted(year_total.items())}))
dump("keywords.json", keywords_out)
dump("clusters.json", clusters)
dump("copies.json", copy_of)
