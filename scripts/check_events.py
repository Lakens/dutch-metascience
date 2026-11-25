"""Check the historical events for the History page against Wikipedia, and keep only those that pass.

Usage: python -I check_events.py <out history_events.json> <events file> [<events file> ...]
The events were collected by Claude agents from Wikipedia (English or Dutch). Each event has a year, a Wikipedia URL
and a quote: the words in the article that give the date. For every event this script downloads the article's plain
text from the Wikipedia API and keeps the event only when
 1. the article exists;
 2. the quote is in the article (case, punctuation and spacing ignored; at least 80% of the quote's words must appear
    in the article as one unbroken run, to allow for small edits to the article since the quote was taken);
 3. the event's year (and end year, if any) is written in the quote.
Events that fail are listed on screen and left out. Duplicates (same article and year) are merged, keeping the
union of their themes.
"""
import sys, re, json, time, difflib, urllib.parse, unicodedata
import requests

sys.stdout.reconfigure(encoding="utf-8")
out_path, in_paths = sys.argv[1], sys.argv[2:]
s = requests.Session()
s.headers["User-Agent"] = "dutch-metascience/1.0 (https://github.com/Lakens/dutch-metascience)"

def words(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return re.findall(r"[^\W_]+", text)
cache = {}
def article(url):
    if url in cache:
        return cache[url]
    u = urllib.parse.urlparse(url)
    lang = u.netloc.split(".")[0]
    title = urllib.parse.unquote(u.path.split("/wiki/", 1)[1]).replace("_", " ").split("#")[0]
    for attempt in range(4):
        try:
            r = s.get(f"https://{lang}.wikipedia.org/w/api.php", timeout=60,
                      params={"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
                              "titles": title, "format": "json", "formatversion": 2})
            r.raise_for_status()
            pages = r.json()["query"]["pages"]
            text = "" if pages[0].get("missing") else pages[0].get("extract", "")
            break
        except (requests.RequestException, ValueError, KeyError):
            time.sleep(3 * (attempt + 1))
    else:
        text = None
    cache[url] = text
    time.sleep(0.2)
    return text

events, failed = [], []
for path in in_paths:
    for e in json.load(open(path, encoding="utf-8")):
        text = article(e["url"])
        q = words(e.get("quote") or "")
        why = None
        if text is None:
            why = "could not download the article"
        elif not text:
            why = "article not found"
        elif len(q) < 4:
            why = "quote too short"
        else:
            t = words(text)
            m = difflib.SequenceMatcher(None, q, t, autojunk=False).find_longest_match(0, len(q), 0, len(t))
            if m.size < 0.8 * len(q):
                why = f"quote not found (longest matching run {m.size} of {len(q)} words)"
            else:
                years = [str(e["year"])] + ([str(e["end"])] if e.get("end") else [])
                quote_text = " ".join(q)
                missing = [y for y in years if y not in quote_text]
                if missing:
                    why = "year not in quote: " + ", ".join(missing)
        if why:
            failed.append((why, e))
        else:
            events.append(e)

# The same event found by two agents in different articles (checked by hand): (article, year) of the second -> the first.
SAME_EVENT = {
    ("https://nl.wikipedia.org/wiki/Don_Poldermans", 2011): ("https://en.wikipedia.org/wiki/Don_Poldermans", 2011),
    ("https://en.wikipedia.org/wiki/Gene_V._Glass", 1976): ("https://en.wikipedia.org/wiki/Meta-analysis", 1976),
    ("https://en.wikipedia.org/wiki/Replication_crisis", 2021): ("https://en.wikipedia.org/wiki/Reproducibility_Project", 2021),
}
merged = {}
events.sort(key=lambda e: (e["url"], e["year"]) in SAME_EVENT)      # the version to keep comes first
for e in events:
    key = SAME_EVENT.get((e["url"], e["year"]), (e["url"], e["year"]))
    if key in merged:
        merged[key]["themes"] = sorted(set(merged[key]["themes"]) | set(e["themes"]))
        merged[key]["dutch"] = merged[key]["dutch"] or e["dutch"]
    else:
        merged[key] = dict(year=e["year"], month=e.get("month"), end=e.get("end"), title=e["title"], text=e["text"],
                           themes=sorted(set(e["themes"])), dutch=bool(e.get("dutch")), url=e["url"],
                           quote=e["quote"])
out = sorted(merged.values(), key=lambda e: (e["year"], e.get("month") or 0))
json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"events read: {len(events) + len(failed)} | passed: {len(events)} | after merging duplicates: {len(out)} "
      f"| Dutch: {sum(e['dutch'] for e in out)} | failed: {len(failed)}")
for why, e in failed:
    print(f"  FAILED ({why}): {e['year']} {e['title']} | {e['url']}")
