"""Metascience terms for searching Bluesky and Mastodon posts, grouped by theme (used by search_social_posts.py,
select_feed_accounts.py and build_socials.py).

The terms combine the three lists used elsewhere in this project: the OpenAlex search terms (terms.py), the terms
over time on the site (build_site_data.py) and the Dutch terms for metascience grants (build_funding.py), plus short
forms used on social media (prereg, OSF, QRPs, HARKing, RRs). The search ignores capital letters, except for short
forms that are also ordinary words or names (OSF, QRP, HARK, RRs, NHST, TOST, DORA); spaces, hyphens and the "#" of a
hashtag are optional inside a term, so "#OpenScience" and "open-science" match "open science".
Bare "replication" is left out (DNA and virus replication); "replication" counts only next to words such as study,
crisis or attempt.
"""
import re

S = r"[\s_-]?"   # optional space, underscore or hyphen inside a term (hashtags have none)
THEMES = {
    "replication and reproducibility": {
        "replicability": r"replicab",
        "replication crisis": rf"(replication|reproducibility|replicability){S}crisis",
        "reproducibility": r"reproducib",
        "replication study": rf"replication{S}(study|studies|project|attempt|effort|report|paper|package)|"
                             rf"(direct|conceptual|close|exact|independent|registered){S}replications?|"
                             r"fail(ed|s|ure)? to replicate|(does|did|do)(n'?t| not) replicate|replicatie",
        "many labs / big team science": rf"many{S}labs|multi{S}labs?\b|big{S}team{S}science|many{S}analysts",
    },
    "research practices and open science": {
        "preregistration": rf"pre{S}regist|\bprereg(s|ged|ging)?\b",
        "registered report": rf"registered{S}reports?|(?-i:\bRRs\b)",
        "open science": rf"open{S}(science|scholarship|research)",
        "OSF": r"(?-i:\bOSF\b)|osf\.io",
        "publication bias": rf"publication{S}bias|file{S}drawer",
        "questionable research practices": rf"questionable{S}research{S}practices?|(?-i:\bQRPs?\b)",
        "p-hacking": rf"\bp{S}hack",
        "HARKing": r"(?-i:\bHARK(ing|ed)?\b)",
        "selective reporting": rf"selective{S}reporting|outcome{S}switching|reporting{S}bias",
        "research waste": rf"research{S}waste",
        "reporting guidelines": rf"reporting{S}(guidelines?|quality)",
        "data sharing": rf"data{S}sharing|open{S}data|fair{S}data",
        "peer review": rf"peer{S}review",
    },
    "meta-research and integrity": {
        "metascience": rf"meta{S}scien|meta{S}research|research{S}on{S}research|metawetenschap|science{S}of{S}science",
        "research integrity": rf"(research|scientific){S}integrity|wetenschappelijke{S}integriteit",
        "misconduct and fraud": rf"(research|scientific|academic){S}(misconduct|fraud)|data{S}fabrication|"
                                rf"fabricated{S}data|paper{S}mills?",
        "retraction": r"retraction|retracted",
        "responsible conduct of research": rf"responsible{S}conduct{S}of{S}research",
        "research culture": rf"research{S}culture",
    },
    "statistics": {
        "significance testing": rf"(?-i:\bNHST\b)|null{S}hypothesis{S}significance|significance{S}testing",
        "p-values": rf"\bp{S}values?\b",
        "Bayes factor": rf"bayes{S}factors?",
        "equivalence test": rf"equivalence{S}test|(?-i:\bTOST\b)",
        "sample size and power": rf"sample{S}size{S}(planning|justification|calculation)|power{S}analys|statistical{S}power",
        "multiverse analysis": rf"multiverse{S}analys|specification{S}curve",
        "statcheck": r"statcheck",
        "statistical inference": rf"statistical{S}inference",
    },
    "scientometrics and policy": {
        "scientometrics": r"scientometric|bibliometric|altmetric",
        "citations and impact factor": rf"citation{S}(analysis|impact|metrics?)|impact{S}factor|\bh{S}index",
        "research assessment": rf"research{S}(assessment|evaluation)|recognition{S}(and|&){S}rewards?|"
                               rf"erkennen{S}(en|&){S}waarderen|(?-i:\bDORA\b)|\bcoara\b",
        "science and research policy": rf"(science|research){S}policy",
        "trust in science": rf"trust{S}in{S}science|vertrouwen{S}in{S}(de{S})?wetenschap",
    },
}
TERM_RX = {t: re.compile(rx, re.I) for terms in THEMES.values() for t, rx in terms.items()}
THEME_OF = {t: th for th, terms in THEMES.items() for t in terms}
CLEAN = re.compile(r"https?://\S+|@[\w.-]+(@[\w.-]+)?")   # links and mentions are not searched (osf.io is kept below)

# Terms that almost every academic uses; they are not counted when deciding who posts about metascience.
NOT_COUNTED = {"peer review", "citations and impact factor"}

def terms_in(text):
    """the terms found in a post (links and mentions are not searched; an osf.io link counts as OSF)"""
    text = text or ""
    searchable = CLEAN.sub(" ", text) + (" osf.io" if "osf.io" in text.lower() else "")
    return [t for t, rx in TERM_RX.items() if rx.search(searchable)]
