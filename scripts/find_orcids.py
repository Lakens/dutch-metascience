"""Find ORCID and OpenAlex IDs for every person in the combined list.

Usage: python -I find_orcids.py <combined list.xlsx> <cache.json>
Reads OPENALEX_MAILTO from the environment if set (never hard-coded).
"""
import sys, os, re, json, time, unicodedata, urllib.parse
import requests
import openpyxl

xlsx, cache_path = sys.argv[1], sys.argv[2]
sys.stdout.reconfigure(encoding="utf-8")
TEST = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set()  # test mode: these names only, no save
MAILTO = os.environ.get("OPENALEX_MAILTO", "")
OA_KEY = os.environ.get("OPENALEX_API_KEY", "").strip().strip('"').strip("'")
UA = {"User-Agent": "dutch-metascience-script"}

cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
session = requests.Session()
n_new = 0

def get(url, accept_json=True):
    global n_new
    if url in cache:
        return cache[url]
    # the cache and any error messages use the URL without the key or email
    full = url
    if "openalex" in url:
        if OA_KEY:
            full += ("&" if "?" in full else "?") + "api_key=" + urllib.parse.quote(OA_KEY)
        if MAILTO:
            full += ("&" if "?" in full else "?") + "mailto=" + MAILTO
    for attempt in range(5):
        try:
            r = session.get(full, headers={**UA, "Accept": "application/json"}, timeout=40)
            if r.status_code == 404:
                cache[url] = None; break
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            cache[url] = r.json(); break
        except Exception as e:
            print("  retrying after error:", url, e, flush=True)
            time.sleep(2 * (attempt + 1))
    if url not in cache:
        # never continue with missing data: that would silently produce wrong matches
        json.dump(cache, open(cache_path, "w", encoding="utf-8"))
        raise SystemExit(f"STOPPED: request kept failing (last status {getattr(r, 'status_code', '?')}): {url}")
    n_new += 1
    if n_new % 50 == 0:
        json.dump(cache, open(cache_path, "w", encoding="utf-8"))
    time.sleep(0.12)
    return cache.get(url)

TRANSLIT = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss",
                          "æ": "ae", "Æ": "Ae", "ı": "i", "‐": "-", "‘": "'", "’": "'"})

def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").translate(TRANSLIT)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s).split()

def normj(s):
    return "".join(norm(s))

# ---------- name parsing ----------
PARTICLES = {"van", "de", "den", "der", "ten", "ter", "'t", "von", "la", "le", "del", "da", "di"}
NAME_OVERRIDE = {
    "María de los Ángeles Crespo López": ("María", "Crespo López"),
    "Delfina S Martinez Pandiani": ("Delfina", "Martinez Pandiani"),
    "Tak Tsun (Edmund) Lo": ("Tak Tsun", "Lo"),
    "Marie Charlotte Huysmans": ("Marie Charlotte", "Huysmans"),
    "Tsz Keung Wong": ("Tsz Keung", "Wong"),
    "Luana Carla Salvi": ("Luana Carla", "Salvi"),
    "Rodrigo García Valiente": ("Rodrigo", "García Valiente"),
    "Mar Barrantes Cepas": ("Mar", "Barrantes Cepas"),
    "Sofia Gomes Pelica": ("Sofia", "Gomes Pelica"),
    "William Hedley Thompson": ("William", "Thompson"),
    "Björn Peare Bartholdy": ("Björn Peare", "Bartholdy"),
    "Sandra Klaperski-van der Wal": ("Sandra", "Klaperski"),
}
ALT_GIVEN = {"Henrik Wang": ["Mengyun"], "Dennis Peng": ["Xinru", "X"]}

def split_name(full):
    if full in NAME_OVERRIDE:
        return NAME_OVERRIDE[full]
    toks = full.replace(".", ". ").split()
    toks = [t for t in toks if not re.fullmatch(r"[A-Z]\.?", t)]  # drop middle initials
    fam = [toks[-1]]
    i = len(toks) - 2
    while i >= 1 and toks[i].lower() in PARTICLES:
        fam.insert(0, toks[i]); i -= 1
    return toks[0], " ".join(fam)

