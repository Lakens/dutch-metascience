"""Add new metascience papers to the existing paper map, keeping its 20 themes and their names.

Usage: python -I extend_map.py <raw database.sqlite>
Needs SRC_API_KEY. Starts the SURF GPU and always pauses it at the end.

embed_and_map.py builds the map from scratch: new positions, new clusters and new cluster names (which were then
revised by hand in cluster_names.json). When papers are added later, this script is used instead:
1. embeddings (bge-m3, the same text as embed_and_map.py: title + ". " + abstract, at most 3000 characters) for the
   metascience papers that are not yet on the map; the existing embeddings are reused;
2. each new paper joins the existing theme whose centre (the mean embedding of its papers) is nearest; the themes,
   their names and descriptions stay as they are, only their number of papers is updated;
3. the 2-D map is computed again with UMAP (same settings as embed_and_map.py) for all papers, starting from the
   current positions (new papers start at the mean position of their 10 most similar papers already on the map), so
   the map keeps its layout. Papers that are no longer metascience are left out of the map.
Writes table paper_map, updates n_papers in cluster_names, and rewrites data_work/embeddings.npy and
embedding_ids.txt for all papers on the map.
"""
import sys, os, sqlite3
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, requests
import gpu

sys.stdout.reconfigure(encoding="utf-8")
raw_path = sys.argv[1]
EMBED_MODEL = "bge-m3"
OUT = os.path.join(os.path.dirname(HERE), "data_work")
db = sqlite3.connect(raw_path)

rows = db.execute("""SELECT w.work_id, w.title, w.abstract FROM metascience_final m JOIN oa_works w USING (work_id)
                     WHERE m.prompt_version = 'v2+v4' AND m.is_metascience = 1 ORDER BY w.work_id""").fetchall()
text = {r[0]: ((r[1] or "") + ". " + (r[2] or ""))[:3000] for r in rows}
old_ids = open(os.path.join(OUT, "embedding_ids.txt")).read().split("\n")
old_X = np.load(os.path.join(OUT, "embeddings.npy"))
assert len(old_ids) == len(old_X)
old_vec = dict(zip(old_ids, old_X))
pos = {w: (x, y, c) for w, x, y, c in db.execute("SELECT work_id, x, y, cluster FROM paper_map")}
assert set(pos) == set(old_ids), "paper_map and embedding_ids.txt do not hold the same papers"
new_ids = [w for w in text if w not in old_vec]
gone = [w for w in old_ids if w not in text]
print(f"metascience papers: {len(text)} | on the map: {len(old_ids)} | new: {len(new_ids)} | "
      f"no longer metascience: {len(gone)}", flush=True)

tunnel = None
new_vec = {}
if new_ids:
    try:
        gpu.start()
        code, out = gpu.ssh(f"ollama list | grep -q '^{EMBED_MODEL}' || ollama pull {EMBED_MODEL} >/dev/null 2>&1; "
                            f"ollama list | grep '^{EMBED_MODEL}'", timeout=900)
        print("embedding model on the workspace:", out, flush=True)
        tunnel = gpu.connect()
        s = requests.Session()
        for i in range(0, len(new_ids), 64):
            batch = new_ids[i:i + 64]
            r = s.post(gpu.OLLAMA + "/api/embed", json={"model": EMBED_MODEL, "input": [text[w] for w in batch],
                                                        "truncate": True}, timeout=300)
            r.raise_for_status()
            for w, v in zip(batch, r.json()["embeddings"]):
                v = np.array(v, dtype=np.float32)
                new_vec[w] = v / np.linalg.norm(v)
            if (i // 64) % 25 == 0:
                print(f"  embedded {min(i + 64, len(new_ids))}/{len(new_ids)}", flush=True)
    finally:
        gpu.stop(tunnel)

keep = [w for w in old_ids if w in text]
ids = keep + new_ids
X = np.array([old_vec[w] for w in keep] + [new_vec[w] for w in new_ids], dtype=np.float32)

# 2. themes: nearest centre of the existing themes (computed from the papers already on the map)
K = 1 + max(c for _, _, c in pos.values())
lab_old = np.array([pos[w][2] for w in old_ids])
centres = np.array([old_X[lab_old == c].mean(axis=0) for c in range(K)])
lab_new = (((X[len(keep):, None, :] - centres[None, :, :]) ** 2).sum(-1)).argmin(1) if new_ids else np.array([], int)
labels = np.concatenate([np.array([pos[w][2] for w in keep]), lab_new]).astype(int)

# 3. map: UMAP for all papers, starting from the current positions
init_old = np.array([[pos[w][0], pos[w][1]] for w in keep], dtype=np.float64)
if new_ids:
    sim = X[len(keep):] @ X[:len(keep)].T
    near = np.argsort(-sim, axis=1)[:, :10]
    init_new = init_old[near].mean(axis=1)
    init = np.vstack([init_old, init_new])
else:
    init = init_old
import umap
xy = umap.UMAP(n_neighbors=20, min_dist=0.08, metric="cosine", random_state=42, init=init).fit_transform(X)
# UMAP rescales its starting positions, so the result can come out turned, mirrored and scaled. Turn, scale and move
# the whole new map (one rotation or reflection, one scale, one shift: Procrustes) so that the papers that were already
# on the map lie as close as possible to where they were.
def align(new_pts, old_pts, all_pts):
    mn, mo = new_pts.mean(0), old_pts.mean(0)
    a, b = new_pts - mn, old_pts - mo
    u, s, vt = np.linalg.svd(a.T @ b)
    rot = u @ vt
    scale = s.sum() / (a ** 2).sum()
    return (all_pts - mn) @ rot * scale + mo
xy = align(xy[:len(keep)], init_old, xy)
shift = np.linalg.norm(xy[:len(keep)] - init_old, axis=1)
span = np.ptp(init_old, axis=0).max()
print(f"movement of papers already on the map, as a share of the map's width: median {np.median(shift) / span:.3f}, "
      f"90th percentile {np.percentile(shift, 90) / span:.3f}", flush=True)

db.execute("DROP TABLE IF EXISTS paper_map")
db.execute("CREATE TABLE paper_map (work_id TEXT PRIMARY KEY, x REAL, y REAL, cluster INTEGER)")
db.executemany("INSERT INTO paper_map VALUES (?,?,?,?)",
               [(w, float(a), float(b), int(c)) for w, (a, b), c in zip(ids, xy, labels)])
for c in range(K):
    db.execute("UPDATE cluster_names SET n_papers = ? WHERE cluster = ?", (int((labels == c).sum()), c))
db.commit()
np.save(os.path.join(OUT, "embeddings.npy"), X)
open(os.path.join(OUT, "embedding_ids.txt"), "w").write("\n".join(ids))
print("new papers per theme:", {c: int((lab_new == c).sum()) for c in range(K)})
print("done")
