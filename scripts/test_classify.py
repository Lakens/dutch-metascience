"""Test the metascience judgements on 100 papers and measure speed; always pauses the GPU at the end.

Usage: python -I test_classify.py <clean database.sqlite> <output.xlsx>
Needs SRC_API_KEY and OPENALEX_API_KEY in the environment.
"""
import sys, os, time, random, sqlite3, concurrent.futures as cf
import requests, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu, classify, terms

sys.stdout.reconfigure(encoding="utf-8")
clean_db, out_xlsx = sys.argv[1], sys.argv[2]
OA_KEY = os.environ["OPENALEX_API_KEY"].strip().strip('"')

def abstract(inv):
    if not inv:
        return None
    pos = {i: w for w, idx in inv.items() for i in idx}
    return " ".join(pos[i] for i in sorted(pos))

# ---- the 100 papers (prepared before the GPU starts) ----
db = sqlite3.connect(clean_db)
random.seed(20261119)
ids = [r[0] for r in db.execute("SELECT work_id FROM papers ORDER BY work_id")]
seed_rows = [("our papers",) + tuple(db.execute("SELECT work_id, title, abstract, year, field FROM papers WHERE work_id=?",
                                                 (w,)).fetchone()) for w in random.sample(ids, 50)]
r = requests.get("https://api.openalex.org/works", params={
    "filter": terms.search_filter(), "sample": 50, "seed": 42, "per-page": 50,
    "select": "id,display_name,abstract_inverted_index,publication_year,primary_topic", "api_key": OA_KEY},
    headers={"User-Agent": "dutch-metascience-script"}, timeout=90)
r.raise_for_status()
print("OpenAlex search hits in total:", r.json()["meta"]["count"], flush=True)
search_rows = [("OpenAlex search", w["id"].rsplit("/", 1)[-1], w["display_name"], abstract(w.get("abstract_inverted_index")),
                w.get("publication_year"), ((w.get("primary_topic") or {}).get("field") or {}).get("display_name"))
               for w in r.json()["results"]]
rows = seed_rows + search_rows
print("papers to judge:", len(rows), flush=True)

results = {}
tunnel = None
try:
    gpu.start()
    code, conf = gpu.ssh("cat /etc/systemd/system/ollama.service.d/override.conf")
    print("Ollama settings on the workspace:", conf.replace("\n", " | "), flush=True)
    if "OLLAMA_NUM_PARALLEL" not in conf:
        print("Adding OLLAMA_NUM_PARALLEL=8 and restarting Ollama", flush=True)
        gpu.ssh("printf 'Environment=OLLAMA_NUM_PARALLEL=8\\n' | sudo tee -a "
                "/etc/systemd/system/ollama.service.d/override.conf >/dev/null && "
                "sudo systemctl daemon-reload && sudo systemctl restart ollama && sleep 3", timeout=90)
    tunnel = gpu.connect()
    # load the model (about 50 s the first time)
    t0 = time.time(); classify.judge("Warm-up", "Warm-up request."); print(f"model loaded in {time.time()-t0:.0f} s", flush=True)

    sess = requests.Session()
    t0 = time.time()
    for row in rows[:10]:
        results[row[1]] = classify.judge(row[2], row[3], sess)
    seq = (time.time() - t0) / 10
    print(f"one at a time: {seq:.2f} s per paper", flush=True)

    t0 = time.time()
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(classify.judge, row[2], row[3]): row[1] for row in rows[10:]}
        for f in cf.as_completed(futs):
            results[futs[f]] = f.result()
    par = (time.time() - t0) / (len(rows) - 10)
    print(f"8 at a time: {par:.2f} s per paper (throughput)", flush=True)
finally:
    gpu.stop(tunnel)

# ---- spreadsheet ----
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Judgements"
hdr = ["Source", "OpenAlex work", "Year", "Field (OpenAlex)", "Title", "Metascience?", "Category", "Explanation",
       "Attempts", "Abstract available"]
ws.append(hdr)
for src, wid, title, abst, year, field in rows:
    ans, att, secs = results.get(wid, (None, None, None))
    ws.append([src, wid, year, field, title, None if ans is None else ("yes" if ans["is_metascience"] else "no"),
               (ans or {}).get("category"), (ans or {}).get("explanation"), att, "yes" if abst else "no"])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
for letter, w in zip("ABCDEFGHIJ", [16, 13, 6, 22, 70, 11, 30, 60, 8, 9]):
    ws.column_dimensions[letter].width = w
ws.freeze_panes = "B2"; ws.auto_filter.ref = ws.dimensions
wb.save(out_xlsx)
n_yes = sum(1 for v in results.values() if v[0] and v[0]["is_metascience"])
n_fail = sum(1 for v in results.values() if v[0] is None)
print(f"judged {len(results)}; metascience: {n_yes}; no answer: {n_fail}; retries needed: "
      f"{sum(1 for v in results.values() if v[1] and v[1] > 1)}")
