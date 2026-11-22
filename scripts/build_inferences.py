"""Data for the Inferences page: possible collaborations, rising themes, similar ongoing NWO projects, and (from a
hand-written file) shared questions and goals.

Usage: python -I build_inferences.py <site data folder> <embeddings.npy> <embedding_ids.txt> [goals.json]
       [project_groups.json]
Reads the site's papers/people/edges/clusters/institutions JSON and the paper embeddings (bge-m3, from
embed_and_map.py); writes <site data folder>/inferences.json.

1. Possible collaborations: each active researcher (>= 3 metascience papers, one in 2024 or later) gets the 5 most similar
   researchers (similarity >= MIN_SIM) they have never written a paper with, and separately the 5 most similar they
   wrote a little with (joint papers at most LITTLE of the papers of the one with fewer papers). Only papers with at
   most MAX_AUTHORS authors count as writing together. A person's profile is the average embedding of their papers,
   after subtracting the average of all papers (otherwise every metascientist looks alike). Evidence per pair: the
   clusters both work in, and the two papers (one each, not written together) that are closest in content.
   Communities: a map of the research communities (Louvain, from the site data), placed by the similarity of their
   papers (SMACOF), with their joint papers.
2. Rising themes: a multinomial logistic regression of each paper's cluster on year (a natural cubic spline; the
   number of knots chosen by QAIC), fitted to the papers from 2005 on (share_model.py). Shares vary more from year
   to year than a multinomial model allows (one project often brings several papers on one theme in one year), so the
   covariance is multiplied by the Pearson dispersion of the most flexible model (quasi-likelihood), and the number of
   knots is chosen by QAIC (AIC with the log likelihood divided by that dispersion). It gives every cluster a share
   per year with a 95% band, and the change in share over the last four years with a 95% interval: a cluster is
   "rising" or "declining" only when that interval excludes zero.
   New authors per cluster: a person enters a cluster in the year of their first paper in it (papers with at most
   MAX_AUTHORS authors, as for the co-author network); "new to metascience" when that is also their first paper on the
   site, otherwise "from another theme". Entries in the last four complete years against the four years before,
   with a 95% interval from resampling the papers (one paper can bring several people at once).
   Rising keywords: share of papers with the keyword, 2024-2026 against 2019-2023.
3. Shared questions and goals: copied from goals.json (written by Claude from the 2025-2026 abstracts), after
   checking that every cited paper is on the site.
4. Similar ongoing projects: the ongoing metascience-related NWO projects (embed_projects.py; their fingerprints,
   project_embeddings.npy and project_ids.txt, lie next to embeddings.npy). Groups with a shared aim come from
   project_groups.json (written and checked by Claude reviewers, project_groups_instructions.md). Computed here: the
   most similar pairs of projects that are NOT in the same group (the groups already show those), from different
   funding schemes, with no organisation and no team member in common, and for every project the
   N_NEAR papers on the site that are closest in content. Similarity as for people: fingerprints minus the average
   of the site's papers, then the cosine.
"""
import sys, os, json, collections, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from share_model import design, fit_multinomial, knots_for, draws_of_shares, shares, dispersion

sys.stdout.reconfigure(encoding="utf-8")
data_dir, emb_path, ids_path = sys.argv[1:4]
goals_path = sys.argv[4] if len(sys.argv) > 4 else None
groups_path = sys.argv[5] if len(sys.argv) > 5 else None
load = lambda n: json.load(open(os.path.join(data_dir, n + ".json"), encoding="utf-8"))
papers, people, edges, clusters = load("papers"), load("people"), load("edges"), load("clusters")
cname = {c["id"]: c["name"] for c in clusters}
pid = {p["id"]: p for p in papers}

# ---------------------------------------------------------------- embeddings of the site papers
X = np.load(emb_path).astype(np.float32)
emb_ids = open(ids_path).read().split()
row = {w: i for i, w in enumerate(emb_ids)}
site_rows = [row[p["id"]] for p in papers if p["id"] in row]
mean_vec = X[site_rows].mean(axis=0)
def unit(v):
    n = np.linalg.norm(v); return v / n if n else v
