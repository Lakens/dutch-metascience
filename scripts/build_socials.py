"""Data for the Socials page: what the people on the site post about metascience on Bluesky and Mastodon.

Usage: python -I build_socials.py <site data folder> <nl_metascience.sqlite> <posts folder> <hits.jsonl>
           <social_final.json> <feed_accounts.tsv> <bluesky_post_details.json> <location_verdicts.tsv>
Input: the confirmed accounts (confirm_social_accounts.py; <social_final>_all.json holds all accounts of a person),
the downloaded posts (download_social_posts.py), the posts with a metascience term (search_social_posts.py) and
the people selected for the feeds (select_feed_accounts.py).
Only people who work in the Netherlands now are counted: "yes" in <location_verdicts.tsv> (Claude reviewers, see
location_review_instructions.md; "no" and "unclear" are left out). The posts of everyone else stay downloaded but are
not used.
Output: <site data folder>/socials.json: counts, plus the text of the most popular posts of the busiest weeks.
People are named (with links to their accounts) only in the parts about individuals (top posters, popular posts, who
interacts with whom), and only when they are in the feeds (select_feed_accounts.py). Only a person's own posts and
replies are counted, not reposts.

Parts:
 - per theme and term: number of posts and of people (social_terms.py), in total and per platform;
 - per month and theme: number of posts, and all own posts that month (for shares), in total and per platform;
 - terms in posts compared with terms in the titles and abstracts of the papers on the site;
 - the busiest weeks: the weeks with the most metascience posts (each the highest within three weeks on either
   side), compared with the median week of the half year before, with the terms used most and unusually often;
 - words used most in the metascience posts of each theme (for word clouds), leaving out common words and words
   that are themselves a term; a word counts when at least 5 people used it;
 - the websites linked most often in metascience posts;
 - top 10 people per platform by number of metascience posts ("peer review" and "impact factor" not counted);
 - rising and falling on social media (for the Inferences page): each term's and theme's share of the metascience
   posts in the last 24 complete months, compared with the 24 months before, as a ratio with a 95% interval from
   resampling people (1,000 times), so that one very active person cannot make the interval narrow. Terms with fewer
   than 30 posts in the two periods together, or fewer than 5 people, are left out;
 - who interacts with whom: mentions (@name in a post) and reposts between people in the feeds, in all their posts,
   plus replies between them among the Bluesky metascience posts (fetch_bluesky_links.py stores which post a post
   replies to; on Mastodon a reply mentions the other person, so it is already counted), and whether the two also
   wrote a paper together.
People with several records on the site (one account shared by several records) are counted once.
"""
import sys, os, re, json, glob, csv, sqlite3, collections, datetime, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social_terms import THEMES, THEME_OF, NOT_COUNTED, terms_in

sys.stdout.reconfigure(encoding="utf-8")
data_dir, db_path, posts_dir, hits_path, final_path, feed_path, details_path, location_path = sys.argv[1:9]
in_nl = {r["person"] for r in csv.DictReader(open(location_path, encoding="utf-8"), delimiter="	")
         if r["verdict"].strip().lower() == "yes"}
details = json.load(open(details_path, encoding="utf-8"))   # full links of Bluesky posts (fetch_bluesky_links.py)
people = {p["id"]: p for p in json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))}
papers = json.load(open(os.path.join(data_dir, "papers.json"), encoding="utf-8"))
every = json.load(open(re.sub(r"\.json$", "", final_path) + "_all.json", encoding="utf-8"))
# people who are no longer on the site (their papers were removed in a later hand check) are left out
_gone = [p for p in every if p not in people]
every = {p: v for p, v in every.items() if p in people}
print(f"accounts of people no longer on the site, left out: {len(_gone)}")
final = json.load(open(final_path, encoding="utf-8"))
feed_ids = {r["person"] for r in csv.DictReader(open(feed_path, encoding="utf-8"), delimiter="\t") if r["include"] == "yes"}

# ---------------------------------------------------------------- one person = all records that share an account
file_of = lambda kind, acct: f"{kind}_{re.sub(r'[^A-Za-z0-9._-]+', '_', acct.lstrip('@'))}"   # as in download_social_posts.py
parent = {p: p for p in every}
def find(p):
    while parent[p] != p:
        parent[p] = parent[parent[p]]; p = parent[p]
    return p
