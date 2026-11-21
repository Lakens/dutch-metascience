"""Candidate events from the open science blog archive: episodes in which many different bloggers discussed the same
thing at the same time. Claude agents then read each candidate and write the events (see check_blog_events.py).

Usage: python -I blog_candidates.py <blogs.json from export_blogs.R> <out: blog_candidates.json>

Two signals, joined into episodes:
 1. Shared links: the same link (a paper, OSF project, news article or someone else's blog post) in posts by at least
    LINK_MIN_AUTHORS different bloggers within LINK_WINDOW days. Left out: links to the blogger's own blog, home pages
    (blogrolls), and general sites (Twitter, Facebook, Google, ...). A query is kept when it identifies the page.
 2. Bursts of terms: a word pair, or a single word that is mostly written with a capital (a name or acronym; generic
    words burst by chance), used by at least TERM_MIN_AUTHORS bloggers in a two-month window, at least 3 times as many as
    expected from the term's overall rate and the number of active bloggers in the window (Poisson tail probability).
    Only the TOP_TERMS most surprising bursts are used, and only terms used in at most MAX_DOC_SHARE of all posts.
Candidates are joined into one episode when at least half of the posts of the smaller one are also in the other.
Counting different bloggers (not posts) keeps a very active blogger from creating events alone.
Episodes are written out, with all their posts, when they have at least MIN_BLOGGERS different bloggers, or when they
contain a shared link and have at least LINK_MIN_AUTHORS bloggers (a link shared by 3 bloggers is a much stronger sign
of one event than a word used by 3 bloggers). The agents can join small episodes about the same event, and
blog_expand.py later searches the whole archive for each event's names, so a small episode can still reach the minimum
number of bloggers that check_blog_events.py asks for.
Episodes are numbered by number of bloggers, then date, so the episodes with at least MIN_BLOGGERS bloggers keep the
numbers they had before small link episodes were added.
"""
import sys, json, re, math, collections, datetime as dt
from urllib.parse import urlsplit, unquote

sys.stdout.reconfigure(encoding="utf-8")
blogs_path, out_path = sys.argv[1:3]
posts = json.load(open(blogs_path, encoding="utf-8"))
LINK_WINDOW, LINK_MIN_AUTHORS = 60, 3
TERM_MIN_AUTHORS, MAX_DOC_SHARE, TOP_TERMS = 4, 0.15, 120
MIN_BLOGGERS = 5
pid = {p["id"]: p for p in posts}
for p in posts:
    p["date"] = dt.date.fromisoformat(p["d"])
    p["m"] = p["date"].year * 12 + p["date"].month - 1

# ---------------------------------------------------------------- 1. shared links
def host_path(u):
    u = unquote((u or "").strip())
    if u.startswith("//"):
        u = "http:" + u
    if not re.match(r"https?://", u):
        return None, None
    try:
        s = urlsplit(u.replace("&amp;", "&"))
    except ValueError:
        return None, None
    h = re.sub(r"^(www\d?|m|mobile|amp)\.", "", s.netloc.lower().split(":")[0])
    path = re.sub(r"/(index\.html?|amp)?$", "", s.path.rstrip("/"))
    return h, re.sub(r"\.html?$", "", path)

def norm(u):
    h, path = host_path(u)
    if not h:
        return None
    m = re.search(r"(10\.\d{4,9}/[^\s?#]+)", u or "")
    if m and "doi" in h:
        return "doi:" + m.group(1).lower().rstrip(".")
    if not path:
        return None
    if re.match(r"/(search|tag|tags|label|category|author|feeds?|p)(/|$)", path.lower()) and "?" not in u:
        return None
    try:
        q = urlsplit(unquote(u).replace("&amp;", "&")).query
    except ValueError:
        q = ""
    keep = sorted(kv for kv in q.split("&") if kv and not re.match(r"(utm_|share|fbclid|ref=|via=|amp|m=)", kv.lower()))
    return h + path.lower() + ("?" + "&".join(keep).lower() if keep else "")

GENERIC = re.compile(r"^(twitter\.com|x\.com|facebook\.com|google\.[a-z.]+|youtube\.com|youtu\.be|linkedin\.com|"
                     r"amazon\.[a-z.]+|github\.com|feeds\.|feedburner|addtoany|reddit\.com/submit|"
                     r"creativecommons\.org|wordpress\.(com|org)|blogger\.com|draft\.blogger)")
own_hosts = collections.defaultdict(set)
for p in posts:
    h, _ = host_path(p["url"])
    if h:
        own_hosts[p["a"]].add(h)
mentions = collections.defaultdict(list)          # link -> [(date, author, post id, link text)]
for p in posts:
    seen = set()
    for l in p["l"]:
        n = norm(l["u"])
        if not n or n in seen or GENERIC.search(n) or n.split("/")[0] in own_hosts[p["a"]]:
            continue
        seen.add(n)
        mentions[n].append((p["date"], p["a"], p["id"], l["t"]))
cands = []
for n, ms in mentions.items():
    if len({m[1] for m in ms}) < LINK_MIN_AUTHORS:
        continue
    ms.sort(key=lambda m: m[0])
    best = None
    for i, m0 in enumerate(ms):
        win = [m for m in ms[i:] if (m[0] - m0[0]).days <= LINK_WINDOW]
        auth = {m[1] for m in win}
        if len(auth) >= LINK_MIN_AUTHORS and (not best or len(auth) > len(best[1])):
            best = (win, auth)
    if best:
        texts = list(dict.fromkeys(m[3] for m in best[0] if m[3]))
        cands.append(dict(kind="link", label=n, text=texts[:3], posts={m[2] for m in best[0]}, score=len(best[1])))
