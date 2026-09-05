SOURCE: Peer-reviewed conference paper (MSR 2022) / follow-up academic literature
TITLE: Evaluating the Code Quality of AI-Assisted Code Generation Tools (on the HumanEval Benchmark)
AUTHOR/ORGANIZATION: Burak Yetistiren, Isik Ozsoy, Eray Tuzun and colleagues; corroborating follow-up studies (Nguyen & Nadi 2022; Dakhel et al.)
DATE: 2022 (original study); results corroborated in follow-up work through 2024
URL: https://arxiv.org/pdf/2304.10778
TOPIC: Software reliability, AI limitations in code generation, AI coding errors

CONTENT:
Where GitHub's own internal study (see ai_code_generation_quality.md)
measured code quality on developer-written tasks, this independent
academic line of research measured GitHub Copilot's raw correctness on
HumanEval, a standardized benchmark of 164 original programming problems
(deliberately built to avoid overlap with code likely seen during model
training). Using this stricter, "can it produce a fully correct
solution to a novel problem" bar, Copilot's suggestions had a 28.7%
correctness rate against the benchmark's own test suite - a substantially
lower figure than the near-universal success developers may assume from
marketing or from surface-level fluency of the suggested code.

Follow-up research using a different methodology found a similar
picture: Nguyen and Nadi's separate study, using 33 real interview-style
LeetCode problems across four languages, found correctness rates ranging
from 27% (JavaScript) to 57% (Java) depending on language, with the
researchers noting Copilot performed noticeably worse on problems that
were less likely to resemble content in its training data - suggesting
its apparent competence can be partly a function of pattern-matching
against familiar problems rather than genuine problem-solving. A related
2023 study comparing GitHub Copilot, Amazon CodeWhisperer, and ChatGPT
on the same benchmark found correctness rates of 46.3%, 31.1%, and 65.2%
respectively for their newest versions at the time, indicating both that
correctness varies significantly between tools and that it was still far
from 100% even for the best-performing tool tested.

RELEVANCE: Supports "software reliability" and general AI-limitations
arguments: even setting security aside, AI code-generation tools produce
a meaningful share of outright incorrect code on novel problems, which is
part of why human review before merging remains standard practice.
