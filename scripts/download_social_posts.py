"""Download all public posts of the confirmed Bluesky and Mastodon accounts (private research data, never published).

Usage: python -I download_social_posts.py <social_final_all.json> <out folder>
Input: social_final_all.json from confirm_social_accounts.py (every confirmed account, also older accounts of the
same person), or social_final.json (only the newest account per platform).
Output: one file per account, <out folder>/<bluesky|mastodon>_<account>.jsonl, one post per line with: person, date,
text, whether it is a reply, whether it is a repost/boost of someone else's post (then also the original author),
the post address, language and the counts of likes, reposts and replies. Accounts already downloaded are skipped, so
a later run fetches only new accounts. A file is written under a temporary name and renamed when complete.

Bluesky: app.bsky.feed.getAuthorFeed on the public server (posts, replies and reposts; 100 per request).
Mastodon: /api/v1/accounts/<id>/statuses on the account's own server (40 per request, at most one request per second
per server).
"""
import sys, os, json, re, time, collections, threading, html
import requests

sys.stdout.reconfigure(encoding="utf-8")
final_path, out_dir = sys.argv[1:3]
os.makedirs(out_dir, exist_ok=True)
UA = {"User-Agent": "metascience-landscape-script"}
final = json.load(open(final_path, encoding="utf-8"))

def plain(h):
    """Mastodon post HTML to text: line breaks and paragraph ends become new lines, other tags are removed"""
    h = re.sub(r"<br\s*/?>|</p>", "\n", h or "")
    return html.unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", h))).strip()
def fetch(url, params):
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(30 * (attempt + 1)); continue
            if not r.ok:
                return None
            return r.json()
        except (requests.RequestException, ValueError):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"kept failing: {url}")
def path_for(kind, acct):
    return os.path.join(out_dir, f"{kind}_{re.sub(r'[^A-Za-z0-9._-]+', '_', acct.lstrip('@'))}.jsonl")

def bluesky_posts(pid, acct):
    cursor, n = None, 0
    while True:
        j = fetch("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
                  {"actor": acct, "limit": 100, "filter": "posts_with_replies", **({"cursor": cursor} if cursor else {})})
        if j is None:
            return
        for it in j.get("feed", []):
            p, rec = it["post"], it["post"].get("record", {})
            repost = it.get("reason", {}).get("$type", "").endswith("reasonRepost")
            yield dict(person=pid, date=(it["reason"].get("indexedAt") if repost else rec.get("createdAt")),
                       text=rec.get("text", ""), reply="reply" in rec, repost=repost,
                       original_author=p["author"]["handle"] if repost else None, uri=p.get("uri"),
                       lang=(rec.get("langs") or [None])[0], likes=p.get("likeCount"), reposts=p.get("repostCount"),
                       replies=p.get("replyCount"))
        cursor = j.get("cursor")
        if not cursor or not j.get("feed"):
            return
        time.sleep(0.2)

def mastodon_posts(pid, acct):
    user, server = acct.lstrip("@").split("@", 1)
    a = fetch(f"https://{server}/api/v1/accounts/lookup", {"acct": user})
    if a is None:
        return
    max_id = None
    while True:
        time.sleep(1.05)
        j = fetch(f"https://{server}/api/v1/accounts/{a['id']}/statuses",
                  {"limit": 40, **({"max_id": max_id} if max_id else {})})
        if not j:
            return
        for st in j:
            b = st.get("reblog")
            src = b or st
            yield dict(person=pid, date=st.get("created_at"), text=plain(src.get("content")),
                       reply=st.get("in_reply_to_id") is not None, repost=b is not None,
                       original_author=b["account"]["acct"] if b else None, uri=src.get("url") or src.get("uri"),
                       lang=src.get("language"), likes=src.get("favourites_count"),
                       reposts=src.get("reblogs_count"), replies=src.get("replies_count"))
        max_id = j[-1]["id"]

groups = collections.defaultdict(list)
for pid, accs in final.items():
    # social_final.json: {kind: {account, ...}}; social_final_all.json: [{kind, account, ...}, ...]
    for kind, acct in ((a["kind"], a["account"]) for a in accs) if isinstance(accs, list) else \
            ((k, v["account"]) for k, v in accs.items()):
        if not os.path.exists(path_for(kind, acct)):
            groups["bluesky" if kind == "bluesky" else acct.rsplit("@", 1)[1]].append((pid, kind, acct))
lock = threading.Lock()
done = collections.Counter()
def work(items):
    for pid, kind, acct in items:
        target = path_for(kind, acct)
        try:
            n = 0
            with open(target + ".part", "w", encoding="utf-8") as f:
                for post in (bluesky_posts if kind == "bluesky" else mastodon_posts)(pid, acct):
                    f.write(json.dumps(post, ensure_ascii=False) + "\n"); n += 1
            os.replace(target + ".part", target)
            with lock:
                done["accounts"] += 1; done["posts"] += n
                if done["accounts"] % 50 == 0:
                    print(f"  accounts done: {done['accounts']}, posts: {done['posts']}", flush=True)
        except RuntimeError as e:
            with lock:
                done["failed"] += 1
            print("  failed:", acct, str(e)[:100], flush=True)
print(f"accounts to download: {sum(map(len, groups.values()))} ({len(groups) - ('bluesky' in groups)} Mastodon servers)",
      flush=True)
ts = [threading.Thread(target=work, args=(items,)) for items in groups.values()]
for t in ts: t.start()
for t in ts: t.join()
print(f"accounts done: {done['accounts']}, posts: {done['posts']}, failed: {done['failed']}")
