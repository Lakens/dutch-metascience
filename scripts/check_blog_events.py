"""Check the 'discussed on blogs' events written by Claude agents, and add working links.

Usage: python -I check_blog_events.py <blog_candidates.json> <blogs.json> <blog_expansion.json> <out: blog_events.json>
                                     <agent files...>

The agents read the posts of each candidate episode (blog_candidates.py) and wrote, for real events only: a title, one
sentence, the posts that are about the event ('relevant'), 3-6 posts to link ('show'), themes, and whether the event
concerns Dutch researchers. Episodes about the same event were joined ('join'), and an episode about an event that was
already found adds its posts to that event ('same_as_existing'). A second round of agents read the posts that the
archive search found for each event (blog_expand.py), and wrote which of them are about the event ('add'), and possibly
a new choice of posts to link and a new sentence that covers the whole debate. An event is kept only when
 - every post id belongs to the event's own or joined episodes or to its archive search results, and 'show' is part
   of 'relevant';
 - the relevant posts come from at least MIN_BLOGGERS different bloggers (except the events in ADDED_BY_HAND, which need
   at least 3), and the shown posts from at least 3;
 - the text is one sentence of at most 45 words, the title at most 80 characters, the themes exist.
The dates are not taken from the agents: the event runs from the month of the first relevant post to that of the last.
Links: each shown post links to its original address when that still answers (HTTP status below 400), and otherwise
to the closest copy in the Internet Archive's Wayback Machine (its availability API); the archive copy is stored too.
"""
import sys, os, json, re, time, datetime as dt
import requests

sys.stdout.reconfigure(encoding="utf-8")
cand_path, blogs_path, exp_path, out_path = sys.argv[1:5]
event_files = sys.argv[5:]
EXP = {int(k): v for k, v in json.load(open(exp_path, encoding="utf-8"))["events"].items()}
MIN_BLOGGERS, MIN_SHOWN_BLOGGERS, MAX_WORDS, MAX_TITLE = 5, 3, 45, 80
# events kept with fewer than MIN_BLOGGERS bloggers, by decision of the site's maintainer (episode: reason); every other
# check still applies, and the event is marked by_hand in the output
ADDED_BY_HAND = {32: "the Förster case (4 bloggers) concerns a Dutch university and the Dutch research integrity board LOWI"}
UA = {"User-Agent": "dutch-metascience/1.0 (https://github.com/Lakens/dutch-metascience)"}
C = json.load(open(cand_path, encoding="utf-8"))
E = {e["episode"]: e for e in C["episodes"]}
blogs = {p["id"]: p for p in json.load(open(blogs_path, encoding="utf-8"))}
n_themes = 20

def live(url):
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True, stream=True)
        r.close()
        return r.status_code < 400
    except requests.RequestException:
        return False
def archived(url, date):
    try:
        r = requests.get("https://archive.org/wayback/available", params=dict(url=url, timestamp=date.replace("-", "")),
                         headers=UA, timeout=30)
        snap = r.json().get("archived_snapshots", {}).get("closest", {})
        return snap.get("url", "").replace("http://web.archive.org", "https://web.archive.org") if snap.get("available") else ""
    except (requests.RequestException, ValueError):
        return ""

# collect the agents' answers: kept events, posts added from other episodes, and the archive search verdicts
main, extra, verdict = {}, {}, {}
for f in event_files:
    for x in json.load(open(f, encoding="utf-8")):
        if "existing" in x:
            continue                                   # only search terms (used by blog_expand.py)
        if "add" in x:
            verdict[x["episode"]] = x
        elif x.get("keep"):
            main[x["episode"]] = x
        elif x.get("same_as_existing"):
            t, k = int(x["same_as_existing"]), x["episode"]
            bad = {int(i) for i in x.get("relevant", [])} - {p["id"] for p in E[k]["posts"]}
            if bad: print(f"  episode {k}: posts {sorted(bad)} are not in that episode; ignored")
            extra.setdefault(t, []).append((k, [int(i) for i in x.get("relevant", []) if int(i) not in bad]))
            print(f"  episode {k} added to episode {t}: {x.get('reason', '')}")
        else:
            print(f"  rejected episode {x['episode']}: {x.get('reason', '')}")