first_owner = {}
for pid, lst in every.items():
    for e in lst:
        f = file_of(e["kind"], e["account"])
        if f in first_owner:
            parent[find(pid)] = find(first_owner[f])
        else:
            first_owner[f] = pid
groups = collections.defaultdict(list)
for pid in every:
    groups[find(pid)].append(pid)
canon = {}   # record -> the record with the most papers in its group
for g in groups.values():
    best = max(g, key=lambda p: (people[p]["k"], p))
    for p in g:
        canon[p] = best
# only people who work in the Netherlands now (a verdict is given for one record of each person)
nl_people = {canon[p] for g in groups.values() if any(q in in_nl for q in g) for p in g}
owner_of_file = {file_of(e["kind"], e["account"]): canon[pid] for pid, lst in every.items() for e in lst
                 if canon[pid] in nl_people}
platform_of_file = {f: f.split("_", 1)[0] for f in owner_of_file}
feed = {canon[p] for p in feed_ids if p in canon and canon[p] in nl_people}
def post_link(h):
    u = h.get("uri") or ""
    m = re.match(r"at://([^/]+)/app\.bsky\.feed\.post/(.+)$", u)
    return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}" if m else u
def account_link(kind, acct):
    if kind == "bluesky":
        return f"https://bsky.app/profile/{acct}"
    user, server = acct.lstrip("@").split("@", 1)
    return f"https://{server}/@{user}"

hits = [json.loads(l) for l in open(hits_path, encoding="utf-8")]
hits = [h for h in hits if h["account"] in owner_of_file and h.get("date")]
hit_uris = {h["uri"] for h in hits}

# ---------------------------------------------------------------- own posts per month (all posts, for shares)
month_total = collections.Counter()
month_total_pl = collections.defaultdict(collections.Counter)   # platform -> month -> own posts
popularity = {}   # metascience post -> (likes, reposts) at download time
did_owner = {}    # Bluesky account identifier (did) -> person, to know whose post a reply answers
for fn in glob.glob(os.path.join(posts_dir, "*.jsonl")):
    if os.path.basename(fn)[:-6] not in owner_of_file:
        continue   # not someone who works in the Netherlands now
    for line in open(fn, encoding="utf-8"):
        p = json.loads(line)
        if not p["repost"] and (p.get("uri") or "").startswith("at://"):
            did_owner.setdefault(p["uri"].split("/")[2], owner_of_file.get(os.path.basename(fn)[:-6]))
        if not p["repost"] and p.get("date"):
            month_total[p["date"][:7]] += 1
            month_total_pl[platform_of_file[os.path.basename(fn)[:-6]]][p["date"][:7]] += 1
            if p.get("uri") in hit_uris:
                popularity[p["uri"]] = (p.get("likes") or 0, p.get("reposts") or 0)

# ---------------------------------------------------------------- metascience posts
term_posts, term_people = collections.Counter(), collections.defaultdict(set)
term_pl, term_people_pl = collections.defaultdict(collections.Counter), collections.defaultdict(lambda: collections.defaultdict(set))
month_theme_pl = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
theme_posts, theme_people = collections.Counter(), collections.defaultdict(set)
month_theme = collections.defaultdict(collections.Counter)
week_total, week_term = collections.Counter(), collections.defaultdict(collections.Counter)
poster = collections.Counter()   # (platform, account file) -> counted metascience posts
def week_of(d):
    day = datetime.date.fromisoformat(d[:10])
    return (day - datetime.timedelta(days=day.weekday())).isoformat()
for h in hits:
    who = owner_of_file[h["account"]]
    m, w = h["date"][:7], week_of(h["date"])
    pl = platform_of_file[h["account"]]
    for t in h["terms"]:
        term_posts[t] += 1; term_people[t].add(who)
        term_pl[pl][t] += 1; term_people_pl[pl][t].add(who)
    for th in {THEME_OF[t] for t in h["terms"]}:
        month_theme_pl[pl][th][m] += 1
    month_theme_pl[pl]["any"][m] += 1
    for th in {THEME_OF[t] for t in h["terms"]}:
        theme_posts[th] += 1; theme_people[th].add(who); month_theme[th][m] += 1
    month_theme["any"][m] += 1
    week_total[w] += 1
    week_term[w].update(h["terms"])
    if set(h["terms"]) - NOT_COUNTED:
        poster[h["account"]] += 1
n_meta = len(hits)

