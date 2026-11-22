"""First grouping of the ongoing metascience-related NWO projects, to be read and corrected by a Claude reviewer.

Usage: python -I draft_project_groups.py <site data folder> <nwo_projects.json> <data_work folder> <out.jsonl>
       [distance threshold]
Input: funding.json, papers.json, the NWO projects (for the full English summaries), the project fingerprints (embed_projects.py) and the paper fingerprints
(embed_and_map.py). Output: one JSON line per draft group (and one per project without a close match), with each
project's id, title, funding scheme, start date, team and summary: the input of the reviewer, who follows
project_groups_instructions.md and writes scripts/project_groups.json.

Similarity: as for people on the Inferences page, the fingerprints minus the average fingerprint of the site's papers
(otherwise every metascience text looks alike), then the cosine. Groups: average-linkage clustering with a
distance threshold (1 - similarity); projects without a project closer than the threshold stay on their own.
"""
import sys, os, json
import numpy as np
from sklearn.cluster import AgglomerativeClustering

sys.stdout.reconfigure(encoding="utf-8")
data_dir, nwo_path, work, out_path = sys.argv[1:5]
THRESHOLD = float(sys.argv[5]) if len(sys.argv) > 5 else 0.6
nwo = {p["project_id"]: p for p in json.load(open(nwo_path, encoding="utf-8"))}

F = json.load(open(os.path.join(data_dir, "funding.json"), encoding="utf-8"))
byid = {p["id"]: p for p in F["projects"]}
papers = json.load(open(os.path.join(data_dir, "papers.json"), encoding="utf-8"))
X = np.load(os.path.join(work, "embeddings.npy"))
row = {w: i for i, w in enumerate(open(os.path.join(work, "embedding_ids.txt")).read().split())}
mean_vec = X[[row[p["id"]] for p in papers if p["id"] in row]].mean(axis=0)
pids = open(os.path.join(work, "project_ids.txt")).read().split()
V = np.load(os.path.join(work, "project_embeddings.npy")) - mean_vec
V /= np.linalg.norm(V, axis=1, keepdims=True)
S = V @ V.T

lab = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average",
                              distance_threshold=THRESHOLD).fit_predict(1 - S)
groups = {}
for i, l in enumerate(lab):
    groups.setdefault(l, []).append(i)
order = sorted(groups.values(), key=lambda g: (-len(g), g[0]))
sizes = [len(g) for g in order]
print(f"projects: {len(pids)} | threshold {THRESHOLD} | groups of 2 or more: {sum(s > 1 for s in sizes)} "
      f"(sizes {[s for s in sizes if s > 1]}) | on their own: {sum(s == 1 for s in sizes)}")

def team(p):
    seen, out = set(), []
    for m in p["ppl"]:
        if m["n"] not in seen:
            seen.add(m["n"]); out.append(f'{m["n"]} ({m["r"]}, {m["o"]})')
    return out
with open(out_path, "w", encoding="utf-8") as f:
    for gi, g in enumerate(order, 1):
        inner = [S[a, b] for a in g for b in g if a < b]
        f.write(json.dumps({"draft_group": gi if len(g) > 1 else None, "n": len(g),
                            "mean_similarity": round(float(np.mean(inner)), 2) if inner else None,
                            "projects": [{"id": pids[i], "title": byid[pids[i]]["t"], "scheme": byid[pids[i]]["s"],
                                          "start": byid[pids[i]]["b"], "team": team(byid[pids[i]]),
                                          "summary": nwo[pids[i]]["summary_en"] or nwo[pids[i]]["summary_nl"]} for i in g]},
                           ensure_ascii=False) + "\n")
