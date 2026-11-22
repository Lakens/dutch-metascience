# Grouping ongoing NWO projects: instructions for the reviewer

These are the instructions given to Claude (Anthropic), working as a reviewer, to write
`scripts/project_groups.json` for the section "Similar ongoing projects" on the Inferences page.

## Input

A file made by `draft_project_groups.py`: one line per draft group of ongoing metascience-related NWO projects
(grouped automatically by the similarity of their titles and summaries), and one line per project that had no close
match. Each project has an id, title, funding scheme, start date, team (name, role, organisation) and summary.

## Task

Read every project yourself (title and summary). Do not write or run scripts.

1. Check the draft groups. A group is a set of at least 2 projects that work towards the same concrete aim (for
   example: replicating published findings in one field; building a shared infrastructure for one kind of research
   data; training researchers in open science at their institution). Sharing only a funding scheme, or only the
   words "open science", is not enough.
   - Move a project to another group when it fits there better.
   - Take a project out of its group when it shares no concrete aim with the others; it then stands on its own.
   - Split a group that holds two different aims; join two groups that have the same aim.
   - A project that stood on its own may join a group when it clearly shares the group's aim.
2. For each final group write:
   - `name`: at most 8 words, plain English;
   - `aim`: 1–2 sentences on what all its projects share;
   - `differences`: 1–2 sentences on how the projects differ (field, method, kind of data, audience);
   - `projects`: the project ids, exactly as in the input.

## Rules

- Every project id appears exactly once: in one group, or in `on_their_own`.
- Every statement must be supported by the summaries of the projects in the group; do not invent aims, results or
  plans.
- Do not judge the quality or importance of any project.
- Plain English, no jargon or abbreviations without explanation.

## Output

Valid JSON: `{"groups": [{"name": ..., "aim": ..., "differences": ..., "projects": [...]}, ...], "on_their_own": [...]}`.
Order the groups from the most to the fewest projects.

## Second reviewer

A second, independent reviewer then reads each group with the summaries of its projects and judges, for every
project, whether it fits the group's aim (fits / partly / does not fit), and whether the `aim` and `differences`
sentences are supported by the summaries. Projects that do not fit, and unsupported sentences, are corrected before
publication.