# ---------------------------------------------------------------- the same terms in the papers on the site
db = sqlite3.connect(db_path)
site_ids = {p["id"] for p in papers}
paper_terms = collections.Counter()
paper_theme = collections.Counter()
for wid, title, abstract in db.execute("SELECT work_id, title, abstract FROM oa_works"):
    if wid not in site_ids:
        continue
    ts = terms_in((title or "") + " " + (abstract or ""))
    paper_terms.update(ts)
    paper_theme.update({THEME_OF[t] for t in ts})
n_papers = len(site_ids)

themes_out = []
for th, terms in THEMES.items():
    themes_out.append(dict(name=th, posts=theme_posts[th], people=len(theme_people[th]),
                           paper_share=round(100 * paper_theme[th] / n_papers, 2),
                           post_share=round(100 * theme_posts[th] / n_meta, 2),
                           terms=[dict(name=t, posts=term_posts[t], people=len(term_people[t]),
                                       by={pl: dict(posts=term_pl[pl][t], people=len(term_people_pl[pl][t]))
                                           for pl in ("bluesky", "mastodon")},
                                       post_share=round(100 * term_posts[t] / n_meta, 2),
                                       paper_share=round(100 * paper_terms[t] / n_papers, 2),
                                       papers=paper_terms[t]) for t in terms]))

# ---------------------------------------------------------------- busiest weeks
weeks = sorted(week_total)
overall = collections.Counter()
for w in weeks:
    overall.update(week_term[w])
peaks = []
for i, w in enumerate(weeks):
    around = [week_total[x] for x in weeks[max(0, i - 3): i + 4] if x != w]
    if week_total[w] >= 40 and all(week_total[w] > a for a in around):
        peaks.append(w)