paper_vec = {p["id"]: unit(X[row[p["id"]]] - mean_vec) for p in papers if p["id"] in row}

# ---------------------------------------------------------------- 1. possible collaborations
LAST_YEAR = max(p["y"] or 0 for p in papers)
papers_of = collections.defaultdict(list)
for p in papers:
    for a in p["p"]:
        papers_of[a].append(p)
# working together = a joint paper with at most MAX_AUTHORS authors (as for the lines of the co-author network): one
# Many Labs paper with 190 authors does not make its 21 Dutch authors collaborators
MAX_AUTHORS = 30
coauthors = collections.defaultdict(set)
joint = collections.Counter()   # (a, b), a < b -> number of joint papers
for p in papers:
    if (p["na"] or 0) > MAX_AUTHORS:
        continue
    for a, b in itertools.combinations(sorted(set(p["p"])), 2):
        coauthors[a].add(b); coauthors[b].add(a); joint[(a, b)] += 1
active = [x for x in people if x["k"] >= 3 and (x["y1"] or 0) >= 2024]   # a paper in 2024 or later: still active
pv = {x["id"]: unit(np.mean([paper_vec[p["id"]] for p in papers_of[x["id"]] if p["id"] in paper_vec], axis=0)) for x in active}
A = [x["id"] for x in active]
M = np.stack([pv[a] for a in A])
S = M @ M.T
byp = {x["id"]: x for x in people}

def cluster_share(a):
    c = collections.Counter(p["cl"] for p in papers_of[a] if p["cl"] is not None)
    n = sum(c.values()) or 1
    return {k: v / n for k, v in c.items()}

def evidence(a, b):
    sa, sb = cluster_share(a), cluster_share(b)
    shared = sorted(set(sa) & set(sb), key=lambda k: -min(sa[k], sb[k]))[:2]
    # papers both wrote are left out, otherwise a joint paper is shown as the closest pair (twice the same title)
    both = {p["id"] for p in papers_of[a]} & {p["id"] for p in papers_of[b]}
    pa = [p["id"] for p in papers_of[a] if p["id"] in paper_vec and p["id"] not in both]
    pb = [p["id"] for p in papers_of[b] if p["id"] in paper_vec and p["id"] not in both]
    if not pa or not pb:   # one of them has only joint papers
        pa = [p["id"] for p in papers_of[a] if p["id"] in paper_vec]
        pb = [p["id"] for p in papers_of[b] if p["id"] in paper_vec]
    sims = np.stack([paper_vec[x] for x in pa]) @ np.stack([paper_vec[x] for x in pb]).T
    i, j = np.unravel_index(np.argmax(sims), sims.shape)
    return [cname[k] for k in shared], [pa[i], pb[j]]

K = 5
# two kinds of suggestions: pairs that never wrote a paper together, and pairs that did, but whose joint papers are at
# most LITTLE of the metascience papers of the one with fewer papers (1 joint paper means little to someone with 100)
LITTLE = 0.05
# and only pairs whose work is clearly alike (similarity at least 0.2, as for the communities below); without this, a
# person with few such pairs got suggestions that are less alike than the average pair
MIN_SIM = 0.2
n_papers = {x["id"]: x["k"] for x in people}
def never(a, b):
    return b not in coauthors[a]
def little(a, b):
    n = joint[tuple(sorted((a, b)))]
    return 1 <= n <= LITTLE * min(n_papers[a], n_papers[b])
def suggestions(allowed):
    sug = {}
    for i, a in enumerate(A):
        out = []
        for j in np.argsort(-S[i]):
            if S[i, j] < MIN_SIM:
                break
            b = A[j]
            if b == a or not allowed(a, b):
                continue
            shared, pair = evidence(a, b)
            out.append(dict(id=b, s=round(float(S[i, j]), 3), cl=shared, pp=pair, j=joint[tuple(sorted((a, b)))]))
            if len(out) == K:
                break
        if out:
            sug[a] = out
    return sug
