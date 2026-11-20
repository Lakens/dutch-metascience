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
print(f"left out by hand check: {n_before - len(cands)} papers")

auth_rows = collections.defaultdict(list)
for wid, pos, aid, aname, orcid, countries in db.execute("""
    SELECT a.work_id, a.position, a.author_id, a.author_name, a.orcid, a.countries FROM oa_authorships a
    JOIN metascience_final m ON m.work_id = a.work_id AND m.prompt_version = ? AND m.is_metascience = 1""", (VERSION,)):
    auth_rows[wid].append((pos, aid, aname, orcid, countries or ""))
inst_rows = collections.defaultdict(list)   # (work, position) -> institution ids
for wid, pos, iid in db.execute("""
    SELECT ai.work_id, ai.position, ai.institution_id FROM oa_authorship_institutions ai
    JOIN metascience_final m ON m.work_id = ai.work_id AND m.prompt_version = ? AND m.is_metascience = 1""", (VERSION,)):
    inst_rows[(wid, pos)].append(iid)
inst_meta = {r[0]: dict(name=r[1], country=r[2], type=r[3], lineage=[x.strip() for x in (r[4] or "").split(";") if x.strip()])
             for r in db.execute("SELECT institution_id, name, country_code, type, lineage FROM oa_institutions")}

papers, paper_people, paper_nl_insts, paper_countries = [], {}, {}, {}
for (wid, title, year, venue, doi, n_auth, cited, wtype, kw, field, topic, cat, expl, x, y, cl) in cands:
    people, nl_insts, countries = [], set(), set()
    for pos, aid, aname, orcid, ctry in sorted(auth_rows.get(wid, [])):
        insts = inst_rows.get((wid, pos), [])
        dutch_here = any(inst_meta.get(i, {}).get("country") == "NL" for i in insts)
        countries.update(c for c in ctry.split("; ") if c)
        nl_insts.update(i for i in insts if inst_meta.get(i, {}).get("country") == "NL")
        pk = listed.get(aid)
        if pk is None and dutch_here and aid:
            pk = "A:" + aid
            if pk not in person_info:
                person_info[pk] = dict(name=aname, orcid=orcid or "", listed=False)
        if pk and pk not in people:
            people.append(pk)
    if not people:      # no Dutch author and no one from our list: not part of the Dutch landscape
        continue
    paper_people[wid], paper_nl_insts[wid], paper_countries[wid] = people, nl_insts, countries
    papers.append(dict(id=wid, t=title, y=year, v=venue or "", doi=doi or "", na=n_auth or 0, c=cited or 0,
                       ty=wtype, cat=cat, ex=expl or "", kw=[k for k in (kw or "").split("; ") if k][:8],
                       f=field or "", tp=topic or "", x=None if x is None else round(x, 3),
                       yy=None if y is None else round(y, 3), cl=cl, p=people,
                       co=sorted(countries - {"NL"})))
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

def top_level(iid):
    """the highest Dutch parent (e.g. Donders Institute -> Radboud University). A parent in another country is
    skipped, so a Dutch branch stays itself (Elsevier Amsterdam is not counted as RELX Group, United Kingdom)."""
    lin = geo.get(iid, {}).get("lineage") or [iid]
    dutch = [x for x in lin if is_nl(x)] or [iid]
    tops = [x for x in dutch if not any(y != x and is_nl(y) for y in geo.get(x, {}).get("lineage") or [x])]
    return tops[0] if tops else dutch[0]

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

person_inst = collections.defaultdict(collections.Counter)
for wid, people in paper_people.items():
    for pos, aid, *_ in auth_rows.get(wid, []):
        pk = listed.get(aid) or ("A:" + aid if ("A:" + aid) in person_info else None)
        if pk:
            for i in inst_rows.get((wid, pos), []):
                if inst_meta.get(i, {}).get("country") == "NL":
                    person_inst[pk][top_level(i)] += 1

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
        ins=[i for i, _ in person_inst[pk].most_common(3)],
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

meta = dict(n_papers=len(papers), n_people=len(people_out), n_listed=sum(r["l"] for r in people_out),
            n_institutions=len(insts_out), n_countries=len(countries_out), n_links=len(edges_out),
            years=[min(year_total), max(year_total)], year_total={str(y): c for y, c in sorted(year_total.items())},
            categories=sorted(set(p["cat"] for p in papers)), max_authors_for_links=MAX_AUTHORS_FOR_LINKS,
            model="gpt-oss:20b (Ollama, SURF Research Cloud)", prompt_version=VERSION, built="November 2026",
            n_excluded_by_hand=n_before - len(cands), n_no_abstract=sum(1 for p in papers if not db.execute(
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
