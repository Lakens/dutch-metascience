"""Text fingerprints (embeddings) of the ongoing metascience-related NWO projects, for the Inferences page.

Usage: python -I embed_projects.py <site data folder> <nwo_projects.json> <raw database.sqlite> <out folder>
Input: <site data folder>/funding.json (build_funding.py), the NWO projects (fetch_nwo.py) for the English summaries,
and the raw database plus <out folder>/embeddings.npy and embedding_ids.txt (embed_and_map.py) for a check.
Output: <out folder>/project_embeddings.npy and project_ids.txt.

Ongoing: a metascience-related project (see build_funding.py) whose end date is in the future, or that has no end
date (NWOpen gives none for recent projects) and started in ONGOING_FROM or later. Text: title + ". " + English
summary, cut at 3,000 characters, as for the papers in embed_and_map.py.

The papers were embedded with bge-m3 in Ollama on a SURF GPU; here the same model (BAAI/bge-m3 from Hugging Face,
dense vector = the normalised first token) runs on this computer, without a GPU. To check that the two give the same
fingerprints, CHECK_N papers are embedded again and compared with their stored fingerprints (the cosine similarity
should be close to 1); the script stops when it is not.
"""
import sys, os, json, datetime, sqlite3
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

sys.stdout.reconfigure(encoding="utf-8")
data_dir, nwo_path, raw_path, out_dir = sys.argv[1:5]
ONGOING_FROM, CHECK_N, MIN_CHECK = "2023-01-01", 30, 0.98
TODAY = datetime.date.today().isoformat()

def ongoing(p):
    if p["e"]:
        return p["e"] >= TODAY
    return (p["b"] or "") >= ONGOING_FROM

F = json.load(open(os.path.join(data_dir, "funding.json"), encoding="utf-8"))
nwo = {p["project_id"]: p for p in json.load(open(nwo_path, encoding="utf-8"))}
projects = sorted((p for p in F["projects"] if p["m"] and ongoing(p)), key=lambda p: p["id"])
texts = [(p["t"] + ". " + (nwo[p["id"]]["summary_en"] or nwo[p["id"]]["summary_nl"] or ""))[:3000] for p in projects]
print(f"ongoing metascience-related projects: {len(projects)} (without an English summary: "
      f"{sum(1 for p in projects if not nwo[p['id']]['summary_en'].strip())})", flush=True)

tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")
model = AutoModel.from_pretrained("BAAI/bge-m3").eval()
def embed(ts):
    out = []
    with torch.no_grad():
        for i in range(0, len(ts), 8):
            b = tok(ts[i:i + 8], padding=True, truncation=True, max_length=8192, return_tensors="pt")
            v = model(**b).last_hidden_state[:, 0]
            out.append(torch.nn.functional.normalize(v, dim=-1).numpy())
    return np.concatenate(out).astype(np.float32)

# check against the stored paper fingerprints
X = np.load(os.path.join(out_dir, "embeddings.npy"))
ids = open(os.path.join(out_dir, "embedding_ids.txt")).read().split()
db = sqlite3.connect(raw_path)
rng = np.random.default_rng(1)
pick = sorted(rng.choice(len(ids), CHECK_N, replace=False))
pt = []
for i in pick:
    t, a = db.execute("SELECT title, abstract FROM oa_works WHERE work_id = ?", (ids[i],)).fetchone()
    pt.append(((t or "") + ". " + (a or ""))[:3000])
cos = (embed(pt) * X[pick]).sum(axis=1)
print(f"check on {CHECK_N} papers: cosine with the stored fingerprints min {cos.min():.4f}, mean {cos.mean():.4f}")
if cos.min() < MIN_CHECK:
    raise SystemExit("STOPPED: this computer's fingerprints differ from the stored ones")

V = embed(texts)
np.save(os.path.join(out_dir, "project_embeddings.npy"), V)
open(os.path.join(out_dir, "project_ids.txt"), "w").write("\n".join(p["id"] for p in projects))
print("written:", V.shape)