out, problems = [], []
for k, x in sorted(main.items()):
    v = verdict.get(k, {})
    ep_ids = {p["id"] for j in [k] + [int(j) for j in x.get("join", [])] for p in E[j]["posts"]}
    found = set(EXP.get(k, {}).get("posts", []))
    allowed = ep_ids | found | {i for _, ids in extra.get(k, []) for i in ids}
    rel = sorted({int(i) for i in x["relevant"]} | {i for _, ids in extra.get(k, []) for i in ids} | {int(i) for i in v.get("add", [])})
    show = [int(i) for i in (v.get("show") or x["show"])]
    if v.get("text"):
        x = dict(x, text=v["text"])
    errs = []
    if not set(rel) <= allowed: errs.append(f"relevant posts not in the event's episodes or search results: {sorted(set(rel) - allowed)}")
    if not set(show) <= set(rel): errs.append(f"shown posts not relevant: {sorted(set(show) - set(rel))}")
    nb = len({blogs[i]["a"] for i in rel if i in blogs})
    if nb < (MIN_SHOWN_BLOGGERS if k in ADDED_BY_HAND else MIN_BLOGGERS): errs.append(f"only {nb} bloggers in the relevant posts")
    ns = len({blogs[i]["a"] for i in show if i in blogs})
    if ns < MIN_SHOWN_BLOGGERS: errs.append(f"shown posts from only {ns} bloggers")
    if any(i not in blogs for i in rel): errs.append("unknown post ids")
    # sentence ends, not counting the full stops of abbreviations such as "et al." or "e.g."
    plain = re.sub(r"\b(et al|e\.g|i\.e|vs|cf|Dr|Mr|Ms|Prof|Jr|St)\.", "x", x["text"].strip())
    if len(x["text"].split()) > MAX_WORDS or len(re.findall(r"[.!?](\s|$)", plain)) > 1:
        errs.append("text is not one sentence of at most 45 words")
    if len(x["title"]) > MAX_TITLE: errs.append("title too long")
    if not x["themes"] or any(not (0 <= int(t) < n_themes) for t in x["themes"]): errs.append("bad themes")
    if errs:
        problems.append((k, x["title"], errs))
        print(f"  NOT KEPT episode {k} ({x['title']}): {'; '.join(errs)}")
        continue
    ds = sorted(blogs[i]["d"] for i in rel)
    d0, d1 = dt.date.fromisoformat(ds[0]), dt.date.fromisoformat(ds[-1])
    # a shown post needs a working link: its address answers, or the Wayback Machine has a copy. Posts without one
    # (no usable address in the archive, or a site that refuses automated checks and has no copy) are replaced by
    # another relevant post with a working link, preferring a blogger not shown yet and a date close by.
    cache = {}
    def link_of(i):
        if i not in cache:
            p = blogs[i]
            url = p["url"] if isinstance(p["url"], str) and re.match(r"https?://", p["url"] or "") else ""
            arch = archived(url, p["d"]) if url else ""
            ok = live(url) if url else False
            cache[i] = (url if ok else arch, arch, ok)
            time.sleep(0.5)
        return cache[i]
    chosen = []
    for i in sorted(show, key=lambda i: blogs[i]["d"]):
        if link_of(i)[0]:
            chosen.append(i)
            continue
        shown_auth = {blogs[j]["a"] for j in chosen} | {blogs[j]["a"] for j in show if j != i}
        pool = sorted((j for j in rel if j not in show and j not in chosen),
                      key=lambda j: (blogs[j]["a"] in shown_auth, abs((dt.date.fromisoformat(blogs[j]["d"]) -
                                                                     dt.date.fromisoformat(blogs[i]["d"])).days)))
        sub = next((j for j in pool if link_of(j)[0]), None)
        print(f"    post {i} ({blogs[i]['a']}) has no working link; {'replaced by ' + str(sub) + ' (' + blogs[sub]['a'] + ')' if sub else 'left out'}")
        if sub:
            chosen.append(sub)
    posts = [dict(a=blogs[i]["a"], t=blogs[i]["t"], d=blogs[i]["d"], u=link_of(i)[0], arch=link_of(i)[1], live=link_of(i)[2])
             for i in sorted(set(chosen), key=lambda i: blogs[i]["d"])]
    if len({p["a"] for p in posts}) < MIN_SHOWN_BLOGGERS:
        problems.append((k, x["title"], ["fewer than 3 bloggers with working links"]))
        print(f"  NOT KEPT episode {k} ({x['title']}): fewer than 3 bloggers with working links")
        continue
    out.append(dict(title=x["title"].strip(), text=x["text"].strip(), year=d0.year, month=d0.month,
                    end_year=d1.year, end_month=d1.month, themes=sorted({int(t) for t in x["themes"]}),
                    dutch=bool(x.get("dutch")), n_bloggers=nb, n_posts=len(rel),
                    bloggers=sorted({blogs[i]["a"] for i in rel}), posts=posts, episode=k,
                    n_found_by_search=len(set(rel) & found - ep_ids), by_hand=k in ADDED_BY_HAND))
    print(f"  kept {d0:%Y-%m}..{d1:%Y-%m} {nb:2d} bloggers: {x['title']} | links live {sum(p['live'] for p in posts)}/{len(posts)}, "
          f"archived {sum(bool(p['arch']) for p in posts)}/{len(posts)}", flush=True)
out.sort(key=lambda e: (e["year"], e["month"]))
json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(out)} events written to {out_path}; {len(problems)} not kept after checking")
