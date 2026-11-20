"""Map the metascience papers: embeddings on the GPU, a 2-D map with UMAP, theme clusters named by the model.

Usage: python -I embed_and_map.py <raw database.sqlite> [n_clusters]
Needs SRC_API_KEY. Starts the SURF GPU and always pauses it at the end.
Writes tables paper_map (work_id, x, y, cluster) and cluster_names (cluster, name, n_papers) to the raw database,
and the embeddings to data_work/embeddings.npy (+ embedding_ids.txt).
"""
import sys, os, json, sqlite3, random
import numpy as np, requests
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gpu, classify

sys.stdout.reconfigure(encoding="utf-8")
raw_path = sys.argv[1]
K = int(sys.argv[2]) if len(sys.argv) > 2 else 20
EMBED_MODEL = "bge-m3"
OUT = os.path.join(os.path.dirname(HERE), "data_work")
os.makedirs(OUT, exist_ok=True)

db = sqlite3.connect(raw_path)
rows = db.execute("""SELECT w.work_id, w.title, w.abstract FROM metascience_final m JOIN oa_works w USING (work_id)
                     WHERE m.prompt_version = 'v2+v4' AND m.is_metascience = 1 ORDER BY w.work_id""").fetchall()
ids = [r[0] for r in rows]
texts = [((r[1] or "") + ". " + (r[2] or ""))[:3000] for r in rows]
titles = {r[0]: r[1] or "" for r in rows}
print("metascience papers to map:", len(ids), flush=True)

tunnel = None
try:
    gpu.start()
    code, out = gpu.ssh(f"ollama list | grep -q '^{EMBED_MODEL}' || ollama pull {EMBED_MODEL} >/dev/null 2>&1; "
                        f"ollama list | grep '^{EMBED_MODEL}'", timeout=900)
    print("embedding model on the workspace:", out, flush=True)
    tunnel = gpu.connect()

    # 1. embeddings, 64 texts per request
    vecs = []
    s = requests.Session()
    for i in range(0, len(texts), 64):
        r = s.post(gpu.OLLAMA + "/api/embed", json={"model": EMBED_MODEL, "input": texts[i:i + 64], "truncate": True},
                   timeout=300)
        r.raise_for_status()
        vecs += r.json()["embeddings"]
        if (i // 64) % 25 == 0:
            print(f"  embedded {min(i + 64, len(texts))}/{len(texts)}", flush=True)
    X = np.array(vecs, dtype=np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    np.save(os.path.join(OUT, "embeddings.npy"), X)
    open(os.path.join(OUT, "embedding_ids.txt"), "w").write("\n".join(ids))

    # 2. 2-D map and clusters (on this computer, while the GPU waits a minute or two)
    import umap
    from sklearn.cluster import KMeans
    xy = umap.UMAP(n_neighbors=20, min_dist=0.08, metric="cosine", random_state=42).fit_transform(X)
    km = KMeans(n_clusters=K, n_init=10, random_state=42).fit(X)
    lab = km.labels_
    db.execute("DROP TABLE IF EXISTS paper_map")
    db.execute("CREATE TABLE paper_map (work_id TEXT PRIMARY KEY, x REAL, y REAL, cluster INTEGER)")
    db.executemany("INSERT INTO paper_map VALUES (?,?,?,?)",
                   [(w, float(a), float(b), int(c)) for w, (a, b), c in zip(ids, xy, lab)])
    db.commit()

    # 3. name each cluster from the 20 titles nearest its centre
    names = {}
    schema = {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
              "required": ["name", "description"]}
    for c in range(K):
        members = np.where(lab == c)[0]
        d = X[members] @ km.cluster_centers_[c]
        near = [titles[ids[j]] for j in members[np.argsort(-d)[:20]]]
        prompt = ("These are titles of metascience papers (research on research) that belong to one group:\n- "
                  + "\n- ".join(near) + "\n\nGive the group a short name of 2 to 5 words that says what these papers "
                  "have in common, and a description of at most 20 words. Answer in English, in JSON.")
        name = None
        for attempt in range(3):
            r = s.post(gpu.OLLAMA + "/api/chat", json={
                "model": gpu.MODEL, "stream": False, "think": "low", "format": schema,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": 0 if attempt == 0 else 1, "seed": random.randint(1, 10**6)}}, timeout=180)
            try:
                ans = json.loads(r.json()["message"]["content"])
                name = (ans["name"], ans["description"]); break
            except (ValueError, KeyError):
                continue
        names[c] = name or (f"Cluster {c + 1}", "")
        print(f"  cluster {c}: {len(members)} papers -> {names[c][0]}", flush=True)
    db.execute("DROP TABLE IF EXISTS cluster_names")
    db.execute("CREATE TABLE cluster_names (cluster INTEGER PRIMARY KEY, name TEXT, description TEXT, n_papers INTEGER)")
    db.executemany("INSERT INTO cluster_names VALUES (?,?,?,?)",
                   [(c, names[c][0], names[c][1], int((lab == c).sum())) for c in range(K)])
    db.commit()
finally:
    gpu.stop(tunnel)
print("done")
