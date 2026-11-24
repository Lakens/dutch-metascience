"""Shared code: OpenAlex requests and storing an OpenAlex work in the raw database (oa_* tables)."""
import os, json, time
import requests

FIELDS = ("id,doi,display_name,publication_year,publication_date,type,primary_location,authorships,"
          "is_authors_truncated,cited_by_count,primary_topic,topics,keywords,abstract_inverted_index,language,"
          "open_access,ids")
short = lambda u: (u or "").rsplit("/", 1)[-1]
KEY = os.environ.get("OPENALEX_API_KEY", "").strip().strip('"').strip("'")
_session = requests.Session()

def oa_get(path, params):
    """GET an OpenAlex address; retries, and stops the program when it keeps failing (never continues silently)."""
    if not KEY:
        raise SystemExit("STOPPED: OPENALEX_API_KEY is not set")
    r = None
    for attempt in range(6):
        try:
            r = _session.get("https://api.openalex.org/" + path, params={**params, "api_key": KEY},
                             headers={"User-Agent": "metascience-community-script"}, timeout=90)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            time.sleep(0.1)
            return r.json()
        except requests.RequestException as e:
            print("  retrying after error:", str(e).replace(KEY, "<key>"), flush=True)
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"STOPPED: OpenAlex request kept failing (last status {getattr(r, 'status_code', '?')}): {path}")

def abstract(inv):
    if not inv:
        return None
    pos = {i: w for w, idx in inv.items() for i in idx}
    return " ".join(pos[i] for i in sorted(pos))

def store(db, w):
    """Write one OpenAlex work with its authorships and institutions; returns the work id."""
    wid = short(w["id"])
    pt = w.get("primary_topic") or {}
    loc = (w.get("primary_location") or {}).get("source") or {}
    auths = w.get("authorships") or []
    db.execute("INSERT OR REPLACE INTO oa_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        wid, (w.get("doi") or "").replace("https://doi.org/", "").lower() or None,
        w.get("display_name"), w.get("type"), w.get("publication_year"), w.get("publication_date"),
        loc.get("display_name"), loc.get("type"), w.get("cited_by_count"), len(auths),
        int(bool(w.get("is_authors_truncated"))), pt.get("display_name"),
        (pt.get("subfield") or {}).get("display_name"), (pt.get("field") or {}).get("display_name"),
        (pt.get("domain") or {}).get("display_name"),
        "; ".join(t.get("display_name", "") for t in w.get("topics") or []),
        "; ".join(k.get("display_name", "") for k in w.get("keywords") or []), w.get("language"),
        int(bool((w.get("open_access") or {}).get("is_oa"))), abstract(w.get("abstract_inverted_index")),
        json.dumps({k: v for k, v in w.items() if k != "abstract_inverted_index"}, ensure_ascii=False)))
    db.execute("DELETE FROM oa_authorships WHERE work_id=?", (wid,))
    db.execute("DELETE FROM oa_authorship_institutions WHERE work_id=?", (wid,))
    for pos, a in enumerate(auths, 1):
        au = a.get("author") or {}
        db.execute("INSERT OR REPLACE INTO oa_authorships VALUES (?,?,?,?,?,?,?,?,?)", (
            wid, pos, short(au.get("id")), au.get("display_name"), short(au.get("orcid")), a.get("author_position"),
            int(bool(a.get("is_corresponding"))), "; ".join(a.get("countries") or []),
            " | ".join(a.get("raw_affiliation_strings") or [])))
        for inst in a.get("institutions") or []:
            iid = short(inst.get("id"))
            if iid:
                db.execute("INSERT OR IGNORE INTO oa_authorship_institutions VALUES (?,?,?)", (wid, pos, iid))
                db.execute("INSERT OR REPLACE INTO oa_institutions VALUES (?,?,?,?,?,?)", (
                    iid, inst.get("display_name"), short(inst.get("ror")), inst.get("country_code"),
                    inst.get("type"), "; ".join(short(x) for x in inst.get("lineage") or [])))
    return wid
