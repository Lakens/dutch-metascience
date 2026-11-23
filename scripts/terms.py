"""Search terms for the OpenAlex search for Dutch metascience papers (2005 on).

Bare 'replication' and 'reproducibility' are left out: in OpenAlex they mostly match DNA replication,
genetic replication cohorts and measurement reliability.
"""
TERMS = [
    # replication and reproducibility
    'replicability', '"reproducibility crisis"', '"replication crisis"', '"computational reproducibility"',
    '"analytic reproducibility"', '"analytical reproducibility"', '"reproducible research"',
    '"research reproducibility"', '"reproducibility project"', '"replication study"', '"replication studies"',
    '"direct replication"', '"conceptual replication"', '"replication attempt"', '"failed to replicate"',
    '"registered replication"', '"many labs"',
    # research practices and bias, open science, peer review
    'preregistration', 'preregistered', '"registered report"', '"registered reports"', '"open science"',
    '"publication bias"', '"questionable research practices"', '"p-hacking"', '"selective reporting"',
    '"reporting bias"', '"outcome switching"', '"research waste"', '"reporting guideline"',
    '"reporting guidelines"', '"reporting quality"', '"data sharing"', '"open data"', '"peer review"',
    # meta-research and integrity, ethics
    'metascience', '"meta-science"', '"meta-research"', '"research on research"', '"research integrity"',
    '"research misconduct"', '"scientific misconduct"', '"scientific fraud"', 'retraction',
    '"responsible conduct of research"', '"research ethics"', '"research culture"',
    # statistics
    '"null hypothesis significance testing"', '"p-values"', '"p values"', '"Bayes factor"', '"Bayes factors"',
    '"equivalence test"', '"equivalence testing"', '"sample size planning"', '"statistical inference"',
    '"multiverse analysis"',
    # scientometrics and policy
    'scientometric', 'scientometrics', '"citation analysis"', '"citation impact"', '"bibliometric indicators"',
    '"research evaluation"', '"research assessment"', '"impact factor"', 'altmetrics', '"science policy"',
    '"research policy"', '"trust in science"',
    # added 23 Nov 2026: terms that the metascience papers of the starting list's full publication lists use but the
    # search above missed (funding and grant review, reporting, research data and software, publishing, research
    # culture and careers, evaluation, a few specific statistics terms). Broad terms that mostly find papers on other
    # subjects were tested and left out: "statistical power", "hypothesis testing", "statistical significance",
    # bibliometric, "conflicts of interest", "risk of bias", "methodological quality", "citizen science",
    # "science communication".
    '"grant review"', '"research funding"', '"grant applications"', '"grant proposals"',
    '"transparent reporting"', '"reporting standards"', '"reporting checklist"', '"research transparency"',
    '"FAIR principles"', '"FAIR data"', '"data reuse"', '"research data management"', '"research software"',
    'preprints', '"scholarly communication"', '"scholarly publishing"', '"open access publishing"',
    '"publication pressure"', '"research quality"', '"academic careers"', '"research careers"', '"science of science"',
    'plagiarism', '"data fabrication"',
    '"h-index"', '"university rankings"', '"recognition and rewards"', '"responsible metrics"', '"research impact"',
    '"significance testing"', '"many analysts"', '"analytic flexibility"', '"researcher degrees of freedom"',
]
KEEP_TYPES = ["article", "review", "preprint", "book", "book-chapter", "conference-paper", "editorial", "letter"]

def search_filter():
    return ("authorships.institutions.country_code:NL,from_publication_date:2005-01-01,"
            "type:" + "|".join(KEEP_TYPES) + ",title_and_abstract.search:(" + " OR ".join(TERMS) + ")")