def strongest(sug):
    # strongest pairs overall, each person at most twice
    ps = sorted({tuple(sorted((a, s["id"]))): s for a, ss in sug.items() for s in ss}.items(), key=lambda kv: -kv[1]["s"])
    seen, top = collections.Counter(), []
    for (a, b), s in ps:
        if seen[a] >= 2 or seen[b] >= 2:
            continue
        shared, pair = evidence(a, b)
        top.append(dict(a=a, b=b, s=s["s"], cl=shared, pp=pair, j=s["j"])); seen[a] += 1; seen[b] += 1
        if len(top) == 30:
            break
    return top
suggest, suggest_little = suggestions(never), suggestions(little)
top_pairs, top_pairs_little = strongest(suggest), strongest(suggest_little)
print(f"suggestions: never together for {len(suggest)} people, a little together (<= {LITTLE:.0%}) for "
      f"{len(suggest_little)} people")

# communities: topical similarity against actual co-authorship
comm_people = collections.defaultdict(list)
for x in people:
    if x["cm"] >= 0:
        comm_people[x["cm"]].append(x)
big = [c for c, xs in sorted(comm_people.items(), key=lambda kv: -len(kv[1])) if len(xs) >= 25][:12]
def comm_vec(c):
    vs = [paper_vec[p["id"]] for x in comm_people[c] for p in papers_of[x["id"]] if p["id"] in paper_vec]
    return unit(np.mean(vs, axis=0))
cv = {c: comm_vec(c) for c in big}
comm_of = {x["id"]: x["cm"] for x in people}
# joint papers of two communities: papers (at most MAX_AUTHORS authors) with an author from each
links = collections.Counter()
for p in papers:
    if (p["na"] or 0) > MAX_AUTHORS:
        continue
    cs = sorted({comm_of.get(a) for a in p["p"]} & set(cv))
    for ca, cb in itertools.combinations(cs, 2):
        links[(ca, cb)] += 1
def comm_topics(c):
    # the group's papers, each counted once (also when several members wrote it); groups have no names, only a
    # number (id + 1, so group 1 is the largest) and these themes
    ps = {p["id"]: p for x in comm_people[c] for p in papers_of[x["id"]]}
    cnt = collections.Counter(p["cl"] for p in ps.values() if p["cl"] is not None)
    return [cname[k] for k, _ in cnt.most_common(3)]
comm_pairs = []
for ca, cb in itertools.combinations(big, 2):
    na, nb = len(comm_people[ca]), len(comm_people[cb])
    comm_pairs.append(dict(a=ca, b=cb, sim=round(float(cv[ca] @ cv[cb]), 3), links=links[(min(ca, cb), max(ca, cb))],
                           per1000=round(1000 * links[(min(ca, cb), max(ca, cb))] / (na * nb), 2)))
# positions for the map of communities, so communities that work on similar themes lie close together. The content
# distance of two communities is 1 - similarity. Classical scaling (the first try) put groups 1 and 7 on top of each
# other although their similarity is only 0.38, because it keeps only the two largest directions of difference; the
# positions are therefore improved by SMACOF (metric multidimensional scaling), which matches all pairwise distances
# as well as it can. Circles that would still overlap are then pushed apart a little.
D = np.array([[1 - float(cv[a] @ cv[b]) if a != b else 0.0 for b in big] for a in big])
J = np.eye(len(big)) - 1 / len(big)
vals, vecs = np.linalg.eigh(-0.5 * J @ (D ** 2) @ J)
top2 = np.argsort(-vals)[:2]
xy = vecs[:, top2] * np.sqrt(np.maximum(vals[top2], 0))
for _ in range(500):   # Guttman transform
    dist = np.linalg.norm(xy[:, None] - xy[None], axis=2)
    B = -np.divide(D, dist, out=np.zeros_like(D), where=dist > 0)
    B[np.diag_indices_from(B)] = -B.sum(axis=1)
    xy = B @ xy / len(big)
