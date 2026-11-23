"""Decide which Bluesky and Mastodon accounts belong to the people on the site; one account per platform per person.

Usage: python -I confirm_social_accounts.py <site data folder> <social_accounts.json> <social_search.json>
           <review_verdicts.tsv> <out.json> <activity.json>
Input: accounts listed by the people themselves (find_social_accounts.py: ORCID and Wikidata) and name matches from
the search (search_social_accounts.py). <activity.json> keeps the number of posts and the last 5 posts of each
account found by name (read once, then reused). When <review_verdicts.tsv> does not exist yet, the script writes the
name matches that need a reviewer to <review_verdicts.tsv>.input.jsonl and stops.

Accounts found by name are considered only when they exist and have at least one post. Which accounts are kept (all
private until published on purpose):
 1. listed in the person's ORCID record or in Wikidata;
 2. found by name, the only such account of the person on that platform, and the profile text or account address
    names the person's ORCID, their main institution (its name without generic words, or a common short form) or the
    city of that institution, or the account is on a Mastodon server for scientists (SCIENCE_SERVERS);
 3. found by name without such evidence, and judged "yes" by a Claude reviewer who compared the profile text and the
    last 5 posts with the person's institution and paper titles. Names that match several accounts on one platform
    also go to the reviewer;
 4. added by hand in social_added_by_hand.tsv (next to <review_verdicts.tsv>), for accounts the name search cannot
    find, such as an account without a display name, and for one person split into several records that share no
    ORCID or institution (the account is then added to each record).
Then, per person and platform:
 - automatic copies: a Bluesky account that copies a Mastodon account (handle ending in .ap.brid.gy) is replaced by
   that Mastodon account; a Mastodon account that copies a Bluesky account (server bsky.brid.gy) is replaced by that
   Bluesky account;
 - a Mastodon account that has moved is replaced by the account it moved to;
 - the newest version: the account with the most recent post (Bluesky: latest post in its feed; Mastodon: the
   server's date of the last post); accounts that no longer exist are dropped.
Finally, an account given to several people on the site is kept for all of them only when they share an ORCID or an
institution (one person split into several records); otherwise see the comment at the end of the script.
"""
import sys, os, json, re, time, unicodedata, csv, collections, threading
import requests

sys.stdout.reconfigure(encoding="utf-8")
data_dir, listed_path, search_path, verdict_path, out_path, activity_path = sys.argv[1:7]
UA = {"User-Agent": "metascience-landscape-script"}
people = {p["id"]: p for p in json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))}
insts = {i["id"]: i for i in json.load(open(os.path.join(data_dir, "institutions.json"), encoding="utf-8"))["list"]}
papers = json.load(open(os.path.join(data_dir, "papers.json"), encoding="utf-8"))
titles = collections.defaultdict(list)
for p in sorted(papers, key=lambda p: -(p["y"] or 0)):
    for a in p["p"]:
        titles[a].append(p["t"])

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9/]+", " ", s).strip()
GENERIC = set("university universiteit of the and for medical center centre centers umc applied sciences hogeschool "
              "institute instituut technology research netherlands royal academy national foundation stichting "
              "school hospital academic universitair medisch centrum vrije health care clinical social science "
              "public life international business management economics arts central".split())
SHORT = {"Eindhoven University of Technology": ["tu/e", "tue"], "Delft University of Technology": ["tu delft"],
         "University of Amsterdam": ["uva"], "Vrije Universiteit Amsterdam": ["vu amsterdam", "vrije universiteit"],
         "Amsterdam University Medical Centers": ["amsterdam umc", "amsterdamumc"],
         "Erasmus University Rotterdam": ["erasmus", "eur"], "Erasmus MC": ["erasmus"],
         "Leiden University Medical Center": ["lumc"], "University Medical Center Utrecht": ["umc utrecht", "umcu"],
         "University Medical Center Groningen": ["umcg"], "Radboud University Medical Center": ["radboudumc"],
         "Maastricht University Medical Centre": ["mumc"], "Utrecht University": ["uu"]}
def evidence_words(pid):
    out = set()
    for iid in people[pid].get("ins") or []:
        i = insts.get(iid)
        if not i:
            continue
        out |= {w for w in norm(i["n"]).split() if w not in GENERIC and len(w) > 3}
        if i.get("city"):
            out.add(norm(i["city"]))
        out |= set(SHORT.get(i["n"], []))
    return out
