"""Search the downloaded Bluesky and Mastodon posts for metascience terms (private research data, never published).

Usage: python -I search_social_posts.py <posts folder> <out.jsonl>
Input: the files written by download_social_posts.py (one post per line, with the person's id).
Output: <out.jsonl> with every post that contains at least one term (person, date, text, whether it is a reply or a
repost, and the matched terms), and a summary printed per term, per theme and per year.

The terms and how they are matched: social_terms.py.
"""
import sys, os, json, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social_terms import THEMES, THEME_OF, terms_in

sys.stdout.reconfigure(encoding="utf-8")
posts_dir, out_path = sys.argv[1:3]

n_posts = n_own = 0
people_any, people_own = set(), set()
per_term, per_term_people, per_theme_people = collections.Counter(), collections.defaultdict(set), collections.defaultdict(set)
per_year, per_year_hit = collections.Counter(), collections.Counter()
files = sorted(glob.glob(os.path.join(posts_dir, "*.jsonl")))
with open(out_path, "w", encoding="utf-8") as out:
    for fn in files:
        account = os.path.basename(fn)[:-6]
        for line in open(fn, encoding="utf-8"):
            p = json.loads(line)
            n_posts += 1
            people_any.add(p["person"])
            if p["repost"]:
                continue   # reposts are someone else's words; only the person's own posts and replies are counted
            n_own += 1
            people_own.add(p["person"])
            y = (p.get("date") or "")[:4]
            per_year[y] += 1
            text = p.get("text") or ""
            hits = terms_in(text)
            if not hits:
                continue
            per_year_hit[y] += 1
            for t in hits:
                per_term[t] += 1
                per_term_people[t].add(p["person"])
                per_theme_people[THEME_OF[t]].add(p["person"])
            out.write(json.dumps(dict(person=p["person"], account=account, date=p.get("date"), reply=p["reply"],
                                      terms=hits, text=text, uri=p.get("uri")), ensure_ascii=False) + "\n")

print(f"accounts: {len(files)} | posts: {n_posts} (own posts and replies: {n_own}) | people: {len(people_own)}")
print(f"own posts with a term: {sum(per_year_hit.values())} | "
      f"people with at least one: {len(set().union(*per_term_people.values())) if per_term_people else 0}")
for th, terms in THEMES.items():
    print(f"\n{th}: {len(per_theme_people[th])} people")
    for t in terms:
        print(f"  {t:34s} posts {per_term[t]:6d}   people {len(per_term_people[t]):4d}")
print("\nper year (own posts | with a term | share):")
for y in sorted(per_year):
    if y:
        print(f"  {y}: {per_year[y]:7d} | {per_year_hit[y]:5d} | {100 * per_year_hit[y] / per_year[y]:.1f}%")