print(f"shared links: {sum(1 for c in cands if c['kind'] == 'link')} candidates", flush=True)

# ---------------------------------------------------------------- 2. bursts of terms
STOP = set("""a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her here
hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or other our
ours out over own same she should so some such than that the their theirs them then there these they this those
through to too under until up very was we were what when where which while who whom why will with would you your
yours one two three also like get got make made much many may might must us way well even still really think know
see say said says going want new time people thing things lot lots dont don doesn didn isn wasn im ive youre thats
http https www com org html blog post posts comment comments reply pm am
january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday""".split())
for p in posts:
    w = [t.strip("'-") for t in re.findall(r"[^\W\d_][\w'\-]+", (p["t"] + " " + p["x"]).lower().replace("’", "'")) if len(t) > 2]
    p["terms"] = {t for t in w if t not in STOP and len(t) >= 4} | \
                 {f"{a} {b}" for a, b in zip(w, w[1:]) if a not in STOP and b not in STOP}
cap, low = collections.Counter(), collections.Counter()
for p in posts:
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([^\W\d_][\w'\-]+)\b", p["x"]):
        (cap if m.group(1)[0].isupper() else low)[m.group(1).lower().strip("'-")] += 1
for p in posts:
    p["terms"] = {t for t in p["terms"] if " " in t or cap[t] >= 0.6 * (cap[t] + low[t])}
N = len(posts)
df = collections.Counter(t for p in posts for t in p["terms"])
by_term_month = collections.defaultdict(lambda: collections.defaultdict(set))
for p in posts:
    for t in p["terms"]:
        if df[t] >= 5 and df[t] / N <= MAX_DOC_SHARE:
            by_term_month[t][p["m"]].add(p["a"])
active = collections.defaultdict(set)
for p in posts:
    active[p["m"]].add(p["a"])
total_am = sum(len(v) for v in active.values())
def pois_sf(k, lam):
    s, term = 0.0, math.exp(-lam)
    for i in range(k):
        s += term
        term *= lam / (i + 1)
    return max(1e-300, 1 - s)
bursts = []
for t, tm in by_term_month.items():
    if len(set().union(*tm.values())) < TERM_MIN_AUTHORS:
        continue
    rate = sum(len(v) for v in tm.values()) / total_am
    best = None
    for m in tm:
        for m0 in (m - 1, m):
            a = tm.get(m0, set()) | tm.get(m0 + 1, set())
            if len(a) < TERM_MIN_AUTHORS:
                continue
            lam = rate * len(active.get(m0, set()) | active.get(m0 + 1, set()))
            score = -math.log10(pois_sf(len(a), lam))
            if len(a) / lam >= 3 and (not best or score > best[0]):
                best = (score, m0)
    if best:
        bursts.append((best[0], t, best[1]))
bursts.sort(reverse=True)
for score, t, m0 in bursts[:TOP_TERMS]:
    cands.append(dict(kind="term", label=t, text=[], score=score,
                      posts={p["id"] for p in posts if p["m"] in (m0, m0 + 1) and t in p["terms"]}))
print(f"term bursts: {len(bursts)}, the {TOP_TERMS} most surprising used", flush=True)

# ---------------------------------------------------------------- episodes
parent = list(range(len(cands)))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i
for i in range(len(cands)):
    for j in range(i + 1, len(cands)):
        A, B = cands[i]["posts"], cands[j]["posts"]
        if A and B and len(A & B) / min(len(A), len(B)) >= 0.5:
            parent[find(i)] = find(j)
groups = collections.defaultdict(list)
for i, c in enumerate(cands):
    groups[find(i)].append(c)
episodes = []
for g in groups.values():
    ps = sorted(set().union(*(c["posts"] for c in g)), key=lambda x: pid[x]["date"])
    au = sorted({pid[x]["a"] for x in ps})
    if len(au) < (LINK_MIN_AUTHORS if any(c["kind"] == "link" for c in g) else MIN_BLOGGERS):
        continue
    episodes.append(dict(
        n_bloggers=len(au), start=pid[ps[0]]["d"], end=pid[ps[-1]]["d"], bloggers=au,
        terms=[c["label"] for c in sorted(g, key=lambda c: -c["score"]) if c["kind"] == "term"][:10],
        links=[dict(link=c["label"], text=c["text"]) for c in g if c["kind"] == "link"][:6],
        posts=[dict(id=x, a=pid[x]["a"], d=pid[x]["d"], t=pid[x]["t"], url=pid[x]["url"]) for x in ps]))
episodes.sort(key=lambda e: (-e["n_bloggers"], e["start"]))
for i, e in enumerate(episodes):
    e["episode"] = i + 1
json.dump(dict(settings=dict(link_window=LINK_WINDOW, link_min_authors=LINK_MIN_AUTHORS, term_min_authors=TERM_MIN_AUTHORS,
                             max_doc_share=MAX_DOC_SHARE, top_terms=TOP_TERMS, min_bloggers=MIN_BLOGGERS),
               n_posts=len(posts), n_bloggers=len({p["a"] for p in posts}), episodes=episodes),
          open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(episodes)} episodes: {sum(e['n_bloggers'] >= MIN_BLOGGERS for e in episodes)} with at least {MIN_BLOGGERS} bloggers, "
      f"the others with a shared link and at least {LINK_MIN_AUTHORS}")
for e in episodes:
    print(f"  {e['episode']:2d}. {e['n_bloggers']:2d} bloggers {e['start']}..{e['end']}  {' · '.join(e['terms'][:5])}  "
          f"{' · '.join(l['link'][:50] for l in e['links'][:1])}")
