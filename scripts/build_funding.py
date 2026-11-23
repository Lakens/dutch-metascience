"""NWO grants of the people on the site, plus all metascience-related NWO projects, for the Funding page.

Usage: python -I build_funding.py <raw database.sqlite> <nwo_projects.json> <site data folder>
Input: all NWO projects from the NWOpen API (fetch_nwo.py; CC0), the site's people.json, and the raw database
(OpenAlex author ids and institutions with ROR ids). Output: <site data folder>/funding.json.

Matching an NWO project member to a person on the site (NWO gives names, organisations with ROR ids, and for some
members an ORCID):
 1. same ORCID;
 2. otherwise the same full name (first name, prefix, last name; accents and case ignored) AND an organisation in
    common (the NWO organisation's ROR is one of the ROR ids of the institutions on the person's papers, or their
    parents), for only one person on the site;
 3. members without a first name: same first initial and last name and an organisation in common, for only one
    person on the site.
Name matches without a shared organisation are not used (counted in the output as 'name only, not used').

Metascience-related projects: funding schemes of NWO's open science programmes (Open Science Fund, Open Science NL,
Replication Studies), but not the funds that only pay open-access publishing costs or open-access books; and projects
whose title is about research on research (replication, reproducibility, research integrity, meta-research, ...).
"""
import sys, os, re, json, sqlite3, unicodedata, collections

sys.stdout.reconfigure(encoding="utf-8")
raw_path, nwo_path, data_dir = sys.argv[1:4]
db = sqlite3.connect(raw_path)
projects = json.load(open(nwo_path, encoding="utf-8"))
people = json.load(open(os.path.join(data_dir, "people.json"), encoding="utf-8"))

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)
def ror_short(r):
    return (r or "").rstrip("/").split("/")[-1]