min_gap = 0.12 * (D[D > 0].max())
for _ in range(200):
    moved = False
    for i, j in itertools.combinations(range(len(big)), 2):
        v = xy[j] - xy[i]; d = np.linalg.norm(v)
        if d < min_gap:
            step = (min_gap - d) / 2 * (v / d if d else np.array([1.0, 0.0]))
            xy[i] -= step; xy[j] += step; moved = True
    if not moved:
        break
dist = np.linalg.norm(xy[:, None] - xy[None], axis=2)
iu = np.triu_indices(len(big), 1)
comm_map_r = round(float(np.corrcoef(dist[iu], D[iu])[0, 1]), 2)
print("community map: correlation of map distances with content distances:", comm_map_r)
communities = [dict(id=c, n=len(comm_people[c]), topics=comm_topics(c), x=round(float(xy[i, 0]), 4),
                    y=round(float(xy[i, 1]), 4)) for i, c in enumerate(big)]

# ---------------------------------------------------------------- 2. rising themes
FIT_FROM, CHANGE_YEARS = 2005, 4
years = list(range(FIT_FROM, LAST_YEAR + 1))
tot = collections.Counter(p["y"] for p in papers if p["y"])
cl_year = collections.defaultdict(collections.Counter)
for p in papers:
    if p["y"] and p["cl"] is not None:
        cl_year[p["cl"]][p["y"]] += 1
REC, EARLY = (2024, LAST_YEAR), (2019, 2023)        # used for the rising keywords below
cids = [c["id"] for c in clusters]
counts = np.array([[cl_year[c][y] for c in cids] for y in years], float)
ref = int(np.argmax(counts.sum(axis=0)))             # reference category: the largest cluster (any choice gives the same shares)
fits = {}
for df in range(1, 8):                               # 1 = a straight line in the log odds
    kn = knots_for(df, years, counts.sum(axis=1))
    B, cov, ll, free = fit_multinomial(design(years, kn), counts, ref)
    fits[df] = dict(knots=kn, B=B, cov=cov, free=free, ll=ll, k=B.shape[0] * len(free))
PHI = max(1.0, dispersion(design(years, fits[max(fits)]["knots"]), counts, fits[max(fits)]["B"], fits[max(fits)]["k"]))
for f in fits.values():
    f["qaic"] = -2 * f["ll"] / PHI + 2 * f["k"]
DF = min(fits, key=lambda d: fits[d]["qaic"])
F = fits[DF]
F["cov"] = F["cov"] * PHI
print(f"share model: dispersion {PHI:.2f}; QAIC per spline df:", {d: round(f["qaic"], 1) for d, f in fits.items()}, "-> df", DF, flush=True)
grid = np.round(np.arange(FIT_FROM, LAST_YEAR + 1e-9, 0.25), 2)
Xg = design(grid, F["knots"])
est = 100 * shares(Xg, F["B"])
S = 100 * draws_of_shares(F["B"], F["cov"], F["free"], Xg, n_draws=4000, seed=1)
lo, hi = np.percentile(S, [2.5, 97.5], axis=0)
i_to, i_from = len(grid) - 1, int(np.where(grid == LAST_YEAR - CHANGE_YEARS)[0][0])
chg_draws = (S[:, i_to, :] - S[:, i_from, :]) / CHANGE_YEARS
chg_lo, chg_hi = np.percentile(chg_draws, [2.5, 97.5], axis=0)
chg_est = (est[i_to] - est[i_from]) / CHANGE_YEARS

# new authors per cluster
small = sorted((p for p in papers if p["y"] and (p["na"] or 0) <= MAX_AUTHORS), key=lambda p: p["y"])
first_any, first_in = {}, {}
for p in small:
    for a in p["p"]:
        first_any.setdefault(a, p["y"])
        if p["cl"] is not None and (a, p["cl"]) not in first_in:
            first_in[(a, p["cl"])] = (p["y"], p["id"])