def name_ok(given, family, c_given, c_family, alt_given=()):
    f, cf = normj(family), normj(c_family)
    fam_core = normj(family.split()[-1])
    if not cf or not (f == cf or fam_core == cf or cf.endswith(fam_core) or f in cf):
        return False
    cg = norm(c_given)
    if not cg:
        return False
    for g in [given, *alt_given]:
        gn = norm(g)
        if not gn or cg[0][0] != gn[0][0]:
            continue
        a, b = cg[0], gn[0]
        # an initial matches; otherwise one first name must start with the other (Ben / Benedikt)
        if len(a) == 1 or len(b) == 1 or a.startswith(b) or b.startswith(a):
            return True
        if a in NICK.get(b, ()) or b in NICK.get(a, ()):
            return True
    return False

NICK = {"nick": ("nicholas", "nicolaas", "nikolaus"), "kris": ("kirsten", "kristina", "kristin", "christiaan"),
        "hans": ("johannes", "johan"), "bas": ("sebastiaan", "sebastian"), "lex": ("alexander",),
        "wim": ("willem", "wilhelmus"), "jos": ("josephus", "johannes"), "andy": ("andrew",), "tom": ("thomas",),
        "jim": ("james",), "bill": ("william",), "dick": ("richard",), "joe": ("joseph",), "rene": ("renatus",),
        "sander": ("alexander",), "ruud": ("rudolf",), "kees": ("cornelis",), "joost": ("justus",),
        "mike": ("michael",), "sam": ("samuel",), "liz": ("elizabeth",), "max": ("maximilian",)}

# ---------- institution evidence ----------
DOMAIN_KW = {
    "uvt.nl": ["tilburg"], "tilburguniversity.edu": ["tilburg"],
    "ru.nl": ["radboud", "nijmegen", "donders"], "radboudumc.nl": ["radboud", "nijmegen"],
    "mpi.nl": ["psycholinguistics"], "uu.nl": ["utrecht"], "umcutrecht.nl": ["utrecht"],
    "uva.nl": ["university of amsterdam", "universiteit van amsterdam", "amsterdam umc", "academic medical center"],
    "amsterdamumc.nl": ["amsterdam umc", "amsterdam university medical", "academic medical center",
                        "university of amsterdam", "vrije universiteit", "vu university"],
    "vu.nl": ["vrije universiteit", "vu amsterdam", "vu university"],
    "hva.nl": ["amsterdam university of applied sciences", "hogeschool van amsterdam"],
    "han.nl": ["han university", "hogeschool van arnhem"],
    "tudelft.nl": ["delft"], "rug.nl": ["groningen"], "umcg.nl": ["groningen"],
    "leidenuniv.nl": ["leiden"], "lumc.nl": ["leiden"], "maastrichtuniversity.nl": ["maastricht"],
    "eur.nl": ["erasmus"], "rsm.nl": ["erasmus"], "utwente.nl": ["twente"], "tue.nl": ["eindhoven"],
    "ou.nl": ["open universiteit", "open university of the netherlands"],
    "knaw.nl": ["data archiving and networked", "knaw", "royal netherlands academy"],
    "esciencecenter.nl": ["escience"], "uvh.nl": ["humanistic", "humanistiek"],
    "bham.ac.uk": ["birmingham"], "ox.ac.uk": ["oxford"], "uni-muenchen.de": ["ludwig maximilian", "munich", "munchen"],
    "lmu.de": ["ludwig maximilian", "munich", "munchen"], "cardiff.ac.uk": ["cardiff"], "ki.se": ["karolinska"],
    "essex.ac.uk": ["essex"], "uibk.ac.at": ["innsbruck"], "ucl.ac.uk": ["university college london"],
    "bath.ac.uk": ["bath"], "uni-wh.de": ["witten"], "unibe.ch": ["bern"], "sheffield.ac.uk": ["sheffield"],
    "lnu.se": ["linnaeus"], "gu.se": ["gothenburg", "goteborg"], "helsinki.fi": ["helsinki"],
    "uc.pt": ["coimbra"], "leibniz-psychology.org": ["leibniz", "zpid"], "uni-stuttgart.de": ["stuttgart"],
    "glasgow.ac.uk": ["glasgow"], "tu-dresden.de": ["dresden"], "uantwerpen.be": ["antwerp", "antwerpen"],
    "uni-muenster.de": ["munster"], "bbk.ac.uk": ["birkbeck"], "uni-freiburg.de": ["freiburg"],
    "unipd.it": ["padova", "padua"], "tudublin.ie": ["technological university dublin"],
    "oslonh.no": ["oslo new university", "oslo nye","hoyskolen kristiania", "kristiania"],
    "irb.hr": ["boskovic"], "mefst.hr": ["split"], "ffst.hr": ["split"], "elte.hu": ["eotvos", "elte"],
}
AFF_KW = {  # used when the email domain gives nothing (personal email addresses)
    "nijmegen": ["radboud", "nijmegen", "donders"], "osc amsterdam": ["amsterdam"],
    "leiden": ["leiden"], "groningen": ["groningen"], "maastricht": ["maastricht"],
    "zi mannheim": ["central institute of mental health", "mannheim"], "fair paris": ["meta", "facebook"],
    "harbers": [], "utrecht": ["utrecht"], "osc the netherlands": [],
}
TLD_COUNTRY = {"nl": "NL", "uk": "GB", "de": "DE", "ch": "CH", "se": "SE", "at": "AT", "fi": "FI",
               "pt": "PT", "hr": "HR", "hu": "HU", "be": "BE", "it": "IT", "ie": "IE", "no": "NO"}

