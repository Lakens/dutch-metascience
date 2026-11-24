"""Bluesky and Mastodon accounts that people on the site listed themselves: in their ORCID record or in Wikidata.

Usage: python -I find_social_accounts.py <site data folder> <out.json>
Input: <site data folder>/people.json (ORCIDs). Output (private, not published): <out.json> with, per person, the
accounts found and where they were found. Nothing is matched by name.

1. ORCID: the public API (pub.orcid.org, no key) gives each record's "researcher URLs" (websites and social links
   the researcher entered). Bluesky: links to bsky.app/profile/<handle> or a *.bsky.social address. Mastodon: links of
   the form https://<server>/@<name> or /users/<name>, on a server that answers as a Mastodon-compatible server
   (/api/v1/instance), which rules out other sites with /@ addresses (Medium, YouTube, TikTok, Threads).
2. Wikidata: items with an ORCID (P496) of a person on the site and a Bluesky handle (P12361) or Mastodon address
   (P4033), through the public query service.
"""
import sys, os, json, time, re, urllib.parse
import requests

sys.stdout.reconfigure(encoding="utf-8")
data_dir, out_path = sys.argv[1:3]
UA = {"User-Agent": "metascience-community-script"}
people = json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))
orcid_of = {p["id"]: p["o"] for p in people if p.get("o")}
s = requests.Session()

def get(url, **kw):
    for attempt in range(6):
        try:
            r = s.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=60, **kw)
            if r.status_code in (404, 409, 410):   # no record, or a locked or deprecated ORCID record
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            print("  retrying after error:", str(e)[:120], flush=True)
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"STOPPED: request kept failing: {url}")

found = {}   # person id -> list of {kind, account, source, url}
def add(pid, kind, account, source, url=""):
    lst = found.setdefault(pid, [])
    if not any(a["kind"] == kind and a["account"].lower() == account.lower() for a in lst):
        lst.append(dict(kind=kind, account=account, source=source, url=url))

# ---------------------------------------------------------------- 1. ORCID researcher URLs
NOT_MASTODON = {"medium.com", "www.medium.com", "youtube.com", "www.youtube.com", "tiktok.com", "www.tiktok.com",
                "threads.net", "www.threads.net", "bsky.app", "substack.com", "linktr.ee"}
mastodon_cand = []   # (pid, host, name, url)
n_with_urls = 0
for n, (pid, orcid) in enumerate(sorted(orcid_of.items()), 1):
    r = get(f"https://pub.orcid.org/v3.0/{orcid}/researcher-urls", headers={"Accept": "application/json"})
    urls = [u["url"]["value"].strip() for u in ((r.json() if r else {}) or {}).get("researcher-url", []) if u.get("url")]
    n_with_urls += bool(urls)
    for u in urls:
        p = urllib.parse.urlparse(u if "://" in u else "https://" + u)
        host, path = p.netloc.lower(), p.path
        m = re.match(r"^/profile/([^/?#]+)", path)
        if host in ("bsky.app", "www.bsky.app") and m:
            add(pid, "bluesky", m.group(1), "ORCID", u)
        elif host.endswith(".bsky.social"):
            add(pid, "bluesky", host, "ORCID", u)
        else:
            m = re.match(r"^/(?:@|users/)([A-Za-z0-9_.]+)/?$", path)
            if m and host and host not in NOT_MASTODON:
                mastodon_cand.append((pid, host, m.group(1), u))
    time.sleep(0.1)
    if n % 500 == 0:
        print(f"  ORCID records read: {n}/{len(orcid_of)}", flush=True)
print(f"ORCID records with any website or social link: {n_with_urls} of {len(orcid_of)}")

hosts = {}
for h in sorted({c[1] for c in mastodon_cand}):
    try:
        r = s.get(f"https://{h}/api/v1/instance", headers=UA, timeout=20)
        hosts[h] = r.ok and "uri" in r.json()
    except Exception:
        hosts[h] = False
for pid, h, name, u in mastodon_cand:
    if hosts.get(h):
        add(pid, "mastodon", f"@{name}@{h}", "ORCID", u)
print(f"possible Mastodon links: {len(mastodon_cand)}, on Mastodon-compatible servers: "
      f"{sum(1 for c in mastodon_cand if hosts.get(c[1]))} ({sum(hosts.values())} of {len(hosts)} servers)")

# ---------------------------------------------------------------- 2. Wikidata
pid_of_orcid = {o.upper(): pid for pid, o in orcid_of.items()}
orcids = sorted(pid_of_orcid)
for i in range(0, len(orcids), 200):
    values = " ".join(f'"{o}"' for o in orcids[i:i + 200])
    q = f"""SELECT ?orcid ?bsky ?masto WHERE {{ VALUES ?orcid {{ {values} }} ?item wdt:P496 ?orcid .
            OPTIONAL {{ ?item wdt:P12361 ?bsky }} OPTIONAL {{ ?item wdt:P4033 ?masto }}
            FILTER(BOUND(?bsky) || BOUND(?masto)) }}"""
    r = get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"})
    for b in r.json()["results"]["bindings"]:
        pid = pid_of_orcid[b["orcid"]["value"].upper()]
        if "bsky" in b:
            add(pid, "bluesky", b["bsky"]["value"], "Wikidata")
        if "masto" in b:
            v = b["masto"]["value"]
            add(pid, "mastodon", v if v.startswith("@") else "@" + v, "Wikidata")
    time.sleep(1)

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(found, f, ensure_ascii=False, indent=1)
kinds = lambda k: sum(1 for v in found.values() if any(a["kind"] == k for a in v))
print(f"people with a Bluesky account: {kinds('bluesky')} | with a Mastodon account: {kinds('mastodon')} | "
      f"with either: {len(found)}")
