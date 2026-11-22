"""Input for the reviewers who judge whether a person with a confirmed social media account works in the Netherlands now.

Usage: python -I prepare_location_review.py <site data folder> <social_final.json> <posts folder> <profiles.json>
           <out.jsonl>
Only people who work in the Netherlands now are counted on the Socials page (build_socials.py). This script collects
per person (records that share an account count as one person): the name, the institutions and years of their papers
on the site, their most recent paper titles, the current profile text of each of their accounts, and their five most
recent own posts. Profiles are read from the public Bluesky and Mastodon servers and kept in <profiles.json>, so a
second run asks only for new accounts. The reviewers follow location_review_instructions.md.
Private research data, never published.
"""
import sys, os, re, json, glob, time, collections, threading, html
import requests

sys.stdout.reconfigure(encoding="utf-8")
data_dir, final_path, posts_dir, profiles_path, out_path = sys.argv[1:6]
UA = {"User-Agent": "metascience-landscape-script"}
people = {p["id"]: p for p in json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))}
insts = {i["id"]: i["n"] for i in json.load(open(os.path.join(data_dir, "institutions.json"), encoding="utf-8"))["list"]}
papers = json.load(open(os.path.join(data_dir, "papers.json"), encoding="utf-8"))
every = json.load(open(re.sub(r"\.json$", "", final_path) + "_all.json", encoding="utf-8"))

# ---------------------------------------------------------------- one person = all records that share an account
file_of = lambda kind, acct: f"{kind}_{re.sub(r'[^A-Za-z0-9._-]+', '_', acct.lstrip('@'))}"   # as in download_social_posts.py
parent = {p: p for p in every}
def find(p):
    while parent[p] != p:
        parent[p] = parent[parent[p]]; p = parent[p]
    return p
first = {}
for pid, lst in every.items():
    for e in lst:
        f = file_of(e["kind"], e["account"])
        if f in first:
            parent[find(pid)] = find(first[f])
        else:
            first[f] = pid
groups = collections.defaultdict(list)
for pid in every:
    groups[find(pid)].append(pid)

# ---------------------------------------------------------------- current profiles
profiles = json.load(open(profiles_path, encoding="utf-8")) if os.path.exists(profiles_path) else {}
accts = sorted({(e["kind"], e["account"]) for lst in every.values() for e in lst if e["account"] not in profiles})
def plain(h):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or ""))).strip()
def fetch(url, params):
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            if r.status_code == 429:
                time.sleep(30); continue
            return r.json() if r.ok else None
        except (requests.RequestException, ValueError):
            time.sleep(3)
    return None
bs = [a for k, a in accts if k == "bluesky"]
for i in range(0, len(bs), 25):
    j = fetch("https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles", [("actors", a) for a in bs[i:i + 25]]) or {}
    got = {p["handle"].lower(): p for p in j.get("profiles", [])}
    for a in bs[i:i + 25]:
        p = got.get(a.lower(), {})
        profiles[a] = dict(name=p.get("displayName") or "", text=p.get("description") or "")
    time.sleep(0.3)
lock = threading.Lock()
by_server = collections.defaultdict(list)
for k, a in accts:
    if k == "mastodon":
        by_server[a.rsplit("@", 1)[1]].append(a)
def work(server, items):
    for a in items:
        j = fetch(f"https://{server}/api/v1/accounts/lookup", {"acct": a.lstrip("@").split("@")[0]}) or {}
        fields = " | ".join(f"{f.get('name', '')}: {plain(f.get('value'))}" for f in j.get("fields", []))
        with lock:
            profiles[a] = dict(name=j.get("display_name") or "", text=(plain(j.get("note")) + (" | " + fields if fields else "")).strip())
        time.sleep(1.05)
ts = [threading.Thread(target=work, args=kv) for kv in by_server.items()]
for t in ts: t.start()
for t in ts: t.join()
json.dump(profiles, open(profiles_path, "w", encoding="utf-8"), ensure_ascii=False)

# ---------------------------------------------------------------- recent own posts per account
recent = {}
for fn in glob.glob(os.path.join(posts_dir, "*.jsonl")):
    own = [p for p in map(json.loads, open(fn, encoding="utf-8")) if not p["repost"] and p.get("date")]
    own.sort(key=lambda p: p["date"], reverse=True)
    recent[os.path.basename(fn)[:-6]] = [p["date"][:10] + ": " + re.sub(r"\s+", " ", p["text"])[:250] for p in own[:5]]

titles = collections.defaultdict(list)
for p in sorted(papers, key=lambda p: -(p["y"] or 0)):
    for a in p["p"]:
        titles[a].append(f"{p['y']}: {p['t'][:120]}")
n = 0
with open(out_path, "w", encoding="utf-8") as out:
    for root, pids in sorted(groups.items()):
        pids = sorted(pids, key=lambda p: -people[p]["k"])
        accs = sorted({(e["kind"], e["account"]) for p in pids for e in every[p]})
        rec = dict(
            person=pids[0], records=pids, name=people[pids[0]]["n"],
            site_institutions=sorted({insts.get(i, "") for p in pids for i in (people[p].get("ins") or [])} - {""}),
            paper_years=f"{min(people[p]['y0'] or 9999 for p in pids)}-{max(people[p]['y1'] or 0 for p in pids)}",
            papers_on_site=sum(people[p]["k"] for p in pids),
            recent_paper_titles=sorted({t for p in pids for t in titles[p]}, reverse=True)[:4],
            accounts=[dict(platform=k, account=a, display_name=profiles.get(a, {}).get("name", ""),
                           profile=profiles.get(a, {}).get("text", "")[:700],
                           recent_posts=recent.get(file_of(k, a), [])) for k, a in accs])
        out.write(json.dumps(rec, ensure_ascii=False) + "\n"); n += 1
print(f"people: {n} | profiles read: {len(profiles)}")
