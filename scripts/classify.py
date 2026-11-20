"""Judge with the GPU model whether papers are metascience.

Shared by the test run and the full run: prompt, answer format, one call with retries.
"""
import json, time, random
import requests

OLLAMA_CHAT = "http://localhost:11435/api/chat"
PROMPT_VERSION = "v2"  # v1: first test; v2: tighter policy/ethics/open-science/tool rules (19 Nov 2026)
MODEL = "gpt-oss:20b-capped"

CATEGORIES = ["replication and reproducibility", "research practices and bias", "open science",
              "peer review and publishing", "research integrity and misconduct", "statistical methods",
              "scientometrics and research evaluation", "science policy and ethics", "not metascience"]

SYSTEM = """You classify scientific papers. Decide from the title and abstract whether the paper is METASCIENCE.

Metascience (also called meta-research, research on research) studies how research is done, reported, evaluated, communicated or rewarded, or develops tools and methods to improve research practice. It COUNTS as metascience:
- replication and reproducibility: replication projects, single replication studies of a published finding, reproducibility of published results or code, the replication crisis;
- research practices and bias: questionable research practices, p-hacking, publication bias, selective reporting, reporting quality, reporting guidelines, preregistration, registered reports, research waste;
- open science: studies, position papers, guidelines or national infrastructure about data sharing, open data, open materials, research data management, open access as a topic of study, or the transparency of research (in general or within one field);
- peer review and publishing: studies of peer review, journals, editorial practice, retractions;
- research integrity and misconduct: fraud, misconduct, responsible conduct of research;
- statistical methods aimed at better inference in research generally: significance testing, p values, Bayes factors, equivalence tests, effect sizes, power and sample size planning, meta-analytic methods, multiverse analysis;
- scientometrics and research evaluation: bibliometrics, citation analysis, research assessment, indicators, science of science;
- science policy and ethics: policy about the research system itself (research funding, research evaluation, academic careers and research culture, open science policy), science and society (trust in science, science communication as a topic of study), and research ethics (the ethics of doing research: informed consent in research, ethics review, responsible research).

It is NOT metascience:
- a substantive study that merely USES good practices (a preregistered experiment, a study that shares its data);
- a meta-analysis or systematic review of a substantive topic (e.g. the effect of a drug), unless it studies research quality or bias itself;
- reproducibility or reliability of a measurement, device or assay (test-retest, imaging, lab measurements);
- replication in biology (DNA replication, viral replication) or a genetic replication cohort;
- a statistical method developed for one specific application only;
- a software tool, data library or dataset for one application domain, even when it is called "open";
- policy, law or regulation of other domains than research (environment, health care, technology, AI, human rights);
- medical or professional ethics, or ethics education within a profession, that is not about doing research.

Answer in JSON with: is_metascience (true/false), category (one of the given categories; "not metascience" when false), and explanation (at most 25 words)."""

SYSTEM_V2 = SYSTEM

# the first version (19 Nov 2026 test 1), kept to compare both on the same reference papers
SYSTEM_V1 = """You classify scientific papers. Decide from the title and abstract whether the paper is METASCIENCE.

Metascience (also called meta-research, research on research) studies how research is done, reported, evaluated, communicated or rewarded, or develops tools and methods to improve research practice. It COUNTS as metascience:
- replication and reproducibility: replication projects, single replication studies of a published finding, reproducibility of published results or code, the replication crisis;
- research practices and bias: questionable research practices, p-hacking, publication bias, selective reporting, reporting quality, reporting guidelines, preregistration, registered reports, research waste;
- open science: data sharing, open data, open materials, open access as a topic of study, transparency of research;
- peer review and publishing: studies of peer review, journals, editorial practice, retractions;
- research integrity and misconduct: fraud, misconduct, responsible conduct of research;
- statistical methods aimed at better inference in research generally: significance testing, p values, Bayes factors, equivalence tests, effect sizes, power and sample size planning, meta-analytic methods, multiverse analysis;
- scientometrics and research evaluation: bibliometrics, citation analysis, research assessment, indicators, science of science;
- science policy and ethics: research policy, science and society, trust in science, research ethics, research culture and careers.

It is NOT metascience:
- a substantive study that merely USES good practices (a preregistered experiment, a study that shares its data);
- a meta-analysis or systematic review of a substantive topic (e.g. the effect of a drug), unless it studies research quality or bias itself;
- reproducibility or reliability of a measurement, device or assay (test-retest, imaging, lab measurements);
- replication in biology (DNA replication, viral replication) or a genetic replication cohort;
- a statistical method developed for one specific application only.

Answer in JSON with: is_metascience (true/false), category (one of the given categories; "not metascience" when false), and explanation (at most 25 words)."""

