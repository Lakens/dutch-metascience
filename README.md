# Dutch Metascience Community

A website that maps metascience (research on research) in the Netherlands: who works on what, who works with whom,
how the field grew, and where people could work together.

**Website:** https://lakens.github.io/dutch-metascience-community/

I built this site for the symposium *Research Prioritization in Dutch Metascience* on 10 December 2026. Its goal is
to let people explore possible collaborations based on shared interests. Most of the classification and data
cleaning was done by AI, following rules that I decided on, checked and had revised many times. This README describes how the
data were collected and judged, and how I checked their quality. The data are meant for inspiration, not
scholarship, and will contain errors.

## What is on the site

- **Overview**: a map of all papers by content, the co-authorship network, and the 20 themes per year.
  "Find yourself" lets you see the whole site from the position of one person.
- **People**: a profile per person (categories, papers over time, co-authors, papers), who works on what, and
  newcomers per year.
- **Papers**: every paper with search, filters and details; how the field grew compared to all Dutch publications;
  what got cited; landmark papers per category.
- **History**: a timeline per theme with historical events, blog debates and the landmark papers that Dutch
  metascience papers cite.
- **Funding**: NWO grants of the people on the site and metascience-related NWO projects.
- **Working Together**: the 20 themes, who could work together, which themes are rising, shared questions that could
  become joint projects, and similar ongoing NWO projects.
- **Socials**: what people on the site who work in the Netherlands now post about metascience on Bluesky and
  Mastodon, and who interacts with whom.

The personal view ("Find yourself") is kept in the browser and in the page address (`?me=`); nothing is sent
anywhere, because the site has no server.

## Data sources

**People.** I started from a hand-made list of about 120 Dutch metascientists and members of Dutch open-science
networks, kept the academics, and found their ORCID and OpenAlex records. Most people on the site were found later,
as authors of the metascience papers; the site no longer distinguishes between the two. OpenAlex profiles with the
same ORCID are joined into one person.

