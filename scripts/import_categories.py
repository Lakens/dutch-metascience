"""Put the category of every paper (12 categories of scripts/category_rules.md) into table paper_category.

Usage: python -I import_categories.py <raw database.sqlite> <category review folder>
Run before build_site_data.py, which takes the categories from this table and stops if a paper on the site has none.

The review folder (data_work/category_review) holds the answers of the Claude reviewers (25-26 Nov 2026):
- reference_final.tsv: 250 papers judged by two reviewers, disagreements settled by hand;
- out_*.tsv: one reviewer per paper (columns work_id, category, sure, note);
- out2_*.tsv: a second reviewer for a 10% sample. Where the two differ, the second answer is used only when the
  first reviewer was not sure and the second was; otherwise the first answer stays. The agreement is printed;
- none_verdicts.tsv (optional): papers that a reviewer put in no category (NONE) were checked again with
  scripts/hand_check_rules.md (columns work_id, metascience yes/no, category, note). "no" papers are added to
  scripts/excluded_by_hand.csv; "yes" papers get the category given there.
Later papers: judge them with category_rules.md, add their answers as another out_*.tsv, and run this script again.
"""
import sys, os, csv, glob, sqlite3, collections

sys.stdout.reconfigure(encoding="utf-8")
raw_path, folder = sys.argv[1:3]
HERE = os.path.dirname(os.path.abspath(__file__))
CATS = {"replication", "bias", "statistics", "reporting", "methods", "open", "publishing", "integrity",
        "scientometrics", "system", "society", "tools"}
read = lambda path: list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))

final = {}          # work_id -> (category, source, sure, note)
for r in read(os.path.join(folder, "reference_final.tsv")):
    final[r["work_id"]] = (r["category"], "reference set: " + r["source"], "yes", "")
for path in sorted(glob.glob(os.path.join(folder, "out_*.tsv"))):
    for r in read(path):
        if r["work_id"] not in final:
            final[r["work_id"]] = (r["category"], "reviewer " + os.path.basename(path)[4:-4], r["sure"], r["note"])

# second reviewers on a 10% sample
pairs, switched = [], 0
for path in sorted(glob.glob(os.path.join(folder, "out2_*.tsv"))):
    for r in read(path):
        first = final.get(r["work_id"])
        if not first:
            continue
        pairs.append((first[0], r["category"], first[2], r["sure"], first[1]))
        if first[0] != r["category"] and first[2] == "no" and r["sure"] == "yes":
            final[r["work_id"]] = (r["category"], "second reviewer (first was not sure)", "yes", r["note"])
            switched += 1
if pairs:
    agree = sum(a == b for a, b, *_ in pairs)
    print(f"second reviewer: {len(pairs)} papers, same category {agree} ({100 * agree / len(pairs):.0f}%); "
          f"answer switched to the second reviewer: {switched}")
    by_src = collections.defaultdict(lambda: [0, 0])
    for a, b, s1, s2, src in pairs:
        by_src[src.split()[-1][:2]][0] += a == b; by_src[src.split()[-1][:2]][1] += 1
    print("  agreement by first-reviewer batch:", {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_src.items())})
    print("  most frequent differences:", collections.Counter(tuple(sorted((a, b))) for a, b, *_ in pairs if a != b).most_common(8))

# papers in no category: the second hand check
verdict_path = os.path.join(folder, "none_verdicts.tsv")
verdicts = {r["work_id"]: r for r in read(verdict_path)} if os.path.exists(verdict_path) else {}
excl_path = os.path.join(HERE, "excluded_by_hand.csv")
excluded = {r["work_id"] for r in csv.DictReader(open(excl_path, encoding="utf-8"))}
db = sqlite3.connect(raw_path)
title = lambda w: (db.execute("SELECT title FROM oa_works WHERE work_id=?", (w,)).fetchone() or [""])[0] or ""
new_excl = []
for w, (cat, src, sure, note) in list(final.items()):
    if cat != "NONE":
        continue
    v = verdicts.get(w)
    if not v:
        continue
    if v["metascience"].strip().lower() == "no":
        if w not in excluded:
            new_excl.append((w, title(w), "not metascience (category check): " + v["note"], "category check, 26 Nov 2026"))
    elif v["category"] in CATS:
        final[w] = (v["category"], "hand check of a paper without category", "yes", v["note"])
if new_excl:
    with open(excl_path, "a", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\r\n").writerows(new_excl)
print(f"papers added to excluded_by_hand.csv: {len(new_excl)}")

bad = {c for c, *_ in final.values()} - CATS - {"NONE"}
if bad:
    raise SystemExit(f"STOPPED: unknown categories {bad}")
db.execute("""CREATE TABLE IF NOT EXISTS paper_category (work_id TEXT PRIMARY KEY, category TEXT, source TEXT,
              sure TEXT, note TEXT)""")
db.executemany("INSERT OR REPLACE INTO paper_category VALUES (?, ?, ?, ?, ?)",
               [(w, c, s, u, n) for w, (c, s, u, n) in final.items()])
db.commit()
print(f"papers with a category: {sum(c != 'NONE' for c, *_ in final.values())} | still without (NONE): "
      f"{sum(c == 'NONE' for c, *_ in final.values())}")
print("per category:", dict(collections.Counter(c for c, *_ in final.values()).most_common()))