peaks = sorted(peaks, key=lambda w: -week_total[w])[:10]
peaks_out = []
for w in sorted(peaks):
    lift = []
    for t, n in week_term[w].items():
        expected = overall[t] / n_meta * week_total[w]
        if n >= 5 and n >= 2 * expected:
            lift.append((n / max(expected, 0.5), t, n))
    lift.sort(reverse=True)
    recent = [week_total[x] for x in weeks[max(0, weeks.index(w) - 26): weeks.index(w)]]
    # the most liked and reposted posts of the week, by people in the feeds (with their text and a link)
    pop = sorted((h for h in hits if week_of(h["date"]) == w and owner_of_file[h["account"]] in feed),
                 key=lambda h: -sum(popularity.get(h["uri"], (0, 0))))[:3]
    popular = [dict(id=owner_of_file[h["account"]], n=people[owner_of_file[h["account"]]]["n"],
                    platform=platform_of_file[h["account"]], date=h["date"][:10], url=post_link(h),
                    likes=popularity.get(h["uri"], (0, 0))[0], reposts=popularity.get(h["uri"], (0, 0))[1],
                    text=h["text"][:400] + ("…" if len(h["text"]) > 400 else "")) for h in pop]
    peaks_out.append(dict(week=w, posts=week_total[w], typical=round(sorted(recent)[len(recent) // 2]) if recent else None,
                          people=len({owner_of_file[h["account"]] for h in hits if week_of(h["date"]) == w}),
                          top=[dict(name=t, posts=n) for t, n in week_term[w].most_common(3)],
                          unusual=[dict(name=t, posts=n, times=round(r, 1)) for r, t, n in lift[:3]],
                          popular=popular))

# ---------------------------------------------------------------- words per theme (word clouds)
STOP = set("""a about above after again against all almost also although always am among an and another any anyone
anything are aren around as at away back be because been before being below between both but by can cannot could
couldn did didn do does doesn doing don done down during each either else enough even ever every few find first for
from further get gets getting go going gone got had hasn has have haven having he her here hers herself him himself his
how however i if in into is isn it its itself just know last least less let like lot lots made make makes making many
may me might more most much must my myself need needs new next no nor not now of off often oh ok okay on once one only
or other others our ours ourselves out over own per perhaps please quite rather re really right said same say says see
seem seems she should shouldn since so some something still such sure take than thank thanks that the their theirs them
themselves then there these they thing things think this those though through thus to today too two under until up upon
us use used using very via want was wasn way we well were weren what when where whether which while who whom whose why
will with within without won would wouldn yes yet you your yours yourself yourselves also amp rt https http www com org
html pdf de het een en van in op te dat die is niet met voor zijn er aan als ook maar om dan nog wel naar bij uit door
over kan al wat worden heb hebben wordt zo meer geen toch nu mijn je jij we wij ze zij hij haar hun ons onze deze dit
der und die das ist nicht mit für auf ein eine zu sich auch es le la les des et du un une est pour pas que qui dans
year years time day week good great people work just via read thread post posts paper papers new study
research science scientific scientists researchers studies results important interesting different help etc field part
recent better best based large small problem approach looking support available published publish article articles
authors academic academia university information share sharing talk project projects evidence interested lot
join check course follow actually trying look start already forward happy free never instead show point means together
working run""".split())
# words that are part of any term (for example "recognition", "peer", "null") are not shown either
STOP |= {w.lower() for th in THEMES.values() for rx in th.values() for w in re.findall(r"[A-Za-z]{3,}", rx)}
WORD = re.compile(r"[a-zà-öø-ÿ][a-zà-öø-ÿ'’-]{2,}")
URLISH = re.compile(r"https?://\S+|\S+\.\S+/\S*|@[\w.-]+(@[\w.-]+)?")
words_theme = collections.defaultdict(collections.Counter)
words_people = collections.defaultdict(lambda: collections.defaultdict(set))
for h in hits:
    who = owner_of_file[h["account"]]
    toks = {w.strip("'’-") for w in WORD.findall(URLISH.sub(" ", h["text"].lower()).replace("#", " "))}
    toks = {w for w in toks if len(w) > 2 and w not in STOP and "'" not in w and "’" not in w and not terms_in(w)}
    for th in {THEME_OF[t] for t in h["terms"]}:
        own = set(re.findall(r"[a-z]+", " ".join(THEMES[th]).lower()))
        for w in toks - own:
            words_theme[th][w] += 1
            words_people[th][w].add(who)
clouds = {th: [[w, n] for w, n in words_theme[th].most_common(400) if len(words_people[th][w]) >= 5][:60]
          for th in THEMES}

# ---------------------------------------------------------------- links
URL = re.compile(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s)\]>\"']*)?", re.I)
servers = {e["account"].rsplit("@", 1)[1].lower() for lst in every.values() for e in lst if e["kind"] == "mastodon"}
servers |= {"mastodon.social", "fediscience.org", "mstdn.social", "mastodon.online", "scholar.social"}
site_doi = {p["doi"].lower(): p for p in papers if p.get("doi")}
DOI = re.compile(r"(10\.\d{4,9}/[^\s?#]+)")
dom_posts, dom_people = collections.Counter(), collections.defaultdict(set)
dom_pl = collections.defaultdict(collections.Counter)
doi_posts, doi_people = collections.Counter(), collections.defaultdict(set)
for h in hits:
    who = owner_of_file[h["account"]]
    seen, dois = set(), set()
    # Bluesky: the full addresses stored with the post; Mastodon: the addresses in the text (they are complete there)
    full = details.get(h["uri"], {}).get("links") if h["account"].startswith("bluesky_") else None
    found = [URL.match(u) for u in full] if full is not None else list(URL.finditer(h["text"]))
    for m in found:
        if not m:
            continue
        whole, dom, path = m.group(0), m.group(1).lower(), m.group(2) or ""
        if full is None and not (whole.lower().startswith("http") or path.startswith("/")):
            continue   # "e.g." or a domain name in a sentence without a link
        if not whole.endswith("...") and not whole.endswith("\u2026"):
            d = DOI.search(path)
            if d and d.group(1).lower().rstrip(".,;:)") in site_doi:
                dois.add(d.group(1).lower().rstrip(".,;:)"))
        if dom in ("dx.doi.org",):
            dom = "doi.org"
        if dom in ("youtu.be",):
            dom = "youtube.com"
        if dom in servers or dom.endswith(".social") or dom.startswith("mastodon."):
            dom = "Mastodon posts"
        elif dom == "bsky.app":
            dom = "Bluesky posts"
        seen.add(dom)
    for dom in seen:
        dom_posts[dom] += 1; dom_people[dom].add(who); dom_pl[platform_of_file[h["account"]]][dom] += 1
    for d in dois:
        doi_posts[d] += 1; doi_people[d].add(who)
links_out = [dict(site=d, posts=n, people=len(dom_people[d]), by={pl: dom_pl[pl][d] for pl in ("bluesky", "mastodon")})
             for d, n in dom_posts.most_common(60)
             if len(dom_people[d]) >= 3][:25]
