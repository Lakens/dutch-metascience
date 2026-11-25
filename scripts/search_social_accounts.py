"""Search Bluesky and Mastodon by name for the people on the site (candidates only; they are confirmed afterwards).

Usage: python -I search_social_accounts.py <site data folder> <out.json>
Output (private, not published): per person, the accounts whose display name contains the person's first and last
name, with their profile text, so that confirm_social_accounts.py can accept only accounts whose profile names the
person's ORCID or institution, and a Claude reviewer can judge the rest.

Bluesky: the public search (public.api.bsky.app, app.bsky.actor.searchActors), 10 results per name.
Mastodon has no central search; each server searches the accounts it knows (its own and those its users follow). We
search three large servers that know many researchers: mastodon.social, fediscience.org and akademienl.social (Dutch
academics), 10 results per name, at most one request per second per server (their limit is 300 per 5 minutes).
The query is the first name plus the last word of the name; a result counts when its display name contains both
(accents and case ignored). Earlier results are kept, so an interrupted run continues where it stopped.
"""
import sys, os, json, time, re, unicodedata, threading
import requests

sys.stdout.reconfigure(encoding="utf-8")
data_dir, out_path = sys.argv[1:3]
UA = {"User-Agent": "dutch-metascience-script"}
people = json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))
SERVERS = {"bluesky": 0.25, "mastodon.social": 1.05, "fediscience.org": 1.05, "akademienl.social": 1.05}

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", s).strip()
def name_parts(n):
    toks = [t for t in norm(n).split() if len(t) > 1]   # initials dropped
    return (toks[0], toks[-1]) if len(toks) >= 2 else None

out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
lock = threading.Lock()

def search(service, first, last):
    q = f"{first} {last}"
    for attempt in range(6):
        try:
            if service == "bluesky":
                r = requests.get("https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors",
                                 params={"q": q, "limit": 10}, headers=UA, timeout=30)
            else:
                r = requests.get(f"https://{service}/api/v2/search",
                                 params={"q": q, "type": "accounts", "limit": 10}, headers=UA, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(30 * (attempt + 1)); continue
            r.raise_for_status()
            j = r.json()
            break
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
    else:
        return None   # this name is tried again in a next run
    res = []
    if service == "bluesky":
        for a in j.get("actors", []):
            dn = norm(a.get("displayName") or "")
            if first in dn.split() and last in dn.split():
                res.append(dict(account=a["handle"], name=a.get("displayName") or "", text=a.get("description") or "",
                                created=a.get("createdAt")))
    else:
        for a in j.get("accounts", []):
            dn = norm(a.get("display_name") or "")
            if first in dn.split() and last in dn.split():
                acct = a["acct"] if "@" in a["acct"] else a["acct"] + "@" + service
                fields = " ".join(f.get("name", "") + " " + f.get("value", "") for f in a.get("fields", []))
                res.append(dict(account="@" + acct, name=a.get("display_name") or "",
                                text=re.sub(r"<[^>]+>", " ", (a.get("note") or "") + " " + fields),
                                created=a.get("created_at"), last=a.get("last_status_at"),
                                moved=(a.get("moved") or {}).get("acct")))
    return res

def worker(service, pause):
    todo = [p for p in people if name_parts(p["n"]) and service not in out.get(p["id"], {})]
    for n, p in enumerate(todo, 1):
        first, last = name_parts(p["n"])
        res = search(service, first, last)
        if res is not None:
            with lock:
                out.setdefault(p["id"], {})[service] = res
        time.sleep(pause)
        if n % 500 == 0:
            with lock:
                json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"  {service}: {n}/{len(todo)}", flush=True)

threads = [threading.Thread(target=worker, args=(s, w)) for s, w in SERVERS.items()]
for t in threads: t.start()
for t in threads: t.join()
json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
for s in SERVERS:
    print(f"{s}: people searched {sum(1 for v in out.values() if s in v)} | with a name match "
          f"{sum(1 for v in out.values() if v.get(s))}")