entries = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))   # cluster -> year -> [new, moved]
by_paper = collections.defaultdict(collections.Counter)                               # cluster -> paper -> entries
for (a, cl), (y, pid_) in first_in.items():
    entries[cl][y][0 if first_any[a] == y else 1] += 1
    by_paper[cl][pid_] += 1
NEW_REC = (LAST_YEAR - 4, LAST_YEAR - 1)              # the last four complete years
NEW_EARLY = (LAST_YEAR - 8, LAST_YEAR - 5)            # the four years before
paper_year = {p["id"]: p["y"] for p in papers}
rng = np.random.default_rng(2)
def entry_ratio(cls):
    """entries in NEW_REC / entries in NEW_EARLY, with a 95% interval from resampling the entry papers in each window"""
    win = lambda lo_, hi_: np.array([n for cl in cls for q, n in by_paper[cl].items() if lo_ <= paper_year[q] <= hi_], float)
    a, b = win(*NEW_REC), win(*NEW_EARLY)
    if not len(a) or not len(b):
        return dict(rec=int(a.sum()), early=int(b.sum()), ratio=None, lo=None, hi=None)
    ra = rng.choice(a, size=(2000, len(a))).sum(axis=1)
    rb = rng.choice(b, size=(2000, len(b))).sum(axis=1)
    r = ra / np.maximum(rb, 1)
    return dict(rec=int(a.sum()), early=int(b.sum()), ratio=round(float(a.sum() / b.sum()), 3),
                lo=round(float(np.percentile(r, 2.5)), 3), hi=round(float(np.percentile(r, 97.5)), 3))
field_entries = entry_ratio(cids)

trend = []
for j, c in enumerate(clusters):
    status = "rising" if chg_lo[j] > 0 else "declining" if chg_hi[j] < 0 else "no clear change"
    trend.append(dict(id=c["id"], name=c["name"],
                      share={str(y): round(100 * cl_year[c["id"]][y] / tot[y], 2) if tot[y] else 0 for y in years},
                      n={str(y): cl_year[c["id"]][y] for y in years},
                      fit=[[round(float(lo[g, j]), 2), round(float(est[g, j]), 2), round(float(hi[g, j]), 2)] for g in range(len(grid))],
                      change=dict(est=round(float(chg_est[j]), 3), lo=round(float(chg_lo[j]), 3), hi=round(float(chg_hi[j]), 3),
                                  start=round(float(est[i_from, j]), 2), end=round(float(est[i_to, j]), 2)),
                      status=status,
                      entries={str(y): entries[c["id"]][y] for y in years if y in entries[c["id"]]},
                      entry_change=entry_ratio([c["id"]])))
    print(f"  {c['name'][:42]:42s} {est[i_from, j]:5.1f}% -> {est[i_to, j]:5.1f}%  change/yr {chg_est[j]:+.2f} "
          f"[{chg_lo[j]:+.2f}, {chg_hi[j]:+.2f}] {status:15s} entries {trend[-1]['entry_change']}", flush=True)
trend_model = dict(fit_from=FIT_FROM, df=DF, knots=[round(k, 1) for k in F["knots"]], grid=[float(g) for g in grid],
                   change_from=LAST_YEAR - CHANGE_YEARS, change_to=LAST_YEAR, n_papers=int(counts.sum()),
                   qaic={str(d): round(f["qaic"], 1) for d, f in fits.items()}, dispersion=round(PHI, 2),
                   new_recent=list(NEW_REC), new_early=list(NEW_EARLY), max_authors=MAX_AUTHORS, field_entries=field_entries)
kw_win = {w: collections.Counter() for w in ("early", "recent")}
kw_first = {}
for p in papers:
    if not p["y"]:
        continue
    for k in set(p["kw"]):
        kw_first[k] = min(kw_first.get(k, 9999), p["y"])
        if EARLY[0] <= p["y"] <= EARLY[1]:
            kw_win["early"][k] += 1
        elif REC[0] <= p["y"] <= REC[1]:
            kw_win["recent"][k] += 1
