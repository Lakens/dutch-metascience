"""Second, stricter check (prompt v4, plus rescue pass v5) of the papers that prompt v2 called metascience.

Usage: python -I classify_check.py <raw database.sqlite> test|all
Needs SRC_API_KEY. Starts the SURF GPU and always pauses it at the end.
test: judges with the chosen version the reference papers (reference_100.csv, reference_check_100.csv, reference_holdout_80.csv) that v2 called
      metascience, and compares v2 alone with v2 followed by v4 (and v5); prints every disagreement.
all:  also judges all papers for that version; resumable.
CHECK_VERSION=v4 (default): the stricter check of all v2 metascience papers.
CHECK_VERSION=v5: rescue pass over the papers v2 kept and v4 dropped (v4 proved too strict on bibliometrics,
                  research groups, research information and general statistics; see classify.py).
Final: metascience when v2 and v4 both say so (view metascience_final); v5 was tested and not used. Results: table llm_metascience.
"""
import sys, os, csv
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gpu, classify
import sqlite3, datetime, time, concurrent.futures as cf

sys.stdout.reconfigure(encoding="utf-8")
raw_path, mode = sys.argv[1], sys.argv[2]
assert mode in ("test", "all"), "second argument: test or all"
db = sqlite3.connect(raw_path)
V = os.environ.get("CHECK_VERSION", "v4")

def judge_block(block):
    failed = []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(classify.judge, t, a, None, 4, classify.PROMPTS[V]): (wid, t, a) for wid, t, a in block}
        for f in cf.as_completed(futs):
            ans, att, _ = f.result()
            if ans is None:
                failed.append(futs[f]); continue
            db.execute("INSERT OR REPLACE INTO llm_metascience VALUES (?,?,?,?,?,?,?,?)", (
                futs[f][0], V, int(ans["is_metascience"]), ans["category"], ans.get("explanation"),
                att, classify.MODEL, datetime.datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return failed

def run(ids, label):
    global tunnel
    have = {r[0] for r in db.execute("SELECT work_id FROM llm_metascience WHERE prompt_version=?", (V,))}
    items = [(w,) + tuple(db.execute("SELECT title, abstract FROM oa_works WHERE work_id=?", (w,)).fetchone())
             for w in ids if w not in have]
    print(f"{label}: {len(items)} to judge", flush=True)
    t0, done = time.time(), 0
    for start in range(0, len(items), 400):
        block = items[start:start + 400]
        failed = judge_block(block)
        if len(failed) > len(block) / 4:
            print(f"  {len(failed)} of {len(block)} without answer; last error: {classify.LAST_ERROR}", flush=True)
            if tunnel is not None and tunnel.poll() is None:
                tunnel.kill()
            tunnel = gpu.connect()
            failed = judge_block(failed)
            if len(failed) > len(block) / 4:
                raise SystemExit(f"STOPPED: {len(failed)} of {len(block)} got no answer after reconnecting; "
                                 f"last error: {classify.LAST_ERROR}. Run again to continue.")
        done += len(block)
        if done % 2000 < 400 or done == len(items):
            rate = (time.time() - t0) / done
            print(f"  {label}: {done}/{len(items)} ({rate:.2f} s per paper, about "
                  f"{rate * (len(items) - done) / 60:.0f} min to go)", flush=True)

def answer(wid, version):
    r = db.execute("SELECT is_metascience, explanation FROM llm_metascience WHERE work_id=? AND prompt_version=?",
                   (wid, version)).fetchone()
    return r

REFS = ("reference_100.csv", "reference_check_100.csv", "reference_holdout_80.csv")

def is_yes(wid, version):
    a = answer(wid, version)
    return bool(a and a[0])

def final_yes(wid, upto):
    """v2 and (v4, or the rescue pass v5 when upto is v5)"""
    if not is_yes(wid, "v2"):
        return False
    return is_yes(wid, "v4") or (upto == "v5" and is_yes(wid, "v5"))

def score():
    for name in REFS:
        ref = [r for r in csv.DictReader(open(os.path.join(HERE, name), encoding="utf-8")) if r["reference"] != "unclear"]
        steps = ["v2", "v4"] + (["v5"] if V == "v5" else [])
        for upto in steps:
            right = fy = fn = 0
            for r in ref:
                y = is_yes(r["work_id"], "v2") if upto == "v2" else final_yes(r["work_id"], upto)
                ref_yes = r["reference"] == "yes"
                right += y == ref_yes; fy += y and not ref_yes; fn += ref_yes and not y
            label = {"v2": "v2 alone", "v4": "v2 then v4", "v5": "v2 then (v4 or v5)"}[upto]
            print(f"  {name}: {label}: {right} of {len(ref)} right; wrongly yes {fy}, wrongly no {fn}", flush=True)
        for r in ref:
            y = final_yes(r["work_id"], V)
            if is_yes(r["work_id"], "v2") and y != (r["reference"] == "yes"):
                a = answer(r["work_id"], V)
                print(f"    [{name[:16]}] reference {r['reference']}, final {'yes' if y else 'no'}: {r['title'][:90]}\n"
                      f"        {V}: {a[1] if a else '-'}")

ref_ids = [r["work_id"] for n in REFS for r in csv.DictReader(open(os.path.join(HERE, n), encoding="utf-8"))]
v2_yes = [r[0] for r in db.execute("SELECT work_id FROM llm_metascience WHERE prompt_version='v2' AND is_metascience=1")]
if V == "v5":   # rescue pass: only papers that v2 kept and v4 dropped
    v2_yes = [r[0] for r in db.execute("""SELECT a.work_id FROM llm_metascience a JOIN llm_metascience b
        ON b.work_id = a.work_id AND b.prompt_version = 'v4'
        WHERE a.prompt_version = 'v2' AND a.is_metascience = 1 AND b.is_metascience = 0""")]
todo_set = set(v2_yes)

tunnel = None
try:
    gpu.start()
    tunnel = gpu.connect()
    classify.judge("Warm-up", "Warm-up request.")
    run([w for w in dict.fromkeys(ref_ids) if w in todo_set], "reference papers")
    score()
    if mode == "all":
        run(v2_yes, f"all papers for {V}")
finally:
    gpu.stop(tunnel)

# the final set used by candidates.py, embed_and_map.py and build_site_data.py: v2 and the stricter check v4 both
# say metascience; theme and explanation from v4 (from v2 in the rare case that v4 gives no theme).
# The rescue pass v5 was tested (20 Nov 2026) and NOT used: on 80 fresh hand-judged papers, v2+(v4 or v5) scored
# the same as v2+v4 (54 of 65) but traded 7 missed papers for 7 wrongly included ones; about half of the 875 papers
# it restored were not metascience. Its answers stay in llm_metascience for the record.
db.execute("DROP VIEW IF EXISTS metascience_final")
db.execute("""CREATE VIEW metascience_final AS
  SELECT b.work_id, 'v2+v4' AS prompt_version, 1 AS is_metascience,
         CASE WHEN b.category = 'not metascience' THEN a.category ELSE b.category END AS category,
         b.explanation
  FROM llm_metascience a JOIN llm_metascience b ON b.work_id = a.work_id AND b.prompt_version = 'v4'
  WHERE a.prompt_version = 'v2' AND a.is_metascience = 1 AND b.is_metascience = 1""")
db.commit()
print("final metascience papers:", db.execute("SELECT count(*) FROM metascience_final").fetchone()[0])
