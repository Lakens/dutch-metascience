# Dutch Metascience Landscape

An interactive website that maps metascience (research on research) in the Netherlands: who works with whom, on
which themes, at which institutions, and how the literature developed over time.

**Website:** https://lakens.github.io/dutch-metascience-landscape/

## What is on the site

- **Overview**: growth of the field per theme, 20 theme clusters per year, newcomers per year.
- **Who works with whom**: an explorable co-authorship network with research communities and institutions.
- **People**: a profile per author with themes, timeline, co-author network and papers; a person × theme heatmap.
- **Themes**: a map of all papers by content (embeddings + UMAP), named clusters, a keyword network,
  institutions × themes.
- **Over time**: the rise of terms such as preregistration and registered reports, rising keywords, citations.
- **History**: a timeline per theme, as in a history book: historical events from Wikipedia, the landmark papers
  that Dutch metascience papers cite, and the most cited papers by Dutch metascientists.
- **Places**: Dutch institutions on a map over time, collaboration between institutions, partner countries.
- **Funding**: NWO grants of these researchers and all metascience-related NWO projects, over time and on a scrollable timeline.
- **Inferences**: who could work together, which themes are rising, and shared questions that could become joint projects.
- **Personal view**: choose a person on the overview page ("Find yourself"); every page then highlights that person, or
  their subfield (the clusters with at least 15% of their papers). Kept in the browser and in the address (`?me=`);
  nothing is sent anywhere.

## How the data were made

1. A hand-reviewed list of Dutch metascientists; their ORCID and OpenAlex records (`find_orcids.py`).
2. Their papers from OpenAlex (`openalex_works.py`; full author lists of papers with more than 100 authors, which OpenAlex cuts off in bulk requests: `fetch_full_authors.py`) and Crossref (`crossref_works.py`, `crossref_lookup.py`),
   cleaned to scientific papers (`build_clean.py`).
3. An OpenAlex search for papers since 2005 with a Dutch author and metascience terms (`terms.py`, `fetch_search.py`).
4. Every paper judged as metascience or not, with one of eight themes, by `gpt-oss:20b` in Ollama on a SURF Research
   Cloud GPU (`classify.py`, `classify_all.py`, prompt v2), and every "metascience" paper checked again with stricter
   instructions (`classify_check.py`, prompt v4); only papers that pass both are used. Test sets judged by hand:
   `reference_100.csv`, `reference_check_100.csv`, `reference_holdout_80.csv` (the last one judged after the
   instructions were final: about 6% of the papers kept are not metascience, about one in five papers removed was).
5. Every remaining paper with a Dutch author judged once more by reading title and abstract, following
   `hand_check_rules.md`, by Claude (an AI assistant) as 14 separate reviewers, with check papers and double-judged
   papers to measure agreement. All verdicts: `hand_check_verdicts.tsv`; papers left out, with reasons:
   `excluded_by_hand.csv` (571 papers).
6. Embeddings (`bge-m3`), a UMAP map and 20 k-means clusters named by the model (`embed_and_map.py`); the names
   were then revised by hand after reading each cluster's keywords and titles (`cluster_names.json`, applied by
   `build_site_data.py`).
7. The JSON files for the website (`build_site_data.py`, output in `docs/data/`). A paper is shown when it has an
   author at a Dutch institution, or an author from the starting list without a known institution on it; a shared
   affiliation text (or a combined address block starting with "From") that names the Netherlands and other countries does not make an author Dutch on its own; Zenodo, Figshare and OSF deposits are left out, as in `build_clean.py`; copies
   of one paper (same title and a shared author) are shown once, as the journal version (`copies.json` lists them).
8. The Inferences page (`build_inferences.py`): collaboration suggestions from the paper embeddings; rising themes
   from a multinomial logistic regression of each paper's cluster on year (natural spline, chosen by QAIC, intervals
   widened for extra year-to-year variation; `share_model.py`); new authors entering each theme, with intervals from
   resampling papers; and shared questions and goals (`goals.json`, written by Claude after reading
   all 2025-2026 titles and abstracts; every statement cites the papers it rests on).
9. NWO grants (`fetch_nwo.py`, `build_funding.py`): all projects from NWO's open API NWOpen (CC0), linked to people on
   the site by ORCID, or by full name together with a shared organisation (ROR); ZonMw and other funders are not included.
10. The History page: the reference lists of all papers on the site and details of the works they cite most, from
    OpenAlex (`fetch_references.py`); landmark papers per theme chosen by how many of the theme's papers cite a work
    and by its field-weighted citation impact, with rules against near-duplicates, software and too many guidelines,
    plus the 5 most cited Dutch papers per theme (`build_history.py`, rules explained at the top of the script;
    it reads the raw database for the full author lists; papers are placed in their month of publication, from
    `fetch_work_dates.py`, run after a first `build_history.py`, which is then run again with the dates); historical events collected from Wikipedia by
    Claude agents, each with the article's own words for the date, and kept only when a script finds those words and
    the year in the current article (`check_events.py`, result in `history_events.json`); and debates from the
    [Open Science Blogs Archive](https://github.com/Lakens/open_science_blogs): candidate episodes from shared links and
    bursts of names across bloggers (`export_blogs.R`, `blog_candidates.py`), read and summarised by Claude agents; more
    posts about each event found by searching the archive for its names and checked by Claude agents (`blog_expand.py`);
    kept only with at least 5 bloggers and working links (`check_blog_events.py`, result in `blog_events.json`).

The scripts read API keys from environment variables (`OPENALEX_API_KEY`, `SRC_API_KEY`, and `SURF_GPU_*` for the
GPU workspace). The script that built the initial people list is not included, because its input contains
personal contact details.

## Limitations

Theme labels are AI judgements and can be wrong; author identities come from OpenAlex and can be split or merged;
"Dutch" means a Dutch institution on the paper. See the site's *About* page.

## Privacy and corrections

Only public bibliographic data and the AI judgements are published: no email addresses, job titles or memberships.
To be removed or corrected, please open an issue.

## Data sources

OpenAlex (CC0), Crossref, and NWOpen (NWO project data, CC0).