n_early = sum(tot[y] for y in range(EARLY[0], EARLY[1] + 1))
n_recent = sum(tot[y] for y in range(REC[0], REC[1] + 1))
rising = []
for k, r in kw_win["recent"].items():
    if r < 10:
        continue
    e = kw_win["early"][k]
    ratio = ((r + 1) / n_recent) / ((e + 1) / n_early)   # +1: a keyword absent before does not give an infinite ratio
    rising.append(dict(k=k, recent=r, early=e, ratio=round(ratio, 2), first=kw_first[k]))
rising.sort(key=lambda d: -d["ratio"])

# ---------------------------------------------------------------- 3. shared questions and goals
goals = None
if goals_path and os.path.exists(goals_path):
    goals = json.load(open(goals_path, encoding="utf-8"))
    # a cited paper that is now shown as another copy (a preprint and its journal version; copies.json, made by
    # build_site_data.py) is cited by the copy that is kept
    copy_of = load("copies") if os.path.exists(os.path.join(data_dir, "copies.json")) else {}
    for q in [q for c in goals.get("clusters", []) for q in c.get("questions", [])] + goals.get("goals", []):
        if "papers" in q:
            q["papers"] = list(dict.fromkeys(copy_of.get(x, x) for x in q["papers"]))
    # papers and people that are no longer on the site (for example Zenodo deposits, left out since goals.json was
    # written) are dropped from the statements; statements left with fewer than 3 papers are reported
    names = {p["n"] for p in people}
    n_gone_p = n_gone_n = 0
    for q in [q for c in goals.get("clusters", []) for q in c.get("questions", [])] + goals.get("goals", []):
        keep = [x for x in q.get("papers", []) if x in pid]
        n_gone_p += len(q.get("papers", [])) - len(keep)
        q["papers"] = keep
        if "people" in q:
            kp = [x for x in q["people"] if x in names]
            n_gone_n += len(q["people"]) - len(kp)
            q["people"] = kp
        if len(keep) < 3:
            print(f"  left out: statement now rests on {len(keep)} papers: {(q.get('question') or q.get('goal'))[:90]}")
    # a statement that rests on fewer than 3 papers on the site is left out
    for c in goals.get("clusters", []):
        c["questions"] = [q for q in c.get("questions", []) if len(q.get("papers", [])) >= 3]
    goals["goals"] = [g for g in goals.get("goals", []) if len(g.get("papers", [])) >= 3]
    print(f"goals.json: {n_gone_p} cited papers and {n_gone_n} named people are no longer on the site and were dropped")
    cited = [x for c in goals.get("clusters", []) for q in c.get("questions", []) for x in q.get("papers", [])] + \
            [x for g in goals.get("goals", []) for x in g.get("papers", [])]
    missing = [x for x in cited if x not in pid]
    assert not missing, f"goals.json cites papers that are not on the site: {missing[:10]}"