def evidence_keys(emails, affs, nl_list):
    """Returns (normalised keywords, countries, primary keywords for ORCID affiliation search)."""
    kws, countries, primary = set(), set(), []
    for e in emails:
        dom = e.split("@")[-1].lower()
        for d, k in DOMAIN_KW.items():
            if dom == d or dom.endswith("." + d):
                kws.update(k)
                if k[0] not in primary:
                    primary.append(k[0])
        tld = dom.rsplit(".", 1)[-1]
        if tld in TLD_COUNTRY:
            countries.add(TLD_COUNTRY[tld])
        if dom == "tilburguniversity.edu":
            countries.add("NL")
    a = " ".join(norm(affs))
    for k, v in AFF_KW.items():
        if k in a:
            kws.update(v)
            if v and not primary:
                primary.append(v[0])
    for word in ("tilburg", "utrecht", "delft", "radboud", "erasmus", "twente", "maastricht", "groningen",
                 "leiden", "vrije universiteit", "university of amsterdam", "oxford", "birmingham", "innsbruck",
                 "bern", "glasgow", "antwerp", "helsinki", "coimbra", "gothenburg", "sheffield", "essex",
                 "bath", "karolinska", "cardiff", "dresden", "linnaeus", "witten"):
        if word in a:
            kws.add(word)
    if nl_list:
        countries.add("NL")
    return {normj(k) for k in kws if k}, countries, primary[:2]

def inst_hit(names, kws):
    hits = [n for n in names if n and any(k in normj(n) for k in kws)]
    return hits

# ---------- searches ----------
def q(s):
    return s.replace('"', '')

def orcid_search(query):
    url = "https://pub.orcid.org/v3.0/expanded-search/?" + urllib.parse.urlencode({"q": query, "rows": 50})
    d = get(url)
    return (d or {}).get("expanded-result") or []

def openalex_search(name):
    url = "https://api.openalex.org/authors?" + urllib.parse.urlencode({"search": name, "per-page": 25})
    d = get(url)
    return (d or {}).get("results") or []

def openalex_by_orcid(orcid):
    d = get(f"https://api.openalex.org/authors?filter=orcid:{orcid}&per-page=10")
    return (d or {}).get("results") or []

def employments(orcid):
    d = get(f"https://pub.orcid.org/v3.0/{orcid}/employments")
    cur, past = [], []
    for g in (d or {}).get("affiliation-group", []):
        for s in g.get("summaries", []):
            e = s.get("employment-summary") or {}
            org = e.get("organization") or {}
            item = (org.get("name") or "", (org.get("address") or {}).get("country") or "")
            (past if e.get("end-date") else cur).append(item)
    return cur, past

