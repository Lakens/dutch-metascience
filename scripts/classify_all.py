"""Judge every paper (our cleaned papers + the Dutch OpenAlex search results) as metascience or not.

Usage: python -I classify_all.py <raw database.sqlite> <clean database.sqlite>
Needs SRC_API_KEY and OPENALEX_API_KEY. Starts the SURF GPU and always pauses it at the end.
1. scores prompt versions v1 and v2 on scripts/reference_100.csv (my own judgements; 'unclear' not scored);
2. uses the better version (v2 on a tie) for all papers not yet judged with it; resumable.
Results: table llm_metascience in the raw database.
"""
import sys, os, csv, time, sqlite3, datetime, concurrent.futures as cf
import requests
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gpu, classify
from oa_store import oa_get, abstract

sys.stdout.reconfigure(encoding="utf-8")
raw_path, clean_path = sys.argv[1], sys.argv[2]
db = sqlite3.connect(raw_path)
db.execute("""CREATE TABLE IF NOT EXISTS llm_metascience (
  work_id TEXT, prompt_version TEXT, is_metascience INTEGER, category TEXT, explanation TEXT,
  attempts INTEGER, model TEXT, judged_at TEXT, PRIMARY KEY (work_id, prompt_version))""")
db.execute("ATTACH DATABASE ? AS clean", (clean_path,))

def texts_for(ids):
    """title and abstract per work id, from the raw database or else from OpenAlex"""
    out = {}
    for wid in ids:
        r = db.execute("SELECT title, abstract FROM oa_works WHERE work_id=?", (wid,)).fetchone()
        if r is None:
            w = oa_get(f"works/{wid}", {"select": "id,display_name,abstract_inverted_index"})
            r = (w["display_name"], abstract(w.get("abstract_inverted_index"))) if w else ("", None)
        out[wid] = r
    return out

def judge_block(block, version):
    """judge 8 at a time and store each answer; returns the items without an answer"""
    system = classify.PROMPTS[version]
    failed = []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(classify.judge, t, a, None, 4, system): (wid, t, a) for wid, t, a in block}
        for f in cf.as_completed(futs):
            ans, att, _ = f.result()
            if ans is None:
                failed.append(futs[f])
                continue
            db.execute("INSERT OR REPLACE INTO llm_metascience VALUES (?,?,?,?,?,?,?,?)", (
                futs[f][0], version, int(ans["is_metascience"]), ans["category"], ans.get("explanation"),
                att, classify.MODEL, datetime.datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return failed

def ollama_log(n=15):
    code, out = gpu.ssh(f"journalctl -u ollama -n {n} --no-pager", timeout=40)
    return out

def run(items, version, label):
    """judge (work_id, title, abstract) items in blocks of 400; on many failures reconnect and retry once"""
    global tunnel
    t0, done = time.time(), 0
    for start in range(0, len(items), 400):
        block = items[start:start + 400]
        failed = judge_block(block, version)
        if len(failed) > len(block) / 4:
            print(f"  {len(failed)} of {len(block)} without answer; last error: {classify.LAST_ERROR}", flush=True)
            print("  tunnel alive:", tunnel is not None and tunnel.poll() is None, "| model reachable:", gpu.has_model(),
                  flush=True)
            print("  Ollama log on the workspace:\n" + ollama_log(), flush=True)
            if tunnel is not None and tunnel.poll() is None:
                tunnel.kill()
            tunnel = gpu.connect()
            failed = judge_block(failed, version)
            print(f"  after reconnecting: {len(failed)} still without answer", flush=True)
            if len(failed) > len(block) / 4:
                raise SystemExit(f"STOPPED: {len(failed)} of {len(block)} requests in a block got no answer "
                                 f"after reconnecting; last error: {classify.LAST_ERROR}. Run again to continue.")
        done += len(block)
        if done % 4000 < 400 or done == len(items):
            rate = (time.time() - t0) / done
            print(f"  {label}: {done}/{len(items)} ({rate:.2f} s per paper, about "
                  f"{rate * (len(items) - done) / 60:.0f} min to go)", flush=True)

ref = list(csv.DictReader(open(os.path.join(HERE, "reference_100.csv"), encoding="utf-8")))
ref_text = texts_for([r["work_id"] for r in ref])

all_ids = [r[0] for r in db.execute(
    "SELECT work_id FROM clean.papers UNION SELECT work_id FROM oa_search_hits")]
print("papers to judge in total:", len(all_ids), flush=True)

tunnel = None
try:
    gpu.start()
    # diagnosis of the first full run's failure (19 Nov 2026, 20:44:48 Dutch time = 19:44:48 UTC)
    code, out = gpu.ssh("date -u; journalctl -u ollama --since '2026-11-19 19:43:30' --until '2026-11-19 19:47:00' "
                        "--no-pager | tail -25", timeout=40)
    print("Ollama log around the earlier failure:\n" + out, flush=True)
    tunnel = gpu.connect()
    classify.judge("Warm-up", "Warm-up request.")

    # 1. score both prompt versions on the reference papers
    scores = {}
    for version in ("v1", "v2"):
        # judged once; a rerun reuses the stored judgements, so the choice of version cannot change mid-way
        have = {r[0] for r in db.execute("SELECT work_id FROM llm_metascience WHERE prompt_version=?", (version,))}
        missing_ref = [(r["work_id"],) + tuple(ref_text[r["work_id"]]) for r in ref if r["work_id"] not in have]
        if missing_ref:
            run(missing_ref, version, f"reference {version}")
        right = false_yes = false_no = missing = 0
        for r in ref:
            if r["reference"] == "unclear":
                continue
            got = db.execute("SELECT is_metascience FROM llm_metascience WHERE work_id=? AND prompt_version=?",
                             (r["work_id"], version)).fetchone()
            if got is None:
                missing += 1; continue
            model_yes, ref_yes = bool(got[0]), r["reference"] == "yes"
            right += model_yes == ref_yes
            false_yes += model_yes and not ref_yes
            false_no += ref_yes and not model_yes
        scores[version] = right
        print(f"{version}: {right} of 95 right; wrongly yes {false_yes}, wrongly no {false_no}, no answer {missing}",
              flush=True)
    chosen = "v1" if scores["v1"] > scores["v2"] else "v2"
    print("using prompt", chosen, flush=True)

    # 2. all papers not yet judged with the chosen version
    judged = {r[0] for r in db.execute("SELECT work_id FROM llm_metascience WHERE prompt_version=?", (chosen,))}
    todo_ids = [w for w in all_ids if w not in judged]
    items = []
    for wid in todo_ids:
        t, a = db.execute("SELECT title, abstract FROM oa_works WHERE work_id=?", (wid,)).fetchone()
        items.append((wid, t, a))
    print("still to judge:", len(items), flush=True)
    run(items, chosen, "all papers")
finally:
    gpu.stop(tunnel)

n = db.execute("SELECT count(*), sum(is_metascience) FROM llm_metascience WHERE prompt_version=?", (chosen,)).fetchone()
print(f"done: {n[0]} papers judged with {chosen}, {n[1]} metascience")
