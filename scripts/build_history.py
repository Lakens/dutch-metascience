"""Landmark papers and historical events per theme, for the History page.

Usage: python -I build_history.py <site data folder> <references.json> <history_events.json>
Input: the site's papers.json and clusters.json, the reference lists and cited-work details from fetch_references.py,
and the checked Wikipedia events (check_events.py). Output: <site data folder>/history.json.

Which cited works are landmark papers of a theme (a theme = one of the 20 clusters on the Themes page)?
Candidates: works cited by at least MIN_K papers of the theme. Left out are works cited mainly as a tool: software
(title mentions a package, software, toolbox, pipeline, ...) and works of which fewer than TOOL_SHARE of all their
citations come from the site's papers (general methods cited by all of science), except reporting guidelines and
statements, which are limited separately (see below).
Each candidate gets two scores between 0 and 1:
 1. importance inside the theme: the number of the theme's papers that cite the work, on a logarithmic scale, divided
    by the same for the most-cited work of the theme (log(1 + n) / log(1 + n_max));
 2. importance outside metascience: OpenAlex's field-weighted citation impact (citations divided by the average for
    works of the same field, type and year), as a percentile rank among all candidates; so a statistics paper is
    compared with other statistics papers, not with papers in small fields.
The final score is score1^W_IN * score2^W_OUT, so a work must do well on both.
A work is only considered for the MAX_THEMES themes in which the largest share of papers cite it, so a classic cited
everywhere (e.g. Ioannidis 2005) appears in the themes where it matters most, not in every timeline.
Then the works are taken in order of score, skipping a work when
 - it is cited by mostly the same site papers as a work already chosen (Jaccard similarity of the sets of citing
   papers above MAX_OVERLAP): the two cover the same ground, e.g. several papers on one statistical method;
 - it belongs to the same family as a work already chosen (see companions(): one publication series, one named
   guideline, one journal series, or one author's papers on the same topic);
 - it is a reporting guideline or statement and MAX_GUIDELINES of those were already chosen for the theme.
At most N_PER_THEME works are kept per theme, and only works with a score of at least MIN_SCORE, so a theme
without clear landmark papers gets fewer. The combined timeline holds the N_COMBINED best of each theme.
Copies of the same work (same title, e.g. a guideline published in several journals at once) are merged first.
"""
import sys, os, re, json, math, bisect, collections, statistics

sys.stdout.reconfigure(encoding="utf-8")
data_dir, refs_path, events_path = sys.argv[1:4]
MIN_K, N_PER_THEME, N_COMBINED, MAX_OVERLAP, MAX_GUIDELINES, MAX_THEMES = 5, 10, 3, 0.3, 3, 3
TOOL_SHARE, W_IN, W_OUT, MIN_SCORE, COMPANION_OVERLAP = 0.003, 0.6, 0.4, 0.6, 0.15
NOW = 2026
GUIDELINE = re.compile(r"statement|guideline|reporting items|items for reporting|checklist|extension|elaboration|"
                       r"reporting of|recommendations for|handbook|appraisal tool|tool to assess|risk of bias", re.I)
SOFTWARE = re.compile(r"\bR package|\bpackage\b|software|toolbox|\bpipeline\b|\.com\b|open source|\blme4\b|g\*power|"
                      r"\bin R\b|\bStan\b|computer program|\bJASP\b|\bSPSS\b|python|matlab", re.I)

R = json.load(open(refs_path, encoding="utf-8"))
papers = json.load(open(os.path.join(data_dir, "papers.json"), encoding="utf-8"))
clusters = json.load(open(os.path.join(data_dir, "clusters.json"), encoding="utf-8"))
refs = R["refs"]
works = {k: v for k, v in R["works"].items() if v and v["t"] and v["y"]}

# Records checked by hand (20 Nov 2026) among the chosen works, because a timeline must show the right year and author.
# Left out: records that are not the work itself. Corrected: author lists that OpenAlex has wrong (checked in Crossref).
EXCLUDE = {
    "W2499590469": "a 2003 reprint, in a book, of the Belmont Report (1979); the report itself is a Wikipedia event",
    "W2061312249": "a one-page book review (Technology and Culture, 1980) of Garfield's book Citation Indexing",
    "W4406606107": "an encyclopedia chapter (2025) about the organisation CIOMS, without author",
}
CORRECT = {
    "W2567362164": dict(a=["Julian P. T. Higgins", "James Thomas", "Jacqueline Chandler"], na=8,
                        note="editors, as listed in Crossref"),   # OpenAlex lists a contributor first
}
for k in EXCLUDE:
    works.pop(k, None)
for k, fix in CORRECT.items():
    if k in works:
        works[k].update({f: v for f, v in fix.items() if f != "note"})