def orcid_short(o):
    m = re.search(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", o or "")
    return m.group(0) if m else ""

# ---------------------------------------------------------------- people: names, ORCIDs, RORs
inst_ror = {r[0]: ror_short(r[1]) for r in db.execute("SELECT institution_id, ror FROM oa_institutions") if r[1]}
inst_lineage = {r[0]: [x.strip() for x in (r[1] or "").split(";") if x.strip()]
                for r in db.execute("SELECT institution_id, lineage FROM oa_institutions")}
listed_ids = {"P:" + r[0]: [x.strip() for x in (r[1] or "").split(";") if x.strip()]
              for r in db.execute("SELECT person_id, openalex_ids FROM oa_people")}
# OpenAlex author records with the same ORCID are one person on the site (build_site_data.py): use all of them
records_of_orcid = collections.defaultdict(set)
for o, a in db.execute("SELECT DISTINCT orcid, author_id FROM oa_authorships WHERE orcid IS NOT NULL AND orcid != ''"):
    records_of_orcid[o].add(a)
orcid_of = {x["id"]: x.get("o") or "" for x in people}
def author_ids(pid):
    ids = listed_ids.get(pid, []) if pid.startswith("P:") else [pid[2:]]
    return sorted(set(ids) | records_of_orcid.get(orcid_of.get(pid), set()))
def person_rors(pid):
    ids = author_ids(pid)
    if not ids:
        return set()
    q = ",".join("?" * len(ids))
    insts = {r[0] for r in db.execute(f"""SELECT DISTINCT ai.institution_id FROM oa_authorships a
        JOIN oa_authorship_institutions ai ON ai.work_id = a.work_id AND ai.position = a.position
        WHERE a.author_id IN ({q})""", ids)}
    out = set()
    for i in insts:
        for x in [i] + inst_lineage.get(i, []):
            if x in inst_ror:
                out.add(inst_ror[x])
    return out

by_orcid, by_full, by_initial = {}, collections.defaultdict(list), collections.defaultdict(list)
for x in people:
    if x.get("o"):
        by_orcid[orcid_short(x["o"])] = x["id"]
    parts = (x["n"] or "").replace(".", ". ").split()
    if len(parts) >= 2:
        by_full[norm(parts[0]) + norm(" ".join(parts[1:]))].append(x["id"])
        by_initial[norm(parts[0])[:1] + "|" + norm(parts[-1])].append(x["id"])
ror_cache = {}
def rors_of(pid):
    if pid not in ror_cache:
        ror_cache[pid] = person_rors(pid)
    return ror_cache[pid]

# ---------------------------------------------------------------- NWO members -> people
members = collections.defaultdict(lambda: dict(first=set(), prefix="", last="", initials="", orcids=set(), rors=set()))
for p in projects:
    for m in p["project_members"]:
        d = members[m["member_id"]]
        if m.get("first_name"): d["first"].add(m["first_name"])
        d["prefix"] = m.get("prefix") or d["prefix"]; d["last"] = m.get("last_name") or d["last"]
        d["initials"] = m.get("initials") or d["initials"]
        if m.get("orcid"): d["orcids"].add(orcid_short(m["orcid"]))
        if m.get("ror"): d["rors"].add(ror_short(m["ror"]))
match, how, name_only = {}, collections.Counter(), 0
for mid, d in members.items():
    pid = next((by_orcid[o] for o in d["orcids"] if o in by_orcid), None)
    if pid:
        match[mid] = pid; how["ORCID"] += 1; continue
    last = norm((d["prefix"] or "") + (d["last"] or ""))
    cands = set()
    for f in d["first"]:
        cands |= set(by_full.get(norm(f) + last, []))
    kind = "name and organisation"
    if not d["first"] and d["initials"]:
        cands = set(by_initial.get(norm(d["initials"])[:1] + "|" + norm(d["last"]), []))
        kind = "initial, last name and organisation"
    # of the people with this name, exactly one must have an organisation in common with the NWO member (several
    # records can carry the same name, for example a second record with one paper at another institution)
    shared = [c for c in cands if d["rors"] & rors_of(c)]
    if len(shared) == 1:
        match[mid] = shared[0]; how[kind] += 1
    elif cands and not shared:
        name_only += 1
print("NWO members matched to people on the site:", len(match), dict(how), "| name only, not used:", name_only, flush=True)

# ---------------------------------------------------------------- which projects
META_SCHEME = re.compile(r"open science|replicati", re.I)
NOT_META_SCHEME = re.compile(r"open access - publicaties|stimuleringsfonds open access|open access boeken", re.I)
# "replication" only in the sense of repeating a study (not DNA or virus replication)
META_TITLE = re.compile(r"replication stud|replication project|replication of|a replication|direct replication|replicab|"
                        r"replicating|replicatie|reproducib|research integrity|wetenschappelijke integriteit|meta-?research|"
                        r"meta-?scien|metawetenschap|questionable research|preregist|registered report|peer review|"
                        r"research assessment|open science|research culture|erkennen en waarderen|recognition and reward", re.I)
NOT_META_TITLE = re.compile(r"\bdna\b|replication fork|replication stress|chromatin|virus|viral|genom|helicase|polymerase|"
                            r"origin of replication|replisome|replicon|self-?replicat|among states|morphogenesis|"
                            r"tidal dissipation", re.I)   # last four: checked by hand, 20 Nov 2026 (chemistry, politics, biology, astronomy)
def is_meta(p):
    s, t = p.get("funding_scheme") or "", p.get("title") or ""
    by_scheme = bool(META_SCHEME.search(s) and not NOT_META_SCHEME.search(s))
    by_title = bool(META_TITLE.search(t) and not NOT_META_TITLE.search(t))
    return by_scheme or by_title

# eight groups (the site's colour palette has eight slots); Rubicon, industry schemes etc. are in "Other"
FAMILIES = [("Veni", r"\bveni\b"), ("Vidi", r"\bvidi\b"), ("Vici", r"\bvici\b"),
            ("Open Science", r"open science|replicati"), ("Open Competition", r"open competit|open competition|vrije competitie"),
            ("NWA", r"\bnwa\b|nationale wetenschapsagenda"),
            ("Gravitation & large programmes", r"zwaartekracht|gravitation|summit|groot")]
def family(scheme):
    for name, pat in FAMILIES:
        if re.search(pat, scheme or "", re.I):
            return name
    return "Other"

# metascience-related projects, by open science programme (eight groups, the palette's eight slots; the order is the
# colour order). Projects in the Open Science family whose scheme matches none of the first six go to the seventh group;
# metascience-related projects from other schemes (Veni, Open Competition, ...) to the last.
PROGRAMMES = [("Replication studies", r"replicati"),
              ("Open Science Fund", r"open science \(os\) fund|open science fund|open science fonds"),
              ("Research on Open Science", r"research on open science"),
              ("Recognition and rewards", r"erkennen en waarderen|recognition and reward"),
              ("Infrastructure, data and software", r"infrastructu|\bdcc|fair|software"),
              ("Meetings and communities", r"bijeenkomst|communit|citizen science|meeting"),
              ("Open access publishing and other", None), ("Other NWO schemes", None)]
def programme(p, fam):
    if fam != "Open Science":
        return PROGRAMMES[-1][0]
    for name, pat in PROGRAMMES[:-2]:
        if re.search(pat, p.get("funding_scheme") or "", re.I):
            return name
    return PROGRAMMES[-2][0]

def org_short(o):
    return (o or "").split("||")[0]
EMAIL = re.compile(r"([A-Za-z0-9._%+-]+)@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
def no_email(s):
    """NWO's data has an email address in at least one name field; keep only the part before the @, dots as spaces."""
    return EMAIL.sub(lambda m: m.group(1).replace(".", " "), s or "")
out_projects, people_funding = [], collections.defaultdict(list)
for p in projects:
    ms = [m for m in p["project_members"]]
    matched = [m for m in ms if m["member_id"] in match]
    meta = is_meta(p)
    if not matched and not meta:
        continue
    seen = {}
    for m in ms:
        key = (m["member_id"], m["role"])
        if key in seen:
            continue
        seen[key] = dict(id=match.get(m["member_id"]), n=no_email(" ".join(x for x in (m.get("first_name") or m.get("initials") or "",
                                                                              m.get("prefix") or "", m.get("last_name") or "") if x)),
                         r=m["role"], o=org_short(m.get("organisation")))
    fam = family(p.get("funding_scheme"))
    rec = dict(id=p["project_id"], t=p["title"], s=p.get("funding_scheme") or "", f=fam,
               b=(p.get("start_date") or "")[:10], e=(p.get("end_date") or "")[:10], a=p.get("award_amount"),
               m=1 if meta else 0, ppl=list(seen.values()),
               sum=no_email((p.get("summary_en") or p.get("summary_nl") or "").strip()[:400]))
    if meta:
        rec["g"] = programme(p, fam)
    out_projects.append(rec)
    for x in rec["ppl"]:
        if x["id"]:
            people_funding[x["id"]].append(rec["id"])
out_projects.sort(key=lambda r: r["b"] or "9999")
summary = dict(n_projects_nwo=len(projects), n_members_matched=len(match), match_kinds=dict(how), name_only_not_used=name_only,
               n_people_with_grants=len(people_funding), n_projects=len(out_projects),
               n_meta=sum(r["m"] for r in out_projects), families=[f for f, _ in FAMILIES] + ["Other"],
               programmes=[g for g, _ in PROGRAMMES],
               n_per_programme={g: sum(1 for r in out_projects if r.get("g") == g) for g, _ in PROGRAMMES},
               api="https://nwopen-api.nwo.nl/NWOpen-API/api/Projects", licence="CC0 1.0")
json.dump(dict(summary=summary, projects=out_projects, people={k: sorted(set(v)) for k, v in people_funding.items()}),
          open(os.path.join(data_dir, "funding.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"funding.json: {os.path.getsize(os.path.join(data_dir, 'funding.json')) / 1e6:.2f} MB |", summary)