def resolve(full, emails, affs, nl_list):
    if full == "Maartje A.B.":
        return dict(certainty="not searched", evidence="Surname incomplete in source")
    given, family = split_name(full)
    alt = ALT_GIVEN.get(full, [])
    kws, countries, primary = evidence_keys(emails, affs, nl_list)
    cands = {}  # orcid -> info

    def add(orcid, **kw):
        c = cands.setdefault(orcid, dict(inst=set(), country=False, oa_ids=set(), works=0, src=set(), name=""))
        c["inst"].update(kw.get("inst", ()))
        c["country"] |= kw.get("country", False)
        if kw.get("oa_id"): c["oa_ids"].add(kw["oa_id"])
        c["works"] = max(c["works"], kw.get("works", 0))
        c["src"].add(kw["src"])
        c["name"] = c["name"] or kw.get("name", "")

    queries = [f'given-names:"{q(given)}" AND family-name:"{q(family)}"']
    for g in alt:
        queries.append(f'given-names:"{q(g)}" AND family-name:"{q(family)}"')
    plain_g, plain_f = " ".join(norm(given)), " ".join(norm(family))
    if (plain_g, plain_f) != (given.lower(), family.lower()):
        queries.append(f'given-names:"{plain_g}" AND family-name:"{plain_f}"')
    for k in primary:
        queries.append(f'family-name:"{q(family)}" AND affiliation-org-name:"{k}"')
    def run_orcid(queries):
      for qu in queries:
        for x in orcid_search(qu):
            if not name_ok(given, family, x.get("given-names") or "", x.get("family-names") or "", alt):
                continue
            insts = x.get("institution-name") or []
            add(x["orcid-id"], inst=inst_hit(insts, kws), src="ORCID",
                name=f'{x.get("given-names")} {x.get("family-names")}')
    run_orcid(queries)
    if not cands:  # fallback: surname only, then the first-name check filters
        run_orcid([f'family-name:"{q(family)}"'])

    oa_only = []
    oa_results = openalex_search(full)
    if not cands:  # e.g. ORCID record without a surname, or a nickname in our list
        oa_results = oa_results + openalex_search(family)
    for a in oa_results:
        # The surname must match the MAIN name: the alternative-name list of merged OpenAlex profiles can
        # contain co-authors' names. Alternatives are used only for first-name variants (Kris / Kirsten).
        main = a.get("display_name", "").replace(".", ". ").split()
        if not main or not name_ok(main[0][0], family, main[0][0], main[-1]) and \
                not name_ok(main[0][0], family, main[0][0], " ".join(main[1:])):
            continue
        main_fam = normj(main[-1])
        names = [a.get("display_name", "")] + [n for n in (a.get("display_name_alternatives") or [])
                                                if n.split() and normj(n.split()[-1]) == main_fam]
        ok = False
        for n in names:
            parts = n.replace(".", ". ").split()
            if len(parts) >= 2 and name_ok(given, family, parts[0], " ".join(parts[1:]), alt):
                ok = True; break
            if len(parts) >= 2 and name_ok(given, family, parts[0], parts[-1], alt):
                ok = True; break
        if not ok:
            continue
        insts = [(i.get("institution") or {}) for i in (a.get("affiliations") or [])] + (a.get("last_known_institutions") or [])
        ih = inst_hit([i.get("display_name", "") for i in insts], kws)
        ch = any(i.get("country_code") in countries for i in insts)
        oid = a["id"].rsplit("/", 1)[-1]
        if a.get("orcid"):
            add(a["orcid"].rsplit("/", 1)[-1], inst=ih, country=ch, oa_id=oid, works=a.get("works_count", 0),
                src="OpenAlex", name=a.get("display_name"))
        else:
            oa_only.append(dict(id=oid, inst=ih, country=ch, works=a.get("works_count", 0)))

    tierA = [o for o, c in cands.items() if c["inst"]]
    tierB = [o for o, c in cands.items() if not c["inst"] and c["country"]]
    res = dict(given=given, family=family)
    if len(tierA) == 1:
        chosen, cert = tierA[0], "exact"
        ev = "Record lists " + "; ".join(sorted(cands[chosen]["inst"])[:2])
    elif len(tierA) > 1:
        # several records list the institution: prefer one confirmed by both ORCID and OpenAlex, then most works
        rank = sorted(tierA, key=lambda o: (-len(cands[o]["src"]), -cands[o]["works"]))
        top, second = cands[rank[0]], cands[rank[1]]
        if (len(top["src"]), top["works"]) > (len(second["src"]), second["works"]) and top["works"] > 0:
            chosen, cert = rank[0], "probable"
            ev = (f"{len(tierA)} records list the institution; chose the one "
                  f"{'confirmed by both ORCID and OpenAlex' if len(top['src']) > len(second['src']) else 'with most works'}"
                  f" ({top['works']} works vs {second['works']}); check the others")
        else:
            chosen, cert = None, "needs manual check"
            ev = f"{len(tierA)} records list the institution and cannot be told apart"
    elif tierB and any(x["inst"] for x in oa_only):
        # an OpenAlex profile without ORCID lists the right institution: stronger than a same-country ORCID record
        chosen, cert, ev = None, "not found", "No ORCID record with this name"
    elif len(tierB) == 1:
        chosen, cert = tierB[0], "probable"
        ev = "Same country in OpenAlex, institution from our list not found"
    elif len(cands) == 1:
        chosen, cert = next(iter(cands)), "probable"
        ev = "Only record with this name; no institution information to confirm"
    elif cands:
        chosen, cert = None, "needs manual check"
        ev = f"{len(cands)} records with this name, none lists the institution"
    else:
        chosen, cert, ev = None, "not found", "No ORCID record with this name"
    res.update(orcid=chosen or "", certainty=cert, evidence=ev)

    others = [o for o in cands if o != chosen]
    res["others"] = "; ".join(
        f'{o} ({cands[o]["name"]}{": " + ", ".join(sorted(cands[o]["inst"])[:1]) if cands[o]["inst"] else ""})'
        for o in sorted(others, key=lambda o: (-len(cands[o]["inst"]), -cands[o]["works"]))[:6])

    if chosen:
        oas = openalex_by_orcid(chosen)
        # also keep OpenAlex profiles without ORCID that list the right institution (split profiles)
        extra = {x["id"] for x in oa_only if x["inst"]}
        res["openalex"] = "; ".join(sorted({a["id"].rsplit("/", 1)[-1] for a in oas} | cands[chosen]["oa_ids"] | extra))
        cur, past = employments(chosen)
        res["employer"] = "; ".join(sorted({n for n, _ in cur}))
        res["emp_country"] = "; ".join(sorted({c for _, c in cur if c}))
        if not cur and oas:
            lki = oas[0].get("last_known_institutions") or []
            res["employer"] = "; ".join(i["display_name"] for i in lki) + (" (OpenAlex, last known)" if lki else "")
            res["emp_country"] = "; ".join(sorted({i.get("country_code") or "" for i in lki}))
    else:
        oa_match = [x for x in oa_only if x["inst"]]
        if len(oa_match) == 1 and cert == "not found":
            res["openalex"] = oa_match[0]["id"]
            res["certainty"] = "no ORCID; OpenAlex profile matched"
            res["evidence"] = "OpenAlex profile without ORCID lists " + oa_match[0]["inst"][0]
    return res

