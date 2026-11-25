"""Full link addresses (and the post replied to) for the Bluesky posts with a metascience term.

Usage: python -I fetch_bluesky_links.py <hits.jsonl> <out.json>
Bluesky shortens long links in the text of a post ("example.org/very/lo..."); the full address is stored with the
post (as a link inside the text, or as a link card). This script asks the public Bluesky server for the posts in
<hits.jsonl> (search_social_posts.py) that come from Bluesky, 25 per request (app.bsky.feed.getPosts), and keeps per
post: the full addresses of its links, and the post it replies to (if any). Posts that were deleted since the
download are missing from the answer and are left out. Earlier results in <out.json> are kept, so a second run asks
only for new posts. Private research data, never published.
"""
import sys, json, os, time
import requests

sys.stdout.reconfigure(encoding="utf-8")
hits_path, out_path = sys.argv[1:3]
UA = {"User-Agent": "dutch-metascience-script"}
out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
uris = sorted({h["uri"] for h in map(json.loads, open(hits_path, encoding="utf-8"))
               if h["account"].startswith("bluesky_") and h.get("uri", "").startswith("at://")} - set(out))
print(f"posts to read: {len(uris)}", flush=True)

def links_of(post):
    rec, found = post.get("record", {}), []
    for f in rec.get("facets", []) or []:
        for feat in f.get("features", []):
            if feat.get("$type") == "app.bsky.richtext.facet#link" and feat.get("uri"):
                found.append(feat["uri"])
    emb = rec.get("embed") or {}
    for e in (emb, emb.get("media") or {}):   # a link card, also when combined with a quote
        if e.get("$type") == "app.bsky.embed.external" and (e.get("external") or {}).get("uri"):
            found.append(e["external"]["uri"])
    return list(dict.fromkeys(found))

for i in range(0, len(uris), 25):
    batch = uris[i:i + 25]
    for attempt in range(5):
        try:
            r = requests.get("https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts",
                             params=[("uris", u) for u in batch], headers=UA, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(20 * (attempt + 1)); continue
            r.raise_for_status()
            break
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"STOPPED: requests kept failing; {len(out)} posts saved, run again to continue")
    for p in r.json().get("posts", []):
        reply = (p.get("record", {}).get("reply") or {}).get("parent", {}).get("uri")
        out[p["uri"]] = dict(links=links_of(p), reply_to=reply)
    if (i // 25) % 40 == 0:
        json.dump(out, open(out_path, "w", encoding="utf-8"))
        print(f"  {i + len(batch)}/{len(uris)}", flush=True)
    time.sleep(0.3)
json.dump(out, open(out_path, "w", encoding="utf-8"))
print(f"posts with details: {len(out)} | with at least one link: {sum(1 for v in out.values() if v['links'])} | "
      f"replies: {sum(1 for v in out.values() if v['reply_to'])}")