# papers on this site linked by at least two people (one person sharing their own paper is not shared widely)
shared_papers = [dict(id=site_doi[d]["id"], t=site_doi[d]["t"], y=site_doi[d]["y"], doi=site_doi[d]["doi"], posts=n,
                      people=len(doi_people[d])) for d, n in doi_posts.most_common() if len(doi_people[d]) >= 2][:15]

# ---------------------------------------------------------------- top posters per platform (people in the feeds)
top = {}
for kind in ("bluesky", "mastodon"):
    rows = collections.Counter()   # all accounts of a person on this platform together
    for f, n in poster.items():
        if platform_of_file[f] == kind and owner_of_file[f] in feed:
            rows[owner_of_file[f]] += n
    out = []
    for pid, n in rows.most_common(10):
        # the account shown: the newest one (social_final.json) of any record of this person
        acct = next((final[p][kind]["account"] for p in groups[find(pid)] if kind in final.get(p, {})), None) or             next(e["account"] for p in groups[find(pid)] for e in every[p] if e["kind"] == kind)
        out.append(dict(id=pid, n=people[pid]["n"], account=acct, url=account_link(kind, acct), posts=n))
    top[kind] = out

# ---------------------------------------------------------------- who interacts with whom (people in the feeds)
handle_owner, user_owner = {}, collections.defaultdict(set)
for pid, lst in every.items():
    if canon[pid] not in feed:
        continue
    for e in lst:
        a = e["account"].lower().lstrip("@")
        handle_owner[a] = canon[pid]
        if e["kind"] == "mastodon":
            user_owner[a.split("@")[0]].add(canon[pid])
MENTION = re.compile(r"(?<![\w@/])@([a-z0-9_.-]+(?:@[a-z0-9.-]+\.[a-z]{2,})?)", re.I)
pair = collections.Counter()
for fn in glob.glob(os.path.join(posts_dir, "*.jsonl")):
    f = os.path.basename(fn)[:-6]
    me = owner_of_file.get(f)
    if me not in feed:
        continue
    kind = platform_of_file[f]
    server = f.rsplit("_", 1)[1] if kind == "mastodon" else None
    for line in open(fn, encoding="utf-8"):
        p = json.loads(line)
        others = set()
        if p["repost"] and p.get("original_author"):
            a = p["original_author"].lower()
            if kind == "mastodon" and "@" not in a:
                a = f"{a}@{server}"
            others.add(handle_owner.get(a))
        elif not p["repost"]:
            parent = (details.get(p.get("uri") or "") or {}).get("reply_to")
            if parent:
                others.add(did_owner.get(parent.split("/")[2]))
            for m in MENTION.finditer(p.get("text") or ""):
                a = m.group(1).lower().rstrip(".")
                if a in handle_owner:
                    others.add(handle_owner[a])
                elif kind == "mastodon" and "@" not in a:
                    if f"{a}@{server}" in handle_owner:
                        others.add(handle_owner[f"{a}@{server}"])
                    elif len(user_owner.get(a, ())) == 1:
                        others.add(next(iter(user_owner[a])))
        for o in others - {None, me}:
            pair[tuple(sorted((me, o)))] += 1
coauthors = set()
for a, b, n in json.load(open(os.path.join(data_dir, "edges.json"), encoding="utf-8")):
    if a in canon and b in canon and canon[a] != canon[b]:
        coauthors.add(tuple(sorted((canon[a], canon[b]))))
edges_out = [dict(a=a, b=b, w=n, co=(a, b) in coauthors) for (a, b), n in pair.items() if n >= 2]
in_net = {x for e in edges_out for x in (e["a"], e["b"])}
meta_by_person = collections.Counter()
for f, n in poster.items():
    meta_by_person[owner_of_file[f]] += n
platforms_of = collections.defaultdict(set)
for f, pid in owner_of_file.items():
    platforms_of[pid].add(platform_of_file[f])
nodes_out = [dict(id=pid, n=people[pid]["n"], k=people[pid]["k"], posts=meta_by_person[pid], pl=sorted(platforms_of[pid]),
                  links=[account_link(e["kind"], e["account"]) for e in sorted(every[pid], key=lambda e: e["kind"])
                         if e["account"].lower() in {v["account"].lower() for v in final.get(pid, {}).values()}])
             for pid in sorted(in_net)]

