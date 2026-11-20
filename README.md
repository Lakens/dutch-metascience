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
- **Places**: Dutch institutions on a map over time, collaboration between institutions, partner countries.
- **Inferences**: who could work together, which themes are rising, and shared questions that could become joint projects.

## How the data were made

1. A hand-reviewed list of Dutch metascientists; their ORCID and OpenAlex records (`find_orcids.py`).
2. Their papers from OpenAlex (`openalex_works.py`) and Crossref (`crossref_works.py`, `crossref_lookup.py`),
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
6. Embeddings (`bge-m3`), a UMAP map and 20 k-means clusters named by the model (`embed_and_map.py`).
7. The JSON files for the website (`build_site_data.py`, output in `docs/data/`).
8. The Inferences page (`build_inferences.py`): collaboration suggestions from the paper embeddings, rising themes
   from each cluster's share per year, and shared questions and goals (`goals.json`, written by Claude after reading
   all 2025-2026 titles and abstracts; every statement cites the papers it rests on).

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

OpenAlex (CC0) and Crossref.
