"""Search the whole blog archive for more posts about each 'discussed on blogs' event.

Usage: python -I blog_expand.py <blogs.json> <out: blog_expansion.json> <agent events files...>

The candidate episodes (blog_candidates.py) catch only part of a debate: a link that several bloggers share, or a burst
of a word. Many posts about the same debate use neither. So the agents that read the episodes also gave, for every
event, 1 to 3 specific search terms (mostly names, such as "Wansink" or "Bargh"). This script lists every post that
contains one of those terms (as a whole word, ignoring case and accents) and was written from WINDOW_BEFORE days before
the event's first post to WINDOW_AFTER days after its last post, and that is not yet part of the event. Claude agents
then read these posts and keep only those about the event (check_blog_events.py accepts only posts from this list or
from the event's own episodes).
"""
import sys, json, re, unicodedata, datetime as dt

sys.stdout.reconfigure(encoding="utf-8")
blogs_path, out_path = sys.argv[1:3]
event_files = sys.argv[3:]
WINDOW_BEFORE, WINDOW_AFTER = 30, 365
posts = json.load(open(blogs_path, encoding="utf-8"))
pid = {p["id"]: p for p in posts}

def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()
text = {p["id"]: fold(p["t"] + " \n " + p["x"]) for p in posts}

# events: the main entry of each kept event, posts added by entries marked "same_as_existing", search terms
ev = {}
search = {}
added = {}
for f in event_files:
    for x in json.load(open(f, encoding="utf-8")):
        if "existing" in x:
            search[x["existing"]] = x["search"]
        elif x.get("keep"):
            ev[x["episode"]] = x
            if x.get("search"):
                search[x["episode"]] = x["search"]
        elif x.get("same_as_existing"):
            added.setdefault(int(x["same_as_existing"]), set()).update(int(i) for i in x.get("relevant", []))

out = {}
for k, x in sorted(ev.items()):
    terms = search.get(k, [])
    if not terms:
        print(f"  episode {k} ({x['title']}): no search terms")
        continue
    rel = {int(i) for i in x["relevant"]} | added.get(k, set())
    ds = sorted(dt.date.fromisoformat(pid[i]["d"]) for i in rel)
    d0, d1 = ds[0] - dt.timedelta(days=WINDOW_BEFORE), ds[-1] + dt.timedelta(days=WINDOW_AFTER)
    pats = [re.compile(r"(?<!\w)" + re.escape(fold(t)) + r"(?!\w)") for t in terms]
    hits = [p["id"] for p in posts if p["id"] not in rel and d0 <= dt.date.fromisoformat(p["d"]) <= d1
            and any(q.search(text[p["id"]]) for q in pats)]
    hits.sort(key=lambda i: pid[i]["d"])
    out[k] = dict(title=x["title"], search=terms, window=[d0.isoformat(), d1.isoformat()], posts=hits)
    print(f"  episode {k:2d} {x['title'][:60]:60s} terms {terms}: {len(hits)} more posts, "
          f"{len({pid[i]['a'] for i in hits} - {pid[i]['a'] for i in rel})} new bloggers")
json.dump(dict(settings=dict(window_before=WINDOW_BEFORE, window_after=WINDOW_AFTER), events=out),
          open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(out)} events searched; written to {out_path}")
