"""Select the people for the Dutch metascience feeds: confirmed accounts of people who actually post about metascience.

Usage: python -I select_feed_accounts.py <site data folder> <social_final.json> <posts folder> <hits.jsonl> <out.tsv>
Input: the accounts (confirm_social_accounts.py), the downloaded posts (download_social_posts.py) and the posts with
a metascience term (search_social_posts.py).
Rule: at least 3 of the person's own posts (reposts not counted) contain a metascience term, and these are at least
1% of all their own posts. "Peer review" and "impact factor" are not counted, because almost every academic uses
them.
Output: <out.tsv>, one line per person (in or out), with the counts and the account per platform, sorted by the
number of metascience posts, for a check by hand before anything is published.
"""
import sys, os, re, json, glob, collections, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social_terms import NOT_COUNTED

sys.stdout.reconfigure(encoding="utf-8")
data_dir, final_path, posts_dir, hits_path, out_path = sys.argv[1:6]
MIN_POSTS, MIN_SHARE = 3, 0.01
people = {p["id"]: p for p in json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))}
final = json.load(open(final_path, encoding="utf-8"))

# Posts are counted per account file and given to the people who own that account in <social_final>_all.json
# (all their confirmed accounts, also older ones), not by the person id stored in the posts.
every = json.load(open(re.sub(r"\.json$", "", final_path) + "_all.json", encoding="utf-8"))
file_of = lambda kind, acct: f"{kind}_{re.sub(r'[^A-Za-z0-9._-]+', '_', acct.lstrip('@'))}"   # as in download_social_posts.py
owners = collections.defaultdict(list)
for pid, lst in every.items():
    for e in lst:
        owners[file_of(e["kind"], e["account"])].append(pid)
own = collections.Counter()
for fn in glob.glob(os.path.join(posts_dir, "*.jsonl")):
    n = sum(1 for line in open(fn, encoding="utf-8") if not json.loads(line)["repost"])
    for pid in owners.get(os.path.basename(fn)[:-6], []):
        own[pid] += n
meta, terms = collections.Counter(), collections.defaultdict(collections.Counter)
for line in open(hits_path, encoding="utf-8"):
    h = json.loads(line)
    t = [x for x in h["terms"] if x not in NOT_COUNTED]
    if t:
        for pid in owners.get(h["account"], []):
            meta[pid] += 1
            terms[pid].update(t)

rows = []
for pid in final:
    n, m = own[pid], meta[pid]
    keep = m >= MIN_POSTS and n and m / n >= MIN_SHARE
    rows.append(dict(person=pid, name=people[pid]["n"], include="yes" if keep else "no", metascience_posts=m,
                     own_posts=n, share=f"{100 * m / n:.1f}%" if n else "",
                     bluesky=final[pid].get("bluesky", {}).get("account", ""),
                     mastodon=final[pid].get("mastodon", {}).get("account", ""),
                     top_terms=", ".join(t for t, _ in terms[pid].most_common(4)),
                     posts_downloaded="yes" if n else "no"))
rows.sort(key=lambda r: (r["include"] != "yes", -r["metascience_posts"]))
with open(out_path, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
    w.writeheader(); w.writerows(rows)
inc = [r for r in rows if r["include"] == "yes"]
print(f"people with an account: {len(rows)} | posts downloaded: {sum(r['posts_downloaded'] == 'yes' for r in rows)} | "
      f"in the feed: {len(inc)} (Bluesky {sum(bool(r['bluesky']) for r in inc)}, "
      f"Mastodon {sum(bool(r['mastodon']) for r in inc)})")
