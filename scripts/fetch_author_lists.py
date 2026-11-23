"""Download metascience papers from the publication lists of authors who are not on the starting list.

Usage: python -I fetch_author_lists.py <raw database.sqlite> <clean database.sqlite> <site data folder>
Needs OPENALEX_API_KEY.

The keyword search (terms.py) finds only papers whose title or abstract has a search term. For the people on the
starting list the full publication lists were collected; for everyone else only the papers the search found are on
the site. This script adds papers from the publication lists of the other people who have at least MIN_PAPERS
metascience papers on the site.

Which works: works by these authors with a Dutch institution among the authors (the same rule as the search), of the
paper types in terms.KEEP_TYPES, that carry at least one of a list of OpenAlex keywords. The keywords are chosen
from the data:
 - the keyword is on at least 10 papers on the site;
 - in the full publication lists of the starting list (which come from metascience authors and were not filtered by
   a search, like the lists collected here) at least 10 papers carry the keyword, and at least 60% of those were
   judged metascience (classifier v2 and v4, minus the papers removed by the hand check).
Without such a filter the lists of these authors hold about 100,000 works, mostly substantive (often clinical)
papers of prolific authors.

The keywords and authors are chosen on the first run and kept in author_lists_input.json (next to this script).
A later run keeps the keywords and adds the authors who reach MIN_PAPERS on the site in the meantime; authors already
done (table oa_author_list_done) are not asked for again. Works already in the database are not stored again
(storing replaces a paper's authors); every work found is recorded in table oa_author_list_hits, which
classify_all.py judges together with the other papers.
"""
import sys, os, json, csv, sqlite3, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terms
from oa_store import oa_get, store, FIELDS

sys.stdout.reconfigure(encoding="utf-8")
db_path, clean_path, data_dir = sys.argv[1:4]
MIN_PAPERS, MIN_SITE, MIN_TESTED, MIN_SHARE = 2, 10, 10, 0.60
db = sqlite3.connect(db_path)
db.execute("ATTACH DATABASE ? AS clean", (clean_path,))
choice_path = os.path.join(HERE, "author_lists_input.json")
people = json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))
authors_now = sorted(p["id"][2:] for p in people if not p["l"] and p["k"] >= MIN_PAPERS and p["id"].startswith("A:"))

if os.path.exists(choice_path):
    choice = json.load(open(choice_path, encoding="utf-8"))
    added = [a for a in authors_now if a not in set(choice["authors"])]
    choice["authors"] += added
    print(f"authors added since the first run: {len(added)}", flush=True)
else:
    site = {p["id"] for p in json.load(open(os.path.join(data_dir, "papers.json"), encoding="utf-8"))}
    excluded = {r["work_id"] for r in csv.DictReader(open(os.path.join(HERE, "excluded_by_hand.csv"), encoding="utf-8"))}
    meta = {r[0] for r in db.execute("SELECT work_id FROM metascience_final")} - excluded
    judged = {r[0] for r in db.execute("SELECT work_id FROM llm_metascience WHERE prompt_version = 'v2'")}
    full = {r[0] for r in db.execute("SELECT work_id FROM clean.papers")} & judged
    n_site, n_full, n_meta, kw_id = collections.Counter(), collections.Counter(), collections.Counter(), {}
    for wid, raw in db.execute("SELECT work_id, raw_json FROM oa_works"):
        if wid not in site and wid not in full:
            continue
        ks = {}
        for k in json.loads(raw).get("keywords") or []:
            ks[k["display_name"].lower()] = k["id"].split("/")[-1]
        kw_id.update(ks)
        if wid in site:
            n_site.update(ks.keys())
        if wid in full:
            n_full.update(ks.keys())
            if wid in meta:
                n_meta.update(ks.keys())
    keywords = sorted(((k, n_site[k], n_full[k], round(n_meta[k] / n_full[k], 3)) for k in n_site
                       if n_site[k] >= MIN_SITE and n_full[k] >= MIN_TESTED and n_meta[k] / n_full[k] >= MIN_SHARE),
                      key=lambda r: -r[1])
    choice = dict(about=f"Chosen on the first run of fetch_author_lists.py (see its description). keywords: OpenAlex "
                        f"keyword, its id, papers on the site, papers in the starting list's publication lists, and "
                        f"the share of those judged metascience. authors: OpenAlex ids of people not on the starting "
                        f"list with at least {MIN_PAPERS} metascience papers on the site (later runs add newcomers).",
                  keywords=[dict(name=k, id=kw_id[k], site_papers=s, tested=t, share_metascience=p)
                            for k, s, t, p in keywords],
                  authors=authors_now)
json.dump(choice, open(choice_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"authors: {len(choice['authors'])} | keywords: {len(choice['keywords'])}", flush=True)

db.execute("CREATE TABLE IF NOT EXISTS oa_author_list_hits (work_id TEXT PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS oa_author_list_done (author_id TEXT PRIMARY KEY)")
done = {r[0] for r in db.execute("SELECT author_id FROM oa_author_list_done")}
todo = [a for a in choice["authors"] if a not in done]
known = {r[0] for r in db.execute("SELECT work_id FROM oa_works")}
kw_ids = [k["id"] for k in choice["keywords"]]
print(f"authors still to ask for: {len(todo)}", flush=True)
n_found = n_new = 0
for i in range(0, len(todo), 25):                   # 25 authors and 100 keywords per request keep the address short
    group = "|".join(todo[i:i + 25])
    for j in range(0, len(kw_ids), 100):
        cursor = "*"
        while cursor:
            d = oa_get("works", {"filter": f"author.id:{group},authorships.institutions.country_code:NL,"
                                           f"type:{'|'.join(terms.KEEP_TYPES)},keywords.id:{'|'.join(kw_ids[j:j + 100])}",
                                 "per-page": 200, "cursor": cursor, "select": FIELDS})
            for w in d.get("results", []):
                wid = w["id"].split("/")[-1]
                if wid not in known:
                    store(db, w); known.add(wid); n_new += 1
                db.execute("INSERT OR IGNORE INTO oa_author_list_hits VALUES (?)", (wid,))
                n_found += 1
            db.commit()
            cursor = d["meta"].get("next_cursor") if d.get("results") else None
    db.executemany("INSERT OR IGNORE INTO oa_author_list_done VALUES (?)", [(a,) for a in todo[i:i + 25]])
    db.commit()
    if (i // 25) % 8 == 0 or i + 25 >= len(todo):
        print(f"  authors {min(i + 25, len(todo))}/{len(todo)}: works found {n_found}, newly stored {n_new}", flush=True)
print("distinct works in oa_author_list_hits:", db.execute("SELECT count(*) FROM oa_author_list_hits").fetchone()[0],
      "| newly stored in this run:", n_new)