# Mastodon servers for scientists and academics: an account there with the person's name counts as evidence
SCIENCE_SERVERS = set("fediscience.org social.edu.nl mathstodon.xyz sciences.social akademienl.social mstdn.science "
                      "genomic.social scicomm.xyz sigmoid.social scholar.social neuromatch.social social.cwts.nl "
                      "ecoevo.social openbiblio.social archaeo.social social.sigsoft.org recsys.social".split())
def has_evidence(pid, acc):
    text = " " + norm(acc.get("text", "") + " " + acc["account"].replace(".", " ")) + " "
    if people[pid].get("o") and people[pid]["o"] in (acc.get("text") or ""):
        return "ORCID in profile"
    if acc["account"].startswith("@") and acc["account"].rsplit("@", 1)[1].lower() in SCIENCE_SERVERS:
        return "account on the science server " + acc["account"].rsplit("@", 1)[1]
    for w in evidence_words(pid):
        if f" {w} " in text:
            return f"profile names '{w}'"
    return None

kind_of = lambda acc: "mastodon" if acc.startswith("@") else "bluesky"
listed = json.load(open(listed_path, encoding="utf-8"))
search = json.load(open(search_path, encoding="utf-8"))

# ---------------------------------------------------------------- activity of the accounts found by name
# Per account: does it exist, how many posts, and the text of its last 5 posts (for the reviewer). Kept in
# <activity.json>, so a second run asks only for accounts not seen before. Accounts without any post, accounts that
# no longer exist and accounts whose server does not answer are left out.
activity = json.load(open(activity_path, encoding="utf-8")) if os.path.exists(activity_path) else {}
activity = {a: v for a, v in activity.items() if "recent" in v}   # older entries without post texts are fetched again
def plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).replace("&amp;", "&").replace("&#39;", "'").strip()
def fetch(url, params):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            if r.status_code == 429:
                time.sleep(30); continue
            return r
        except requests.RequestException:
            time.sleep(3)
    return None
def bluesky_activity(acct):
    r = fetch("https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile", {"actor": acct})
    if r is None or not r.ok:
        return dict(exists=False, posts=0, last=None, recent=[], error=None if r is not None else "no answer")
    n = r.json().get("postsCount", 0)
    recent, last = [], None
    if n:
        f = fetch("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed", {"actor": acct, "limit": 5})
        for it in (f.json().get("feed", []) if f is not None and f.ok else []):
            rec = it["post"].get("record", {})
            repost = it.get("reason", {}).get("$type", "").endswith("reasonRepost")
            last = max(last or "", it["post"].get("indexedAt", "")[:10])
            recent.append(("[repost] " if repost else "") + rec.get("createdAt", "")[:10] + ": " + rec.get("text", "")[:300])
    return dict(exists=True, posts=n, last=last, recent=recent, error=None)
def mastodon_activity(acct):
    user, server = acct.lstrip("@").split("@", 1)
    r = fetch(f"https://{server}/api/v1/accounts/lookup", {"acct": user})
    if r is None or (not r.ok and r.status_code not in (404, 410)):
        return dict(exists=False, posts=0, last=None, recent=[], error="no answer")
    if not r.ok:
        return dict(exists=False, posts=0, last=None, recent=[], error=None)
    j = r.json()
    recent = []
    if j.get("statuses_count"):
        time.sleep(1.05)
        s = fetch(f"https://{server}/api/v1/accounts/{j['id']}/statuses", {"limit": 5})
        for st in (s.json() if s is not None and s.ok else []):
            boost = st.get("reblog")
            recent.append(("[boost] " if boost else "") + st.get("created_at", "")[:10] + ": " +
                          plain((boost or st).get("content"))[:300])
    return dict(exists=True, posts=j.get("statuses_count", 0), last=j.get("last_status_at"), recent=recent,
                moved=(j.get("moved") or {}).get("acct"), error=None)
todo = sorted({r["account"] for v in search.values() for res in v.values() for r in res} - set(activity))
if todo:
    print(f"reading the activity of {len(todo)} accounts", flush=True)
    lock = threading.Lock()
    def work(items, fn, pause):
        for a in items:
            try:
                v = fn(a)
            except ValueError:   # the server sent something other than JSON
                v = dict(exists=False, posts=0, last=None, recent=[], error="no answer")
            with lock:
                activity[a] = v
            time.sleep(pause)
    groups = collections.defaultdict(list)
    for a in todo:
        groups["bluesky" if kind_of(a) == "bluesky" else a.rsplit("@", 1)[1]].append(a)
    ts = [threading.Thread(target=work, args=(items, bluesky_activity if g == "bluesky" else mastodon_activity,
                                              0.3 if g == "bluesky" else 1.05)) for g, items in groups.items()]
    for t in ts: t.start()
    for t in ts: t.join()
    json.dump(activity, open(activity_path, "w", encoding="utf-8"), ensure_ascii=False)