# ---------------------------------------------------------------- 4. similar ongoing projects
projects_out = None
work = os.path.dirname(os.path.abspath(emb_path))
if groups_path and os.path.exists(os.path.join(work, "project_embeddings.npy")):
    N_NEAR, N_PAIRS, PAIR_MIN_SIM = 3, 15, MIN_SIM
    pg = json.load(open(groups_path, encoding="utf-8"))
    pids = open(os.path.join(work, "project_ids.txt")).read().split()
    fund = {p["id"]: p for p in load("funding")["projects"]}
    V = np.load(os.path.join(work, "project_embeddings.npy")) - mean_vec
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    PS = V @ V.T
    # every project in exactly one place, and only projects that are in the data
    placed = [x for g in pg["groups"] for x in g["projects"]] + pg.get("on_their_own", [])
    assert sorted(placed) == sorted(pids), "project_groups.json does not hold every ongoing project exactly once: " +         str(sorted(set(pids) ^ set(placed)) or [x for x, n in collections.Counter(placed).items() if n > 1])
    assert all(len(g["projects"]) >= 2 for g in pg["groups"])
    group_of = {x: gi for gi, g in enumerate(pg["groups"]) for x in g["projects"]}
    def team(p):
        out, seen = [], set()
        for m in p["ppl"]:
            if m["n"] not in seen:
                seen.add(m["n"]); out.append(m)
        return out
    def leaders(p):
        ls = [m for m in team(p) if m["r"] in ("Project leader", "Main Applicant")]
        return [dict(n=m["n"], id=m["id"], o=m["o"]) for m in (ls or team(p))[:3]]
    # closest papers on the site
    P_ids = list(paper_vec)
    PM = np.stack([paper_vec[x] for x in P_ids])
    near = {}
    for i, x in enumerate(pids):
        sims = PM @ V[i]
        near[x] = [P_ids[j] for j in np.argsort(-sims)[:N_NEAR]]
    items = {x: dict(t=fund[x]["t"], s=fund[x]["s"], g=fund[x].get("g") or "", b=(fund[x]["b"] or "")[:7],
                     ld=leaders(fund[x]), n=len(team(fund[x])), near=near[x],
                     pp=sorted({m["id"] for m in fund[x]["ppl"] if m["id"]})) for x in pids}
    # similar pairs that the groups keep apart, from different funding schemes (projects of one funding round follow one
    # template and already meet), with no organisation and no team member in common; each project at most twice
    orgs = {x: {m["o"] for m in fund[x]["ppl"] if m["o"]} for x in pids}
    names = {x: {m["n"] for m in fund[x]["ppl"]} for x in pids}
    cand = sorted(((float(PS[i, j]), pids[i], pids[j]) for i, j in itertools.combinations(range(len(pids)), 2)
                   if PS[i, j] >= PAIR_MIN_SIM and fund[pids[i]]["s"] != fund[pids[j]]["s"]
                   and not (pids[i] in group_of and group_of[pids[i]] == group_of.get(pids[j]))
                   and not (orgs[pids[i]] & orgs[pids[j]])
                   and not (names[pids[i]] & names[pids[j]])), reverse=True)
    seen, ppairs = collections.Counter(), []
    for s_, a, b in cand:
        if seen[a] >= 2 or seen[b] >= 2:
            continue
        ppairs.append(dict(a=a, b=b, s=round(s_, 3)))
        seen[a] += 1; seen[b] += 1
        if len(ppairs) == N_PAIRS:
            break
    projects_out = dict(items=items, groups=pg["groups"], alone=pg.get("on_their_own", []), pairs=ppairs,
                        written_by=pg.get("written_by", ""), n=len(pids))
    print(f"ongoing projects: {len(pids)} | groups: {len(pg['groups'])} | on their own: {len(pg.get('on_their_own', []))}"
          f" | similar pairs without a shared organisation or person: {len(ppairs)}")

out = dict(
    last_year=LAST_YEAR, active_rule="at least 3 metascience papers, one in 2024 or later", n_active=len(A),
    suggest=suggest, top_pairs=top_pairs, suggest_little=suggest_little, top_pairs_little=top_pairs_little,
    little=LITTLE, min_sim=MIN_SIM, max_authors=MAX_AUTHORS, communities=communities, comm_pairs=comm_pairs, comm_map_r=comm_map_r,
    trend=trend, trend_model=trend_model, windows=dict(early=list(EARLY), recent=list(REC)), rising=rising[:30],
    new_keywords=[d for d in rising if d["first"] >= 2023][:15],
    goals=goals, projects=projects_out)
with open(os.path.join(data_dir, "inferences.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print(f"inferences.json: {os.path.getsize(os.path.join(data_dir, 'inferences.json')) / 1e6:.2f} MB | active people: {len(A)} | "
      f"communities: {len(big)} | goals included: {goals is not None}")