# ---------------------------------------------------------------- merge copies of the same work
def title_key(w):
    k = re.sub(r"[^a-z]", "", w["t"].lower())
    return k[:80] if len(k) >= 25 else None
groups = collections.defaultdict(list)
for k, w in works.items():
    groups[title_key(w) or k].append(k)
canon = {}
for g in groups.values():
    best = max(g, key=lambda k: works[k]["c"])
    for k in g:
        canon[k] = best
site_ids = {p["id"] for p in papers}
cl_of = {p["id"]: p["cl"] for p in papers}
citers = collections.defaultdict(set)
for p in papers:
    for r in refs.get(p["id"], []):
        if r in canon:
            citers[canon[r]].add(p["id"])
n_theme = collections.Counter(p["cl"] for p in papers if refs.get(p["id"]))
n_with_refs = sum(n_theme.values())

# ---------------------------------------------------------------- the two scores that do not depend on the theme
def cites_per_year(w):
    return w["c"] / max(1, NOW - w["y"] + 1)
known = [(math.log10(1 + cites_per_year(w)), w["fwci"]) for k, w in works.items() if k in citers and w.get("fwci")]
def fwci(w):
    """OpenAlex's value; when missing (books, some editorials) or 0, the median of works with similar citations per year."""
    if w.get("fwci"):
        return w["fwci"]
    x = math.log10(1 + cites_per_year(w))
    near = [f for lx, f in known if abs(lx - x) < 0.15]
    return statistics.median(near) if near else 0.0
cand_all = [k for k in citers if len(citers[k]) >= MIN_K]
conc_val = {k: len(citers[k]) / max(works[k]["c"], len(citers[k])) for k in cand_all}
tools = {k for k in cand_all if SOFTWARE.search(works[k]["t"])
         or (conc_val[k] < TOOL_SHARE and not GUIDELINE.search(works[k]["t"]))}
cand_all = [k for k in cand_all if k not in tools]
out_val = {k: fwci(works[k]) for k in cand_all}
def prank(values):
    s = sorted(values.values())
    return {k: bisect.bisect_right(s, v) / len(s) for k, v in values.items()}
pr_out = prank(out_val)
def jaccard(a, b):
    return len(citers[a] & citers[b]) / len(citers[a] | citers[b])
def first_words(k):
    return re.findall(r"[a-z0-9]+", works[k]["t"].lower())[:2]
NOT_ACRONYM = {"COVID", "SARS", "HIV", "AIDS", "USA", "WHO", "NIH", "PLOS", "BMJ", "JAMA", "OECD", "UNESCO", "EU"}
def acronyms(k):
    return {a.split("-")[0] for a in re.findall(r"\b[A-Z][A-Z-]{3,}\b", works[k]["t"])} - NOT_ACRONYM
COMMON = set("""research science scientific study studies results analysis analyses evidence psychology psychological
clinical effect effects about their these which between using based towards toward review reviews among across""".split())
def title_words(k):
    return {w for w in re.findall(r"[a-z]{5,}", works[k]["t"].lower())} - COMMON
def companions(a, b):
    """Two works from one family, counted as one: parts of one publication series (same year and the same first two
    title words, e.g. 'CONSORT 2010 Statement' and 'CONSORT 2010 Explanation and Elaboration'); versions of one
    named guideline or tool (a shared acronym such as PRISMA in the title); editions of one document (the same first
    three title words); papers of one series in one journal (same
    year and venue, partly the same citing papers or a shared
    uncommon title word); one first author's papers on the same topic (at most 3 years
    apart, partly the same citing papers)."""
    wa, wb = works[a], works[b]
    if wa["y"] == wb["y"] and first_words(a) == first_words(b):
        return True
    fa, fb = re.findall(r"[a-z0-9]+", wa["t"].lower())[:3], re.findall(r"[a-z0-9]+", wb["t"].lower())[:3]
    if len(fa) == 3 and fa == fb:     # editions of one document, e.g. 'International Ethical Guidelines ...' 1993 and 2016
        return True
    if acronyms(a) & acronyms(b):
        return True
    j = jaccard(a, b)
    if wa["y"] == wb["y"] and wa["v"] and wa["v"] == wb["v"] and (j > COMPANION_OVERLAP or
                                                                  (j > 0.05 and title_words(a) & title_words(b))):
        return True
    return bool(wa["a"] and wb["a"] and wa["a"][0] == wb["a"][0] and abs(wa["y"] - wb["y"]) <= 3
                and j > COMPANION_OVERLAP)

# ---------------------------------------------------------------- per theme
n_in = collections.defaultdict(dict)            # n_in[theme][work] = number of the theme's papers citing the work
for k in cand_all:
    for cl, n in collections.Counter(cl_of[p] for p in citers[k]).items():
        if n >= MIN_K:
            n_in[cl][k] = n