# second, stricter check, used only for papers that v2 called metascience (20 Nov 2026): a spot check found
# that about one in six v2 'yes' papers were domain data infrastructure, substantive reviews, or measurement work
SYSTEM_V3 = SYSTEM + """

STRICT SECOND CHECK. An earlier, more lenient screen marked this paper as possibly metascience; about one in six such papers are not. Ask one question: is the OBJECT of the paper research itself (how scientists do, report, check, share, publish, review, fund, evaluate or communicate research, or how to draw better inferences from research data in general)? If the object is a substantive question, a technology, a measurement, or a domain, answer false.

Answer FALSE for these common mistakes of the earlier screen:
- data infrastructure, data standards, data platforms, FAIR implementations, databases, software or machine-learning tools for one domain or one kind of data (imaging, mass spectrometry, ecology, health records, energy), even when they say "open", "FAIR" or "reproducible";
- open data or open-source products of governments, companies or utilities, and data protection or privacy;
- systematic reviews, scoping reviews and meta-analyses that answer a substantive question (effects, accuracy of diagnostic tests or prediction models, cost-effectiveness, prevalence, how a construct is measured), even when they assess risk of bias as part of their method;
- reliability, validity, fairness or usability of tests, instruments, measurements or methods in one field (psychometrics, test-retest, think-aloud, imaging);
- quality of clinical care or clinical documentation (e.g. radiology reports), drug safety surveillance, regulation of medical products;
- substantive research on biases of people (implicit bias, cognitive bias, forecasting bias, media bias);
- research agendas or priority setting for one disease or topic; descriptions of a consortium, network or project for one domain; editorials introducing a substantive special issue;
- ethics, governance or trust concerning a technology (AI, biotechnology), not concerning research;
- management, business, finance or economics topics that are not about research.

Answer TRUE (these remain metascience): replications of a published finding in any field; studies of whether published findings replicate (including candidate-gene findings); reporting guidelines and checklists, also for one field; studies of reporting quality, statistical power or sample size practice in published research; bibliometric, altmetric and citation studies of any field; research assessment, funding, careers and research culture; research ethics committees and research ethics training; science communication and science journalism as a topic; open access, data sharing and open science practices of researchers; general statistical methods for inference (Bayes factors, multiple comparisons, prior elicitation, power)."""

# v4 (20 Nov 2026): v3 wrongly dropped replications of substantive findings and position papers/reports about
# research practice ("not a study"), and kept clinical reporting quality; these points are made explicit
SYSTEM_V4 = SYSTEM_V3.replace(
    "Ask one question:",
    "First: a replication of a published finding is ALWAYS metascience, whatever its topic (psychology, economics, "
    "software engineering). Otherwise ask one question:").replace(
    "If the object is a substantive question, a technology, a measurement, or a domain, answer false.",
    "If the object is a substantive question, a technology, a measurement, or a domain, answer false. The paper does "
    "NOT have to be an empirical study: position papers, commentaries, editorials, guidelines and reports ABOUT "
    "research practice, publishing or open science count as metascience.").replace(
    "- quality of clinical care or clinical documentation (e.g. radiology reports),",
    "- quality of clinical care or clinical documentation (e.g. how complete radiology or MRI reports for patients "
    "are: these are clinical reports, not research reports),").replace(
    "- ethics, governance or trust concerning a technology (AI, biotechnology), not concerning research;",
    "- ethics, governance or trust concerning a technology (AI, biotechnology) or models used in policy, not "
    "concerning research; knowledge platforms for such topics;").replace(
    "general statistical methods for inference (Bayes factors, multiple comparisons, prior elicitation, power).",
    "general statistical methods for inference (Bayes factors, multiple comparisons, prior elicitation, power); "
    "publishers' or institutions' reports on their open access or open science progress; analyses of how research "
    "software or tools are used and cited.")

