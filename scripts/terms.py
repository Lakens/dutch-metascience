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
]
KEEP_TYPES = ["article", "review", "preprint", "book", "book-chapter", "conference-paper", "editorial", "letter"]

def search_filter():
    return ("authorships.institutions.country_code:NL,from_publication_date:2005-01-01,"
            "type:" + "|".join(KEEP_TYPES) + ",title_and_abstract.search:(" + " OR ".join(TERMS) + ")")