active_acct = lambda a: activity.get(a, {}).get("exists") and activity[a]["posts"] > 0 and not activity[a].get("error")
print("accounts found by name: " + ", ".join(f"{k} {n}" for k, n in collections.Counter(
    "no answer from server" if v.get("error") else "no longer exists" if not v["exists"] else
    "no posts" if not v["posts"] else "with posts" for v in activity.values()).items()))

# candidates per person: listed accounts, and search matches (Mastodon results of three servers joined)
accepted = collections.defaultdict(dict)    # pid -> account (lower) -> reason
review = []
for pid, accs in listed.items():
    for a in accs:
        acct = a["account"] if a["kind"] == "bluesky" else a["account"]
        accepted[pid][acct.lower()] = "listed in " + a["source"]
for pid, by_service in search.items():
    if pid not in people:
        continue
    cands = {}
    for service, res in by_service.items():
        for r in res:
            if active_acct(r["account"]):
                cands.setdefault(r["account"].lower(), r)
    for kind in ("bluesky", "mastodon"):
        ks = [k for k in cands if kind_of(k) == kind and k not in accepted.get(pid, {})]
        if not ks:
            continue
        sure = {k: has_evidence(pid, cands[k]) for k in ks}
        if len(ks) == 1 and sure[ks[0]]:
            accepted[pid][ks[0]] = "found by name; " + sure[ks[0]]
            continue
        for k in ks:   # without evidence, or several candidates: the reviewer decides
            review.append(dict(person=pid, name=people[pid]["n"], orcid=people[pid].get("o") or "",
                               institution=", ".join(insts[i]["n"] for i in people[pid].get("ins") or [] if i in insts),
                               paper_titles=titles[pid][:6], account=cands[k]["account"],
                               display_name=cands[k]["name"], profile_text=re.sub(r"\s+", " ", cands[k]["text"])[:600],
                               number_of_posts=activity[cands[k]["account"]]["posts"],
                               last_5_posts=activity[cands[k]["account"]]["recent"],
                               automatic_evidence=sure[k] or "", other_candidates_same_platform=len(ks) - 1))
print(f"people with a listed account: {len(listed)} | with an account accepted by evidence: "
      f"{sum(1 for v in accepted.values() if any(r.startswith('found') for r in v.values()))} | "
      f"name matches for the reviewer: {len(review)} (people: {len({r['person'] for r in review})})")

if not os.path.exists(verdict_path):
    with open(verdict_path + ".input.jsonl", "w", encoding="utf-8") as f:
        for i, r in enumerate(review, 1):
            f.write(json.dumps(dict(n=i, **r), ensure_ascii=False) + "\n")
    raise SystemExit(f"wrote {len(review)} name matches for the reviewer to {verdict_path}.input.jsonl")

for r in csv.DictReader(open(verdict_path, encoding="utf-8"), delimiter="\t"):
    if r["verdict"].strip().lower() == "yes":
        accepted[r["person"].strip()][r["account"].strip().lower()] = "found by name; reviewer: " + r["reason"].strip()
# accounts added by hand (the name search can miss an account without a display name): social_added_by_hand.tsv in
# the same folder as <review_verdicts.tsv>, columns person, account, reason
hand_path = os.path.join(os.path.dirname(os.path.abspath(verdict_path)), "social_added_by_hand.tsv")
if os.path.exists(hand_path):
    for r in csv.DictReader(open(hand_path, encoding="utf-8"), delimiter="\t"):
        accepted[r["person"].strip()][r["account"].strip().lower()] = "added by hand: " + r["reason"].strip()

# ---------------------------------------------------------------- copies, moves, newest version
s = requests.Session()
def get(url, params):
    for attempt in range(4):
        try:
            r = s.get(url, params=params, headers=UA, timeout=30)
            if r.status_code in (400, 404, 410):
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(20 * (attempt + 1)); continue
            return r.json() if r.ok else None
        except (requests.RequestException, ValueError):
            time.sleep(5 * (attempt + 1))
    return None