assert SYSTEM_V4.count("ALWAYS metascience") == 1 and "MRI reports" in SYSTEM_V4 and "NOT have to be" in SYSTEM_V4 \
    and "models used in policy" in SYSTEM_V4 and "used and cited." in SYSTEM_V4

# v5 (20 Nov 2026): rescue pass over papers that v2 kept and v4 dropped. A fresh check showed v4 read "the object
# is research itself" too narrowly: it dropped bibliometric studies of one field, studies of labs' or grantees'
# output, journal indicators, research-information infrastructure and general Bayesian model comparison.
SYSTEM_V5 = SYSTEM_V4.replace(
    "Otherwise ask one question: is the OBJECT of the paper research itself (",
    "Otherwise ask one question: is the OBJECT of the paper research itself? Research itself includes the "
    "scientific literature (publication counts and trends, citations, journals, journal indicators, topics and "
    "interdisciplinarity of research fields), researchers, labs and research groups (their output, performance, "
    "careers, collaboration, gender), research funding and grants, research information systems and open research "
    "information infrastructure, and statistical inference in general (").replace(
    "Answer TRUE (these remain metascience):",
    "When a paper fits any of the following, answer TRUE even when it concerns one field, one topic or one country "
    "(a bibliometric study OF a medical subspecialty is still a bibliometric study, a replication OF a cognitive "
    "finding is still a replication). Answer TRUE (these remain metascience):") + """

Make sure your answer agrees with your explanation: if your explanation says the paper is a general statistical method, a bibliometric study, or a replication, is_metascience must be true."""

assert "Research itself includes" in SYSTEM_V5 and "OF a medical subspecialty" in SYSTEM_V5

PROMPTS = {"v1": SYSTEM_V1, "v2": SYSTEM_V2, "v3": SYSTEM_V3, "v4": SYSTEM_V4, "v5": SYSTEM_V5}

SCHEMA = {"type": "object",
          "properties": {"is_metascience": {"type": "boolean"},
                         "category": {"type": "string", "enum": CATEGORIES},
                         "explanation": {"type": "string"}},
          "required": ["is_metascience", "category", "explanation"]}

def user_text(title, abstract):
    a = (abstract or "").strip()
    if len(a) > 2500:
        a = a[:2500] + " ..."
    return f"Title: {title or '(no title)'}\nAbstract: {a or '(no abstract available)'}"

def judge(title, abstract, session=None, tries=4, system=None):
    """Returns (dict answer or None, attempts used, seconds)."""
    s = session or requests
    t0 = time.time()
    for attempt in range(1, tries + 1):
        body = {"model": MODEL, "stream": False, "think": "low", "format": SCHEMA,
                "messages": [{"role": "system", "content": system or SYSTEM},
                             {"role": "user", "content": user_text(title, abstract)}],
                # first try at temperature 0; retries at temperature 1 with a new seed
                # (a runaway answer at temperature 0 repeats itself, see the SURF note, section 17)
                "options": {"temperature": 0 if attempt == 1 else 1, "seed": random.randint(1, 10**6),
                            "num_predict": 1500}}
        try:
            r = s.post(OLLAMA_CHAT, json=body, timeout=180)
            r.raise_for_status()
            ans = json.loads(r.json()["message"]["content"])
            if isinstance(ans.get("is_metascience"), bool) and ans.get("category") in CATEGORIES:
                return ans, attempt, time.time() - t0
        except (requests.RequestException, ValueError, KeyError) as e:
            global LAST_ERROR
            LAST_ERROR = f"{type(e).__name__}: {str(e)[:200]}"
    return None, tries, time.time() - t0

LAST_ERROR = None  # the most recent failure, for diagnosis