**Papers.** Papers come from [OpenAlex](https://openalex.org) (CC0) and [Crossref](https://www.crossref.org):

1. all papers on the OpenAlex profiles of the starting list, and papers where the publisher recorded their ORCID in
   Crossref;
2. a search of OpenAlex for papers since 2005 with an author at a Dutch institution and a metascience term in the
   title or abstract (`scripts/terms.py`; terms on funding, reporting standards, research data, publishing, careers
   and research evaluation were added in November 2026);
3. for people outside the starting list with at least two metascience papers: their other papers with a Dutch
   institution that carry one of 238 OpenAlex keywords. The keywords were chosen from the data: each is on at least
   10 papers on the site, and at least 60% of the papers with that keyword in the full publication lists of the
   starting list were judged metascience (`scripts/author_lists_input.json`). This was done once.

Only scientific works are kept: journal articles, reviews, preprints with a DOI, books, chapters, conference papers,
editorials and letters. Deposits on OSF, Zenodo and Figshare, datasets and peer reviews are left out. Retraction
notices, corrections and other notices about specific papers are left out (found through Crossref, which links a
notice to the paper it concerns, and by checking titles); so are retracted papers (Crossref and OpenAlex; none were
found). Versions of the same paper (a preprint and its journal version, or a statement published in several
journals) are shown once: the journal version if there is one, otherwise the most cited version. When any version
was removed, the whole paper is removed.

**Who counts as Dutch.** An author counts as Dutch on a paper when that paper lists a Dutch institution for them. Some
publishers give all authors one shared address text that names institutions in several countries; such a paper alone
does not make anyone Dutch. Each person is shown with one institution: the Dutch institution on most of their papers.

**Other sources.**

- Reference lists and citation counts: OpenAlex.
- Yearly totals of all publications with an author at a Dutch institution (the comparison in "How the field grew"):
  OpenAlex, counting the same kinds of works (`fetch_publication_totals.py`).
- NWO grants: NWO's open data (NWOpen, CC0), linked to people by ORCID, or by full name together with a shared
  organisation. NWOpen has no amounts for projects that started before 2017; for older Veni, Vidi and Vici grants
  the standard amount of their round is used as an estimate. ZonMw and other funders are not included.
- Historical events: Wikipedia, collected by Claude agents; an event is kept only when a script finds its date and
  words in the current article.
- Blog debates: the [Open Science Blogs Archive](https://github.com/Lakens/open_science_blogs).
- Social media: public profiles and public posts on Bluesky and Mastodon (see below).

**Social media and privacy.** The Socials page is built only from public data, read through the public interfaces of
Bluesky and Mastodon without logging in.

- *Finding accounts.* Accounts that people listed themselves (ORCID, Wikidata), and a search by first and last name
  on Bluesky and three Mastodon servers (mastodon.social, fediscience.org, akademienl.social). A name match was
  accepted automatically only when it was the only match and its profile names the person's ORCID, institution or
  city, or when it is on a Mastodon server for scientists. All other name matches were judged by Claude reviewers,
  who compared the profile and recent posts with the person's institution and paper titles and accepted only accounts
  that clearly belong to the person. Accounts that never posted, automatic copies on the other platform and accounts
  that moved were handled separately.
- *Only people who work in the Netherlands now.* Claude reviewers judged this for every person from their current
  profile, recent posts and the addresses on their papers.
- *Which posts count.* All public posts were downloaded in November 2026. Only a person's own posts and replies are
  counted, not reposts. A post counts as a metascience post when it contains one of 38 terms
  (`scripts/social_terms.py`), based on the terms used to find the papers.
- *Who is named.* Only people who post regularly about metascience: at least 3 of their own posts contain a term, and
  these are at least 1% of all their own posts. Everyone else is only counted in totals. A few public posts are
  quoted with a link to the original.
- The downloaded posts and the full list of matched accounts stay private and are not in this repository. The site
  shows counts, and the names and account links of the people it names.

**Privacy and corrections.** The site shows only public information: names as they appear on papers, ORCID
identifiers, institutions on papers, titles, years, DOIs, co-authorships, citation counts, NWO grants, and the AI
judgements. It contains no email addresses, job titles or memberships. If you want to be removed or corrected, or if
a social media account was matched to you by mistake, please open an issue.

## Keywords and themes

The site uses four kinds of labels.

- **Search terms** (`scripts/terms.py`) decide which papers are found in the first place, for example
  *replicability*, *preregistration*, *publication bias*, *research integrity*, *Bayes factor*, *scientometrics* and
  *research assessment*. Plain *replication* is not used, because it mostly finds DNA replication.
- **Twelve categories** (`scripts/category_rules.md`): replication & reproducibility; bias & questionable practices;
  statistical methods; reporting & registration; methods & quality standards; open science; AI & software tools;
  peer review & publishing; scientometrics & evaluation; research integrity & ethics; the research system (policy,
  funding, careers, culture); and science & society (trust, communication, public participation). Each category has
  a written definition with rules for its borders with neighbouring categories. A paper goes to the category of what
  it studies, not the field it is in. They replaced eight earlier categories, one of which held more than a third of
  all papers and mixed very different work.
- **Twenty themes**: each paper's title and abstract were turned into a numeric fingerprint (`bge-m3`), placed on a
  2-D map (UMAP) and grouped into 20 clusters (k-means). The language model first named each cluster from the titles
  nearest its centre. Several names fitted those titles but not the whole cluster, so Claude suggested new names
  after reading each cluster's most distinctive title words, keywords, most cited titles and a random sample of
  titles, and I curated them (`scripts/cluster_names.json`). One cluster has no single subject and is called "Mixed metascience topics". Papers
  added later joined the cluster whose centre is nearest, and the map was recomputed starting from the earlier
  positions (`extend_map.py`), so the themes and their names stayed the same.
- **OpenAlex keywords** are used as they come from OpenAlex: to add papers of frequent authors (see above), to show
  rising keywords on Working Together, and in the paper details.

## AI judgments

Where AI was used, and what was checked:

| Task | Done by | Checked |
| --- | --- | --- |
| Is a paper metascience? First and second pass over about 63,000 candidates | `gpt-oss:20b` in Ollama on a SURF Research Cloud GPU, with written instructions (`classify.py`, `classify_check.py`) | test sets judged by hand (`reference_*.csv`) |
| Is a paper metascience? Reading title and abstract of every remaining paper | Claude, as many separate reviewers following `hand_check_rules.md` | check papers with a known answer, papers judged by two reviewers, samples re-checked |
| Definitions of the 12 categories | suggested by Claude | revised and approved by me |
| Category of each paper | Claude reviewers following `category_rules.md` | two independent reviewers on 250 papers; a second reviewer on 10% of the rest |
| Names of the 20 themes | suggested by AI | curated by me, against titles, keywords and samples of each cluster |
| Short summary of each paper | the model that judged the paper | not checked |
| Social media accounts and where people work now | Claude reviewers (`social_review_instructions.md`, `location_review_instructions.md`) | unclear cases left out |
| Historical events, blog debates | Claude agents | a script checks every event against the source |
| Shared questions and goals, grouping of NWO projects | Claude, every statement citing the papers or projects it rests on (`goals.json`, `project_groups.json`) | a second Claude reviewer for the project groups |

The collaboration suggestions, rising themes and newcomer counts on Working Together are not AI judgements but
calculations: text similarity between people's papers, and a multinomial logistic regression of each paper's theme on
year (`share_model.py`).

## Data quality

The quality checks were not planned in advance as one procedure. Each round of checking showed a problem, and the
next round fixed it. In order:

1. **First automatic pass.** The language model flagged 10,598 papers as metascience. A spot check showed that about
   one in six were not (for example data infrastructure for one field, or ordinary systematic reviews of a medical
   question).
2. **Stricter second pass.** A second check with stricter instructions removed 2,301 papers. A test set judged after
   the instructions were final showed that about 6% of the papers kept were still not metascience, and that about one
   in five removed papers were metascience after all (mostly bibliometric and general statistics papers; these are
   missing from the site).
3. **Reading every paper.** All remaining papers with a Dutch author were judged again from title and abstract by 16
   Claude reviewers following written rules. Each reviewer also judged 15 papers whose answer had been decided beforehand
   (agreement 94%; never "not metascience" where the answer was "metascience"). Of 115 papers judged by two
   reviewers, 106 got the same verdict. Of 40 removals checked again, 39 were right.
4. **New papers, same check.** About 3,500 papers added in November 2026 were checked in the same way by 9 more
   reviewers. Agreement with the decided answers was lower (81%), but almost all differences were "unclear" where the
   decided answer was "not metascience"; of 135 papers judged by two reviewers, 127 got the same verdict.
5. **Explicit rules for borderline papers.** About one in six papers had been judged "unclear". The rules for these
   cases were made explicit (for example: research practice within one field counts; a debate about what one study shows
   does not), and all unclear and removed papers (about 2,200) were judged again by 6 reviewers (113 of 120 papers
   judged by two of them got the same verdict). Groups of papers that reviewers had decided differently were settled
   by one decision per group.
6. **New categories.** Two reviewers who judged the same 250 papers independently chose the same category for 96%;
   a second reviewer for a random 10% of the other papers (876) agreed for 93%, and for all papers that both marked
   as sure. The 308 papers that fitted no category were checked again: 108 were not metascience and were removed.
7. **Notices, retractions and versions.** Retraction notices and corrections were removed, and all candidates were
   checked for retractions (none were found). Versions of one paper are now grouped before any paper is removed, so
   that a removed paper cannot come back as another version.
8. **People.** Profiles with the same ORCID were joined, shared address texts no longer make someone Dutch, and full
   author lists were fetched for large team papers that OpenAlex cuts short.

Every removed paper is listed with its reason in `scripts/excluded_by_hand.csv`; every verdict of step 3 to 5 is in
`scripts/hand_check_verdicts.tsv`, and every category in `scripts/category_verdicts.tsv`.

**What remains.** A few percent of the papers shown are probably not metascience (not measured exactly), and
metascience papers are missing: papers not in OpenAlex, papers that use none of the search terms, and papers before
2005 by people outside the starting list. For some papers OpenAlex has no abstract, so the AI saw only the title.
Author identities come from OpenAlex, which sometimes splits one person over several profiles or merges two people
with the same name. One metascience paper is enough to be on the site, which does not make someone a metascientist.
People who moved abroad appear with their Dutch papers; Dutch researchers working abroad do not.

## Scripts and rebuilding

All scripts are in `scripts/`; the data files behind every chart are in `docs/data/`. The scripts read API keys from
environment variables (`OPENALEX_API_KEY`, `SRC_API_KEY`, and `SURF_GPU_*` for the GPU workspace). The script that
built the starting list is not included, because its input contains personal contact details, and the social media
posts are not included because they are only needed to compute the counts.

Main steps, in order:

1. Collect: `find_orcids.py`, `openalex_works.py`, `fetch_full_authors.py`, `crossref_works.py`,
   `crossref_lookup.py`, `build_clean.py`, `fetch_search.py` (`terms.py`), `fetch_author_lists.py`.
2. Judge: `classify.py`, `classify_all.py`, `classify_check.py`; the reading of every paper follows
   `hand_check_rules.md`; categories follow `category_rules.md` and are imported with `import_categories.py`.
3. Map: `embed_and_map.py` (first map), `extend_map.py` (later papers); theme names in `cluster_names.json`.
4. Build the site data: `fetch_notice_flags.py`, `build_site_data.py`, `fetch_publication_totals.py`,
   `build_funding.py` (`fetch_nwo.py`), `build_inferences.py`, `build_history.py` (`fetch_references.py`,
   `fetch_work_dates.py`, `check_events.py`, `blog_candidates.py`, `blog_expand.py`, `check_blog_events.py`),
   `build_socials.py` (after `find_social_accounts.py`, `search_social_accounts.py`, `confirm_social_accounts.py`,
   `download_social_posts.py`, `search_social_posts.py`, `select_feed_accounts.py`), and `build_paper_extras.py`.

Each script explains its own input and rules at the top.

## Data licences

OpenAlex and NWOpen data are CC0.
