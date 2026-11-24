# Which category? Rules for the category check

Every metascience paper on the site gets exactly one of the 12 categories below (decided 25 Nov 2026; they replace
the 8 categories of the first classification).

Two general rules:

- **Main subject.** Choose the category of what the paper STUDIES or is ABOUT, not the field it is in or the
  method it uses. A bibliometric study of reporting guidelines is about reporting guidelines only if its question is
  about reporting; if it counts citations of the guidelines, it is scientometrics.
- **No leftover category.** If none of the 12 fits, answer NONE and say why in the note; such papers go to the hand
  check (they may not be metascience).

## The 12 categories

1. **replication** — Replication & reproducibility. Replications of a published finding (direct, conceptual,
   multi-lab), studies of whether findings replicate (replication rates, predicting replicability), whether
   published results can be reproduced from the data and code, the replication crisis as a topic.
   Borders: whether data and code are *shared* → open science; the *causes* of failed replications (p-hacking and
   the like) → bias.
2. **bias** — Bias & questionable research practices. Distortions in how research is done and published:
   publication bias, p-hacking, HARKing, spin, questionable research practices, low power in the published
   literature, research waste, the influence of funders or conflicts of interest on results.
   Borders: statistical methods to detect or correct bias → statistics; integrity policy and training → integrity.
3. **statistics** — Statistical methods. Methods and guidance for better inference in research in general:
   significance testing, p values, Bayes factors, equivalence tests, effect sizes, power analysis and sample size
   planning, multiple comparisons, meta-analytic methods, multiverse and many-analysts approaches, statistical
   misconceptions. A method for one application only is not metascience (NONE).
4. **reporting** — Reporting & registration. How completely and openly studies are reported and registered:
   reporting guidelines and checklists (CONSORT, PRISMA, STROBE, TRIPOD, STARD and their extensions), reporting
   quality and adherence, trial and study registration, preregistration, registered reports, differences between
   registrations and publications (outcome switching). Reporting standards for AI models are here.
5. **methods** — Methods & quality standards. How research in a field should be designed and carried out: core
   outcome sets and outcome measurement, consensus (Delphi) studies on methods, risk-of-bias and quality appraisal
   tools, the methodological quality of studies in a field, trial design (blinding, control groups, pragmatic
   trials), methods guidance for systematic reviews (screening, GRADE).
   Border: whether studies are *reported* completely → reporting.
6. **open** — Open science. Openness of research outputs: data sharing, open data, materials and code, research
   data management, FAIR principles, open access as a researcher practice, open science infrastructure, open
   science education and policy.
   Borders: preprints as a publishing route → publishing; citizen science → society.
7. **publishing** — Peer review & publishing. How research is reviewed and published: peer review, editors,
   journals and their policies, preprints and publishing models, predatory journals, authorship, studies of
   retractions and corrections, rules on disclosing conflicts of interest.
   Borders: journal citation metrics → scientometrics; misconduct investigations → integrity.
8. **integrity** — Research integrity & ethics. Responsible conduct of research. Integrity: fraud, fabrication,
   plagiarism, misconduct cases, integrity codes, training and climate, checks of whether published data can be
   trusted. Ethics: informed consent, ethics committees and review, the ethics of study designs (placebo, challenge
   trials), privacy and data protection in research, vulnerable participants, animal research ethics.
   Border: how common questionable practices are and what they do to the literature → bias.
9. **scientometrics** — Scientometrics & research evaluation. Measuring research and judging it: bibliometrics,
   citation analysis, altmetrics, indicators, journal metrics, rankings, science of science (productivity,
   collaboration measured with publication data), research assessment and its reform (DORA, CoARA, recognition
   and rewards *as an assessment system*), evaluation of research impact.
10. **system** — Research system. How research is organised, funded and governed, and the people in it: funding
    and grant review, science policy and governance, research priorities and agendas, universities and institutes,
    academic careers, early-career researchers and PhD training, working conditions and wellbeing, diversity and
    inclusion, research culture and leadership, team science and interdisciplinarity, the use of research in policy.
    Borders: open science policy → open; research assessment → scientometrics; integrity climate → integrity.
11. **society** — Science & society. The relation between research and the public: trust in science, science
    communication and journalism, misinformation about science, public understanding of science, public
    participation in research (citizen science, patient and public involvement, co-creation, transdisciplinary work
    with societal partners).
    Border: a paper whose main subject is something else that the public merely helped with (for example a core
    outcome set developed with patients) → that subject.
12. **tools** — AI & software tools for research. Software and AI used to do or check research: tools for
    screening and data extraction in reviews, automated checks of statistics and reporting (such as statcheck),
    language models in writing, reviewing or doing research.
    Borders: a paper ABOUT the tool → here; a paper that USES a tool to study the literature → the subject it
    studies; AI for one substantive application → NONE.

## Hard borders (watch these)

- bias vs reporting: outcome switching and registration–publication differences → reporting; publication bias,
  p-hacking, spin → bias.
- scientometrics vs system: recognition and rewards as an assessment system → scientometrics; as careers and
  working conditions → system.
- methods vs reporting: how studies should be designed or appraised → methods; how completely they are reported →
  reporting.
- statistics vs methods (added after the reference set): inference methods for research IN GENERAL → statistics;
  design or analysis guidance for one field or one kind of study (trials, epidemiology, a discipline) → methods.
- system vs society (added after the reference set): communication and exchange between science and POLICY (the
  science–policy interface, advice to government) → system; communication with the PUBLIC → society.
- A letter or comment about one specific study, a substantive review, or a method for one application is not
  metascience → NONE.

## Answer format

One line per paper, tab-separated: `work_id`, `category` (one of the 12 short names above, or NONE), `sure`
(yes/no), `note` (a few words; required when sure = no or category = NONE).