# ---------------------------------------------------------------- rising and falling on social media
def month_add(m, k):
    y, mo = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mo // 12}-{mo % 12 + 1:02d}"
last_complete = month_add(max(month_total), -1)   # the month of download is not complete
B1, B0 = last_complete, month_add(last_complete, -23)
A1, A0 = month_add(B0, -1), month_add(B0, -24)
per = collections.defaultdict(lambda: {"A": collections.Counter(), "B": collections.Counter()})   # person -> period -> counts
for h in hits:
    m = h["date"][:7]
    p = "A" if A0 <= m <= A1 else "B" if B0 <= m <= B1 else None
    if not p:
        continue
    c = per[owner_of_file[h["account"]]][p]
    c["*"] += 1
    for t in h["terms"]:
        c["t:" + t] += 1
    for th in {THEME_OF[t] for t in h["terms"]}:
        c["h:" + th] += 1
persons = sorted(per)
def ratio(sample, key):
    a = sum(per[x]["A"][key] for x in sample); b = sum(per[x]["B"][key] for x in sample)
    ta = sum(per[x]["A"]["*"] for x in sample); tb = sum(per[x]["B"]["*"] for x in sample)
    if not (a or b) or not (ta and tb):
        return None
    if not a:
        return MAX_RATIO   # only in the last two years: counted as a very large rise, not skipped
    if not b:
        return 1 / MAX_RATIO
    return min(MAX_RATIO, max(1 / MAX_RATIO, (b / tb) / (a / ta)))
MAX_RATIO = 100
rng = random.Random(1)
boots = [[rng.choice(persons) for _ in persons] for _ in range(1000)]
def summary(key, name, theme):
    a = sum(per[x]["A"][key] for x in persons); b = sum(per[x]["B"][key] for x in persons)
    pa = sum(1 for x in persons if per[x]["A"][key]); pb = sum(1 for x in persons if per[x]["B"][key])
    both = sum(1 for x in persons if per[x]["A"][key] or per[x]["B"][key])
    r = ratio(persons, key)
    if r is None or not a or not b or a + b < 30 or both < 5:
        return None
    # a resample without anyone who used the term in one period counts as an extreme ratio (it is not skipped),
    # so that a term carried by one or two people gets a wide interval
    rs = sorted(x for x in (ratio(bs, key) for bs in boots) if x is not None)
    lo, hi = rs[int(0.025 * len(rs))], rs[int(0.975 * len(rs)) - 1]
    return dict(name=name, theme=theme, a=a, b=b, people_a=pa, people_b=pb, ratio=round(r, 3), lo=round(lo, 3),
                hi=round(hi, 3), status="rising" if lo > 1 else "declining" if hi < 1 else "no clear change")
rising = dict(periods=[A0, A1, B0, B1],
              posts=[sum(per[x]["A"]["*"] for x in persons), sum(per[x]["B"]["*"] for x in persons)],
              themes=[x for x in (summary("h:" + th, th, th) for th in THEMES) if x],
              terms=[x for x in (summary("t:" + t, t, THEME_OF[t]) for th in THEMES for t in THEMES[th]) if x])

out = dict(
    n_accounts=len(owner_of_file), n_people=len(set(owner_of_file.values())), n_feed=len(feed),
    n_own_posts=sum(month_total.values()), n_meta_posts=n_meta, n_meta_people=len({owner_of_file[h["account"]] for h in hits}),
    n_papers=n_papers, first_month=min(month_total), last_month=max(month_total),
    themes=themes_out, months={k: dict(v) for k, v in month_theme.items()}, month_total=dict(month_total),
    months_by={pl: {th: dict(c) for th, c in v.items()} for pl, v in month_theme_pl.items()},
    month_total_by={pl: dict(c) for pl, c in month_total_pl.items()},
    rising=rising, peaks=peaks_out, clouds=clouds, links=links_out, shared_papers=shared_papers, top=top,
    network=dict(nodes=nodes_out, edges=edges_out))
with open(os.path.join(data_dir, "socials.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print(f"people {out['n_people']} | metascience posts {n_meta} by {out['n_meta_people']} people | peaks {len(peaks_out)} | "
      f"links {len(links_out)} | shared site papers {len(shared_papers)} | network: {len(nodes_out)} people, "
      f"{len(edges_out)} pairs ({sum(e['co'] for e in edges_out)} also coauthors)")