home = {}                                        # the MAX_THEMES themes with the largest share of papers citing the work
for k in cand_all:
    sh = sorted(((n_in[cl][k] / n_theme[cl], cl) for cl in n_in if k in n_in[cl]), reverse=True)
    home[k] = {cl for _, cl in sh[:MAX_THEMES]}
themes, chosen_all, scores = [], collections.OrderedDict(), {}
for c in clusters:
    cl = c["id"]
    cand = {k: n for k, n in n_in[cl].items() if cl in home[k]}
    top = math.log1p(max(n_in[cl].values())) if n_in[cl] else 1
    sc = {k: (math.log1p(n) / top) ** W_IN * pr_out[k] ** W_OUT for k, n in cand.items()}
    sel, n_guide = [], 0
    for k in sorted(sc, key=lambda k: -sc[k]):
        if sc[k] < MIN_SCORE:
            break
        if any(jaccard(k, x) > MAX_OVERLAP or companions(k, x) for x in sel):
            continue
        g = bool(GUIDELINE.search(works[k]["t"]))
        if g and n_guide >= MAX_GUIDELINES:
            continue
        n_guide += g
        sel.append(k)
        if len(sel) == N_PER_THEME:
            break
    for k in sel:
        scores[(cl, k)] = dict(s=round(sc[k], 3), n=cand[k], sh=round(cand[k] / n_theme[cl], 3), o=round(pr_out[k], 2))
    themes.append(dict(id=cl, name=c["name"], n=n_theme[cl], n_cand=len(cand), papers=sel))
    for k in sel[:N_COMBINED]:
        chosen_all.setdefault(k, []).append(cl)

# ---------------------------------------------------------------- output
used = {k for t in themes for k in t["papers"]}
out_works = {}
for k in used:
    w = works[k]
    th = {str(t["id"]): scores[(t["id"], k)] for t in themes if k in t["papers"]}
    out_works[k] = dict(t=w["t"], y=w["y"], a=w["a"], na=w["na"], v=w["v"], doi=w["doi"], ty=w["ty"], c=w["c"],
                        fwci=round(out_val[k], 1), k=len(citers[k]), nl=1 if k in site_ids else 0, th=th)
events = json.load(open(events_path, encoding="utf-8")) if os.path.exists(events_path) else []
json.dump(dict(themes=themes, combined=[dict(id=k, th=v) for k, v in chosen_all.items()], works=out_works,
               events=events, n_papers=len(papers), n_with_refs=n_with_refs, n_cited=len({r for p in papers for r in refs.get(p["id"], [])}),
               n_cited_min_k=len(cand_all) + len(tools),
               settings=dict(min_k=MIN_K, n_per_theme=N_PER_THEME, n_combined=N_COMBINED, max_overlap=MAX_OVERLAP,
                             max_guidelines=MAX_GUIDELINES, max_themes=MAX_THEMES, tool_share=TOOL_SHARE,
                             w_in=W_IN, w_out=W_OUT, min_score=MIN_SCORE,
                             companion_overlap=COMPANION_OVERLAP)),
          open(os.path.join(data_dir, "history.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
# for the personal view: which landmark papers each person on the site cites (in any of their papers on the site);
# a separate file, loaded only when someone views the site as a person. Works are numbered in sorted order.
order = sorted(used)
pos = {k: i for i, k in enumerate(order)}
cites_of = collections.defaultdict(set)
for p in papers:
    hits = {pos[canon[r]] for r in refs.get(p["id"], []) if r in canon and canon[r] in pos}
    for pid in p["p"]:
        cites_of[pid] |= hits
json.dump(dict(works=order, people={pid: sorted(v) for pid, v in cites_of.items() if v}),
          open(os.path.join(data_dir, "history_people.json"), "w", encoding="utf-8"), separators=(",", ":"))
print(f"history_people.json: {sum(1 for v in cites_of.values() if v)} people cite at least one landmark paper, "
      f"{os.path.getsize(os.path.join(data_dir, 'history_people.json')) / 1e6:.2f} MB")
print("left out as tools:", len(tools), "|", "; ".join(sorted(works[k]["t"][:40] for k in tools)[:40]))
print(f"history.json: {len(themes)} themes, {len(used)} papers, {len(chosen_all)} on the combined timeline, "
      f"{len(events)} events")
for t in themes:
    print(f"\n== {t['id']} {t['name']} ({t['n']} papers with references, {t['n_cand']} candidates)")
    for k in sorted(t["papers"], key=lambda k: works[k]["y"]):
        w, s = works[k], scores[(t["id"], k)]
        print(f"  {w['y']} {(w['a'] or ['?'])[0][:20]:20s} s={s['s']:.2f} n={s['n']:3d} share={s['sh']:.2f} "
              f"out={s['o']:.2f} {'NL ' if k in site_ids else ''}{w['t'][:70]}")
