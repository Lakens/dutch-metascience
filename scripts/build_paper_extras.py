"""Extra information per paper for the Papers page: similar papers, citations, open access, links to the other pages.

Usage: python -I build_paper_extras.py <site data folder> <nl_metascience.sqlite> <embeddings.npy> <embedding_ids.txt>
           <references.json>
Run after build_site_data.py, build_inferences.py and build_socials.py (it reads papers.json, copies.json,
inferences.json and socials.json from the site data folder). Writes two files to the site data folder:

paper_extras.json
 - sim: per paper the 8 most similar papers on the site (cosine similarity of the bge-m3 text fingerprints of title
   and abstract, the same fingerprints as the paper map; embed_and_map.py / extend_map.py);
 - cites: per paper the papers on this site that it cites (OpenAlex reference lists, fetch_references.py; a citation
   of a copy that is not shown counts for the version that is shown, copies.json); "cited by" is the reverse;
 - nref: the number of references in OpenAlex; refs: per paper its 5 most cited references that are not on this site
   and are in references.json (works cited by several papers on the site), with their details in works;
 - oa: the papers that are open access according to OpenAlex;
 - proj, projects: ongoing NWO projects that list the paper among their 3 most similar papers on the Inferences page;
 - stm, pstm: the statements on the Inferences page (goals and research questions) that cite the paper;
 - shares: the number of posts with a metascience term on Bluesky or Mastodon that link to the paper, and the number
   of people who wrote them (socials.json; counts only).
paper_authors.json: per paper the names of all authors in order (at most 30; for the BibTeX export only).
"""
import sys, os, json, sqlite3, collections
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
data_dir, db_path, emb_path, emb_ids_path, refs_path = sys.argv[1:6]
N_SIM, N_REFS, MAX_AUTHORS = 8, 5, 30
rd = lambda name: json.load(open(os.path.join(data_dir, name), encoding="utf-8"))
papers = rd("papers.json")
site = {p["id"] for p in papers}
copy_of = rd("copies.json")
shown = lambda w: copy_of.get(w, w)

# ---------------------------------------------------------------- similar papers
ids = open(emb_ids_path, encoding="utf-8").read().split()
E = np.load(emb_path)
row = {w: i for i, w in enumerate(ids)}
order = [p["id"] for p in papers if p["id"] in row]
X = E[[row[w] for w in order]].astype(np.float32)
X /= np.linalg.norm(X, axis=1, keepdims=True)
sim = {}
for s in range(0, len(order), 1000):
    S = X[s:s + 1000] @ X.T
    for i in range(S.shape[0]):
        S[i, s + i] = -1                       # not the paper itself
    top = np.argpartition(-S, N_SIM, axis=1)[:, :N_SIM]
    for i in range(S.shape[0]):
        best = top[i][np.argsort(-S[i, top[i]])]
        sim[order[s + i]] = [order[j] for j in best]
print(f"similar papers: {len(sim)} of {len(papers)} papers have a text fingerprint")

# ---------------------------------------------------------------- citations
R = json.load(open(refs_path, encoding="utf-8"))
refs, works = R["refs"], R["works"]
cites, ref_top, nref, used = {}, {}, {}, set()
for w in site:
    lst = refs.get(w) or []
    if not lst:
        continue
    nref[w] = len(lst)
    on_site = list(dict.fromkeys(shown(x) for x in lst if shown(x) in site and shown(x) != w))
    if on_site:
        cites[w] = on_site
    other = sorted({x for x in lst if works.get(x) and shown(x) not in site},   # (works without details are None)
                   key=lambda x: -(works[x].get("c") or 0))[:N_REFS]
    if other:
        ref_top[w] = other; used.update(other)
works_out = {x: [works[x]["t"], works[x].get("y"), (works[x].get("a") or [""])[0], works[x].get("na") or 0,
                 works[x].get("doi") or "", works[x].get("c") or 0] for x in sorted(used)}
print(f"papers with a reference list: {len(nref)} | citing another paper on the site: {len(cites)} "
      f"({sum(len(v) for v in cites.values())} citations) | other cited works listed: {len(works_out)}")

# ---------------------------------------------------------------- open access and authors (database)
db = sqlite3.connect(db_path)
oa, authors = [], collections.defaultdict(list)
site_list = sorted(site)
for s in range(0, len(site_list), 500):
    chunk = site_list[s:s + 500]
    q = ",".join("?" * len(chunk))
    oa += [w for w, o in db.execute(f"SELECT work_id, is_oa FROM oa_works WHERE work_id IN ({q})", chunk) if o]
    for w, pos, name in db.execute(f"SELECT work_id, position, author_name FROM oa_authorships WHERE work_id IN ({q}) "
                                   "ORDER BY work_id, position", chunk):
        if len(authors[w]) < MAX_AUTHORS:
            authors[w].append(name or "")
print(f"open access: {len(oa)} of {len(site)}")

# ---------------------------------------------------------------- links to the Inferences and Socials pages
inf = rd("inferences.json")
proj, projects = collections.defaultdict(list), {}
for pid, it in inf["projects"]["items"].items():
    for w in it.get("near") or []:
        if shown(w) in site:
            proj[shown(w)].append(pid)
            projects[pid] = [it["t"], it.get("s") or "", it.get("b") or ""]
stm, pstm = [], collections.defaultdict(list)
g = inf.get("goals") or {}
for x in g.get("goals", []):
    stm.append(["goal", x["goal"]])
    for w in x.get("papers", []):
        pstm[shown(w)].append(len(stm) - 1)
for c in g.get("clusters", []):
    for x in c.get("questions", []):
        stm.append(["question", x["question"]])
        for w in x.get("papers", []):
            pstm[shown(w)].append(len(stm) - 1)
pstm = {w: sorted(set(v)) for w, v in pstm.items() if w in site}
shares = {w: v for w, v in (rd("socials.json").get("paper_shares") or {}).items() if w in site}
print(f"papers near an ongoing NWO project: {len(proj)} | cited in an Inferences statement: {len(pstm)} | "
      f"shared on social media: {len(shares)}")

out = dict(sim=sim, cites=cites, nref=nref, refs=ref_top, works=works_out, oa=sorted(oa), proj=dict(proj),
           projects=projects, stm=stm, pstm=pstm, shares=shares)
for name, obj in (("paper_extras.json", out), ("paper_authors.json", dict(authors))):
    path = os.path.join(data_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{name}: {os.path.getsize(path) / 1e6:.2f} MB")