# ---------- run over the workbook ----------
wb = openpyxl.load_workbook(xlsx)
NEW = ["ORCID", "OpenAlex ID", "Match certainty", "Match evidence", "Current employer (ORCID)",
       "Current employer country", "Other candidate ORCIDs"]
for ws in [wb["In NL"], wb["Check or not NL"]]:
    hdr = [c.value for c in ws[1]]
    for h in NEW:
        if h not in hdr:
            ws.cell(row=1, column=len(hdr) + 1, value=h)
            ws.cell(row=1, column=len(hdr) + 1)._style = ws.cell(row=1, column=1)._style
            hdr.append(h)
    col = {h: i + 1 for i, h in enumerate(hdr)}
    nl_list = ws.title == "In NL"
    for r in range(2, ws.max_row + 1):
        name = ws.cell(r, col["Name"]).value
        if TEST and name not in TEST:
            continue
        emails = [e.strip() for e in (ws.cell(r, col["Email(s)"]).value or "").split(";") if e.strip()]
        affs = ws.cell(r, col["Affiliation(s)"]).value or ""
        res = resolve(name, emails, affs, nl_list)
        for h, k in zip(NEW, ["orcid", "openalex", "certainty", "evidence", "employer", "emp_country", "others"]):
            ws.cell(r, col[h], value=res.get(k, ""))
        print(f'{res.get("certainty",""):<34} {name} {res.get("orcid","")}', flush=True)
        if TEST:
            print("     ", {k: v for k, v in res.items() if k not in ("certainty", "orcid")}, flush=True)
    for h, w in zip(NEW, [22, 22, 20, 45, 40, 12, 60]):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col[h])].width = w

json.dump(cache, open(cache_path, "w", encoding="utf-8"))
if not TEST:
    wb.save(xlsx)
print("new requests:", n_new)
