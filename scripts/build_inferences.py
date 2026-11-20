"""Data for the Inferences page: possible collaborations, rising themes, and (from a hand-written file) shared
questions and goals.

Usage: python -I build_inferences.py <site data folder> <embeddings.npy> <embedding_ids.txt> [goals.json]
Reads the site's papers/people/edges/clusters/institutions JSON and the paper embeddings (bge-m3, from
embed_and_map.py); writes <site data folder>/inferences.json.

1. Possible collaborations: each active researcher (>= 3 metascience papers, one in 2024 or later) gets the 5 most similar
   researchers they have never written a paper with. A person's profile is the average embedding of their papers,
   after subtracting the average of all papers (otherwise every metascientist looks alike). Evidence per pair: the
   clusters both work in, and the two papers (one each) that are closest in content.
   Communities: topical similarity of the research communities (Louvain, from the site data) against how often
   they actually write together.
2. Rising themes: each cluster's share of the papers per year; growth of the share 2024-2026 against 2019-2023;
   a straight-line trend over 2016-2026, continued to 2028 (a continuation of the trend, not a forecast).
   Rising keywords: share of papers with the keyword, 2024-2026 against 2019-2023.
3. Shared questions and goals: copied from goals.json (written by Claude from the 2025-2026 abstracts), after
   checking that every cited paper is on the site.
"""
import sys, os, json, collections, itertools
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
data_dir, emb_path, ids_path = sys.argv[1:4]
goals_path = sys.argv[4] if len(sys.argv) > 4 else None
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
coauthors = collections.defaultdict(set)
for p in papers:
    for a, b in itertools.combinations(set(p["p"]), 2):
        coauthors[a].add(b); coauthors[b].add(a)
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
    pa = [p["id"] for p in papers_of[a] if p["id"] in paper_vec]
    pb = [p["id"] for p in papers_of[b] if p["id"] in paper_vec]
    sims = np.stack([paper_vec[x] for x in pa]) @ np.stack([paper_vec[x] for x in pb]).T
    i, j = np.unravel_index(np.argmax(sims), sims.shape)
    return [cname[k] for k in shared], [pa[i], pb[j]]

K = 5
suggest = {}
for i, a in enumerate(A):
    order = np.argsort(-S[i])
    out = []
    for j in order:
        b = A[j]
        if b == a or b in coauthors[a]:
            continue
        shared, pair = evidence(a, b)
        out.append(dict(id=b, s=round(float(S[i, j]), 3), cl=shared, pp=pair))
        if len(out) == K:
            break
    suggest[a] = out
# strongest pairs overall, each person at most twice
pairs = sorted({tuple(sorted((a, s["id"]))): s["s"] for a, ss in suggest.items() for s in ss}.items(), key=lambda kv: -kv[1])
seen, top_pairs = collections.Counter(), []
for (a, b), s in pairs:
    if seen[a] >= 2 or seen[b] >= 2:
        continue
    shared, pair = evidence(a, b)
    top_pairs.append(dict(a=a, b=b, s=s, cl=shared, pp=pair)); seen[a] += 1; seen[b] += 1
    if len(top_pairs) == 30:
        break

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
links = collections.Counter()
for a, b, w in edges:
    ca, cb = comm_of.get(a), comm_of.get(b)
    if ca in cv and cb in cv and ca != cb:
        links[tuple(sorted((ca, cb)))] += 1
def comm_label(c):
    top = sorted(comm_people[c], key=lambda x: -x["k"])[:2]
    return " & ".join(x["n"] for x in top)
def comm_topics(c):
    cnt = collections.Counter(p["cl"] for x in comm_people[c] for p in papers_of[x["id"]] if p["cl"] is not None)
    return [cname[k] for k, _ in cnt.most_common(3)]
comm_pairs = []
for ca, cb in itertools.combinations(big, 2):
    na, nb = len(comm_people[ca]), len(comm_people[cb])
    comm_pairs.append(dict(a=ca, b=cb, sim=round(float(cv[ca] @ cv[cb]), 3), links=links[(min(ca, cb), max(ca, cb))],
                           per1000=round(1000 * links[(min(ca, cb), max(ca, cb))] / (na * nb), 2)))
communities = [dict(id=c, label=comm_label(c), n=len(comm_people[c]), topics=comm_topics(c)) for c in big]

# ---------------------------------------------------------------- 2. rising themes
years = list(range(2010, LAST_YEAR + 1))
tot = collections.Counter(p["y"] for p in papers if p["y"])
cl_year = collections.defaultdict(collections.Counter)
for p in papers:
    if p["y"] and p["cl"] is not None:
        cl_year[p["cl"]][p["y"]] += 1
REC, EARLY = (2024, LAST_YEAR), (2019, 2023)
def window_share(cnt, lo, hi):
    n = sum(cnt[y] for y in range(lo, hi + 1)); d = sum(tot[y] for y in range(lo, hi + 1))
    return n / d if d else 0
trend = []
fit_years = np.arange(2016, LAST_YEAR + 1)
for c in clusters:
    cnt = cl_year[c["id"]]
    share = [100 * cnt[y] / tot[y] if tot[y] else 0 for y in years]
    ys = np.array([100 * cnt[y] / tot[y] for y in fit_years])
    slope, icept = np.polyfit(fit_years, ys, 1)
    proj = {str(y): round(max(0.0, slope * y + icept), 2) for y in range(LAST_YEAR, LAST_YEAR + 3)}
    early, recent = window_share(cnt, *EARLY), window_share(cnt, *REC)
    trend.append(dict(id=c["id"], name=c["name"], share={str(y): round(s, 2) for y, s in zip(years, share)},
                      n={str(y): cnt[y] for y in years}, early=round(100 * early, 2), recent=round(100 * recent, 2),
                      ratio=round(recent / early, 2) if early else None, slope=round(float(slope), 3), proj=proj))
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
    cited = [x for c in goals.get("clusters", []) for q in c.get("questions", []) for x in q.get("papers", [])] + \
            [x for g in goals.get("goals", []) for x in g.get("papers", [])]
    missing = [x for x in cited if x not in pid]
    assert not missing, f"goals.json cites papers that are not on the site: {missing[:10]}"

out = dict(
    last_year=LAST_YEAR, active_rule="at least 3 metascience papers, one in 2024 or later", n_active=len(A),
    suggest=suggest, top_pairs=top_pairs, communities=communities, comm_pairs=comm_pairs,
    trend=trend, windows=dict(early=list(EARLY), recent=list(REC)), rising=rising[:30],
    new_keywords=[d for d in rising if d["first"] >= 2023][:15],
    goals=goals)
with open(os.path.join(data_dir, "inferences.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print(f"inferences.json: {os.path.getsize(os.path.join(data_dir, 'inferences.json')) / 1e6:.2f} MB | active people: {len(A)} | "
      f"communities: {len(big)} | goals included: {goals is not None}")