def info(acct):
    """(kind, canonical account, date of the last post or None, exists) after following copies and moves"""
    if kind_of(acct) == "bluesky":
        if acct.endswith(".ap.brid.gy"):   # copy of a Mastodon account: user.server.ap.brid.gy
            user, server = acct[:-len(".ap.brid.gy")].split(".", 1)
            return info(f"@{user}@{server}")
        j = get("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed", {"actor": acct, "limit": 1})
        if j is None:
            return ("bluesky", acct, None, False)
        feed = j.get("feed", [])
        return ("bluesky", acct, feed[0]["post"]["indexedAt"][:10] if feed else None, True)
    user, server = acct.lstrip("@").split("@", 1)
    if server == "bsky.brid.gy":   # copy of a Bluesky account
        return info(user)
    j = get(f"https://{server}/api/v1/accounts/lookup", {"acct": user})
    if j is None:
        return ("mastodon", acct, None, False)
    if j.get("moved"):
        m = j["moved"]["acct"]
        return info("@" + (m if "@" in m else m + "@" + server))
    return ("mastodon", acct, j.get("last_status_at"), True)

final, every, dropped = {}, {}, collections.Counter()
for pid, accs in accepted.items():
    best = {}
    for acct, why in accs.items():
        kind, canon, last, exists = info(acct)
        time.sleep(0.2)
        if not exists:
            dropped["no longer exists"] += 1; continue
        if not last:
            dropped["no posts"] += 1; continue
        if not any(e["account"].lower() == canon.lower() for e in every.get(pid, [])):
            every.setdefault(pid, []).append(dict(kind=kind, account=canon, last_post=last, reason=why))
        if kind in best and best[kind]["account"].lower() == canon.lower():
            continue
        cand = dict(account=canon, last_post=last, reason=why + ("" if canon.lower() == acct else f" (via {acct})"))
        if kind not in best or (last or "") > (best[kind]["last_post"] or ""):
            if kind in best:
                dropped["older account of the same person"] += 1
            best[kind] = cand
        else:
            dropped["older account of the same person"] += 1
    if best:
        final[pid] = best
# One account, several people on the site. Often one person split into several records (same ORCID, or same
# institution): then all keep it. Otherwise the account stays with the person who listed it in ORCID or Wikidata and
# is removed from the others (an account added by hand counts as listed); if nobody listed it, it is removed from all of them and written to
# <out>_conflicts.json for a decision by hand.
owners = collections.defaultdict(list)
for pid, lst in every.items():
    for e in lst:
        owners[e["account"].lower()].append(pid)
conflicts = []
for acct, pids in owners.items():
    if len(pids) < 2:
        continue
    orcids = {people[p].get("o") for p in pids}
    inst = [set(people[p].get("ins") or []) for p in pids]
    if (len(orcids) == 1 and None not in orcids and "" not in orcids) or set.intersection(*inst):
        continue
    listed_by = [p for p in pids if any(e["account"].lower() == acct and e["reason"].startswith(("listed", "added by hand"))
                                        for e in every[p])]
    losers = [p for p in pids if p not in listed_by] if listed_by else pids
    if not listed_by:
        conflicts.append(dict(account=acct, people=[dict(person=p, name=people[p]["n"], orcid=people[p].get("o"),
                                                         reason=next(e["reason"] for e in every[p]
                                                                     if e["account"].lower() == acct)) for p in pids]))
    for p in losers:
        every[p] = [e for e in every[p] if e["account"].lower() != acct]
        final[p] = {k: v for k, v in final.get(p, {}).items() if v["account"].lower() != acct}
        dropped["account of another person with the same name"] += 1
every = {p: v for p, v in every.items() if v}
final = {p: v for p, v in final.items() if v}
json.dump(conflicts, open(re.sub(r"\.json$", "", out_path) + "_conflicts.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(final, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# every confirmed account, also older ones of the same person (for downloading all old posts)
json.dump(every, open(re.sub(r"\.json$", "", out_path) + "_all.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
active = {k for k, p in people.items() if p["k"] >= 3 and (p["y1"] or 0) >= 2024}
print(f"people with an account: {len(final)} (active researchers: {sum(k in active for k in final)} of {len(active)}) | "
      f"Bluesky: {sum('bluesky' in v for v in final.values())} | Mastodon: {sum('mastodon' in v for v in final.values())}"
      f" | left out: {dict(dropped)}")
