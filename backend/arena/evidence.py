"""
Structured evidence tracking + claim verification + citation quality.

Three things happen here:

1. Structured evidence: web_search results are kept as
   {title, url, snippet} objects (not just a flattened string blob),
   tagged with which agent/turn used them - so a claim can eventually be
   traced back to an actual source URL instead of "the AI searched the web".

2. Claim verification: after a turn, extract the concrete factual claims
   in the speech and check each one against the evidence gathered that
   turn, tagging it Supported / Partially Supported / Unsupported.

3. Citation quality: alongside verification, judge whether the sources
   actually used are relevant, credible, and (when determinable) recent -
   not just "5 sources were found".

This produces an "Evidence Grounding Score" (0-100) - the percentage of
claims that are actually backed by the retrieved evidence - which is used
as the primary, measured (not vibes-based) input to final scoring.
"""

import json
import re
from urllib.parse import urlparse

from langchain_core.prompts import ChatPromptTemplate

from arena.config import load_llm, load_assessment_llm

# Kept as an override for tests and callers that provide a custom assessment
# model. The default model is loaded when the assessment is first used so
# environment changes made after module import are respected.
assessment_llm = None


# ==========================================================
# Deterministic claim-verdict -> grounding score
# ==========================================================
# Audit finding (Core Problem #1 / #7): grounding_score used to be a
# single, unaudited LLM guess. A claim resting on a stacked inference
# ("code has bugs" -> "therefore AI threatens developer livelihoods")
# could inherit the SUPPORTED strength of the underlying fact it was
# built on top of. These weights + compute_deterministic_grounding()
# turn the verdicts the model already produces into a reproducible
# number, instead of trusting a second free-floating LLM estimate for
# the same thing.

VALID_VERDICTS = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "NOT_SUPPORTED",
    "CONTRADICTED",
    "INSUFFICIENT_EVIDENCE",
}

# 0-1 scale weight per verdict, before the overclaim penalty below.
VERDICT_WEIGHTS = {
    "SUPPORTED": 1.0,
    "PARTIALLY_SUPPORTED": 0.5,
    "INSUFFICIENT_EVIDENCE": 0.2,
    "NOT_SUPPORTED": 0.0,
    "CONTRADICTED": 0.0,
}

# Points (0-100 scale) subtracted when a claim is flagged as stacking an
# unsupported inference on top of its evidence (e.g. a narrow factual
# finding stretched into a much bigger conclusion).
OVERCLAIM_PENALTY = 25


def normalize_verdict(raw: str) -> str:
    """Map anything the LLM returns to one of VALID_VERDICTS. Unknown or
    missing verdicts are treated conservatively as NOT_SUPPORTED rather
    than silently dropped or treated as passing."""
    if not raw:
        return "NOT_SUPPORTED"
    candidate = str(raw).strip().upper().replace(" ", "_")
    return candidate if candidate in VALID_VERDICTS else "NOT_SUPPORTED"


def compute_deterministic_grounding(claims: list) -> float:
    """
    Pure, reproducible 0-100 grounding score derived from a list of
    {"verdict": ..., "overclaim": bool} claim dicts. No LLM call - this
    is the auditable half of the blended grounding score (see
    run_combined_assessment). Empty input is conservative (0), matching
    the existing "no claims / no evidence -> 0" fallback behavior.
    """
    if not claims:
        return 0.0

    scores = []
    for claim in claims:
        verdict = normalize_verdict(claim.get("verdict"))
        base = VERDICT_WEIGHTS[verdict] * 100
        if claim.get("overclaim"):
            base -= OVERCLAIM_PENALTY
        scores.append(max(0.0, min(100.0, base)))

    return round(sum(scores) / len(scores), 2)


# ==========================================================
# Rule-based source credibility tiering
# ==========================================================
# Audit finding (Core Problem #6): citation_credibility was a pure LLM
# guess with nothing stopping a LinkedIn post from scoring the same as a
# peer-reviewed paper. This is a static, inspectable domain allowlist -
# not a claim of ground truth about any specific page, just a floor/
# ceiling so the LLM's guess can't drift arbitrarily.

_SOURCE_TIERS = [
    # (substrings to match against the domain, tier label, 0-10 score)
    (("arxiv.org", "nature.com", "science.org", "ieee.org", "acm.org",
      "springer.com", "sciencedirect.com", "ncbi.nlm.nih.gov", "jstor.org",
      "pubmed"), "peer_reviewed", 9.5),
    ((".gov", "who.int", "oecd.org", "un.org", "worldbank.org", "imf.org",
      "nist.gov", ".edu"), "government_or_academic", 9.0),
    (("mckinsey.com", "gartner.com", "pewresearch.org", "rand.org",
      "brookings.edu", "metr.org", "openai.com/research",
      "deepmind.google", "anthropic.com/research"), "research_organization", 7.5),
    (("reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
      "wsj.com", "economist.com", "ft.com", "npr.org"), "reputable_news", 5.5),
    (("medium.com", "substack.com", "techcrunch.com", "wired.com",
      "theverge.com", "forbes.com"), "professional_blog", 4.0),
    (("linkedin.com", "youtube.com", "reddit.com", "news.ycombinator.com",
      "twitter.com", "x.com", "quora.com", "facebook.com",
      "medium.com/@"), "social_or_forum", 2.0),
]

_DEFAULT_TIER = ("unclassified", 4.5)  # neutral - neither trusted nor penalized


def classify_source(url: str) -> tuple:
    """Return (tier_label, score_0_10) for a URL's domain, checked
    against the static tier table above. Unknown domains get a neutral
    default rather than being assumed credible."""
    if not url:
        return _DEFAULT_TIER

    domain = urlparse(url).netloc.lower() or url.lower()

    for substrings, label, score in _SOURCE_TIERS:
        if any(s in domain or s in url.lower() for s in substrings):
            return (label, score)

    return _DEFAULT_TIER


def score_source_credibility(evidence_records: list) -> dict:
    """
    Rule-based credibility summary for a set of {"url": ...} evidence
    records (e.g. this turn's web_search results). Returns
    {"average": 0-10, "tiers": {label: count}, "count": n}. Empty input
    returns a neutral average rather than 0, since "no external sources
    were retrieved this turn" (e.g. a local-document-only turn) isn't
    itself evidence of low credibility.
    """
    if not evidence_records:
        return {"average": _DEFAULT_TIER[1], "tiers": {}, "count": 0}

    tiers = {}
    total = 0.0
    for record in evidence_records:
        label, score = classify_source(record.get("url", ""))
        tiers[label] = tiers.get(label, 0) + 1
        total += score

    return {
        "average": round(total / len(evidence_records), 2),
        "tiers": tiers,
        "count": len(evidence_records),
    }

_VERIFY_PROMPT = ChatPromptTemplate.from_template(
    """
You are a fact-checking assistant for a debate system.

You will be given a speech and the evidence that was available to the
speaker when they wrote it. Your job is ONLY to check whether the
speaker's factual claims are backed by that evidence - you are not
judging argument quality.

Evidence available this turn:
{evidence_context}

Speech to check:
{speech}

Steps:
1. Extract up to 4 distinct factual/quantitative claims from the speech
   (skip pure opinion or rhetorical questions).
2. For each claim, decide if the evidence above SUPPORTS it, PARTIALLY
   supports it, or does NOT support it (UNSUPPORTED). A claim with no
   matching evidence at all is UNSUPPORTED, even if it sounds plausible.
3. Also rate the citation quality of the evidence actually used this
   turn: relevance (1-10), credibility (1-10), and whether it looks like
   a primary source (study/government/official data) or a secondary one
   (news summary, blog, general web page).

Return ONLY valid JSON in exactly this shape:

{{
    "claims": [
        {{"claim": "short paraphrase", "verdict": "SUPPORTED", "reason": "short reason"}}
    ],
    "citation_relevance": 0,
    "citation_credibility": 0,
    "source_type": "primary",
    "grounding_score": 0
}}

"grounding_score" (0-100) is your overall estimate of what percentage of
the speech's factual content is actually backed by the evidence provided.
If no claims were made, or no evidence was available, be conservative.
"""
)


def _safe_json(text: str) -> dict:
    text = text.strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        # best-effort recovery: grab the first {...} blob
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


def verify_claims(speech: str, evidence_context: str) -> dict:
    """
    Run claim verification + citation quality assessment for one turn.
    Always returns a well-formed dict, even if the LLM call fails or
    returns malformed JSON (falls back to a conservative zero-grounding
    result rather than crashing the debate).
    """
    fallback = {
        "claims": [],
        "citation_relevance": 0,
        "citation_credibility": 0,
        "source_type": "unknown",
        "grounding_score": 0,
    }

    if not evidence_context or not evidence_context.strip():
        fallback["grounding_score"] = 0
        return fallback

    try:
        chain = _VERIFY_PROMPT | load_llm()
        response = chain.invoke(
            {
                "evidence_context": evidence_context[:4000],
                "speech": speech,
            }
        )
        parsed = _safe_json(response.content)

        if not parsed:
            return fallback

        parsed.setdefault("claims", [])
        parsed.setdefault("citation_relevance", 0)
        parsed.setdefault("citation_credibility", 0)
        parsed.setdefault("source_type", "unknown")
        parsed.setdefault("grounding_score", 0)

        # clamp to sane ranges in case the LLM ignores instructions
        parsed["grounding_score"] = max(0, min(100, _to_number(parsed["grounding_score"])))
        parsed["citation_relevance"] = max(0, min(10, _to_number(parsed["citation_relevance"])))
        parsed["citation_credibility"] = max(0, min(10, _to_number(parsed["citation_credibility"])))

        return parsed

    except Exception as e:
        print(f"[verify_claims failed] {e}")
        return fallback


def _to_number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


_COMBINED_PROMPT = ChatPromptTemplate.from_template(
    """
You are an impartial debate judge and fact-checker, doing THREE jobs in
one pass to save API calls:

1. FACT-CHECK: check the speech's factual claims against the evidence.
2. JUDGE: score the argumentation quality (not the facts).
3. CONSISTENCY: check the new claims against {speaker}'s own earlier claims.

Topic: {topic}
Evidence available this turn:
{evidence_context}

{speaker}'s earlier claims this debate (empty if this is their first turn):
{claim_history}

Opponent's previous speech:
{opponent}

{speaker}'s current speech (evaluate THIS):
{speech}

FACT-CHECK RULES (be strict about this):
For each claim, "verdict" must be one of: SUPPORTED, PARTIALLY_SUPPORTED,
NOT_SUPPORTED, CONTRADICTED, INSUFFICIENT_EVIDENCE. A claim is SUPPORTED
only if the evidence directly entails it - not merely related to it. If
the speaker builds a bigger conclusion on top of a narrower supported
fact (e.g. "the study found code quality issues" -> "therefore AI
threatens developers' livelihoods"), the narrower fact can be SUPPORTED
while the bigger conclusion is PARTIALLY_SUPPORTED or
INSUFFICIENT_EVIDENCE - set "overclaim": true on that claim in that case.
Do NOT let evidence for a narrow claim automatically justify a broader
one stacked on top of it.

JUDGE RULES (be strict about this):
- Judge CONTENT only. Do not give a higher score merely because an
  argument is pessimistic vs optimistic, pro- vs anti- the topic, longer,
  more confident-sounding, or from either named speaker - the same
  content from either speaker must score the same.
- A well-reasoned concession ("I accept X, but X does not establish Y")
  is good debating, not a weakness - do not penalize a concession that is
  followed by a counterargument.
- "engaged" must reflect whether this speech actually addressed the
  OPPONENT's specific last claim/evidence/reasoning (not just a related
  but different point): "direct" (named/paraphrased and challenged the
  claim, evidence, or reasoning), "partial" (related but didn't engage
  the specific claim), "none" (non-responsive / new unrelated argument),
  or "na" (opening turn, no opponent argument yet to engage with).

Return ONLY this JSON shape, nothing else:

{{
  "claims": [{{"claim": "short paraphrase", "verdict": "SUPPORTED", "overclaim": false}}],
  "grounding_score": 0,
  "citation_relevance": 0,
  "citation_credibility": 0,
  "rebuttal": 0,
  "logic": 0,
  "clarity": 0,
  "engaged": "direct",
  "contradiction_found": false,
  "conflicting_claim": "",
  "contradiction_explanation": ""
}}

Rules: up to 3 claims max. grounding_score/citation_* are 0-100/0-10 based
on how well the evidence backs the claims (0 if no evidence given).
rebuttal/logic/clarity are 1-10 each, judged on argument quality alone.
contradiction_found is true only if a NEW claim meaningfully reverses an
EARLIER claim by the same speaker (not disagreement with the opponent).
"""
)


def run_combined_assessment(
    topic: str,
    speaker: str,
    speech: str,
    opponent_speech: str,
    evidence_context: str,
    claim_history: list,
    evidence_records: list = None,
) -> dict:
    """
    One LLM call that replaces what used to be three: claim verification
    (verify_node), AI Judge scoring (score_node), and contradiction
    detection (contradiction_node). Roughly a 3x reduction in LLM calls
    for the assessment stage of each turn - the single highest-leverage
    way to cut Groq usage without dropping any feature.

    Two of the returned numbers are NOT taken as-is from the LLM:
    - grounding_score is blended 60/40 with compute_deterministic_grounding()
      (derived from the verdicts/overclaim flags this same call produced),
      so it can't just be a free-floating guess disconnected from the
      claims list.
    - citation_credibility is blended 50/50 with score_source_credibility()
      run over evidence_records (this turn's actual retrieved URLs), when
      any were supplied - a rule-based domain tier, not a pure vibe check.
    Also applies a rebuttal guardrail: a non-responsive turn ("engaged":
    "none") cannot score above 4/10 on rebuttal regardless of how fluent
    the LLM judged it, since fluency isn't the same as engagement.
    """
    fallback = {
        "claims": [],
        "grounding_score": 0,
        "citation_relevance": 0,
        "citation_credibility": 0,
        "rebuttal": 0,
        "logic": 0,
        "clarity": 0,
        "engaged": "na",
        "contradiction_found": False,
        "conflicting_claim": "",
        "contradiction_explanation": "",
        # Audit finding: a genuinely-computed 0 and "the LLM call failed
        # or its JSON got truncated" used to be indistinguishable once
        # this dict reached score_node/verify_node - both just looked
        # like "grounding_score: 0". assessment_status makes that
        # explicit: "ok" means every field below was actually produced
        # by the model; "unavailable" means every field below is a
        # placeholder, not a measurement, and callers should not treat
        # it as "this turn scored zero."
        "assessment_status": "unavailable",
    }

    try:
        chain = _COMBINED_PROMPT | (
            assessment_llm if assessment_llm is not None else load_assessment_llm()
        )
        response = chain.invoke(
            {
                "topic": topic,
                "speaker": speaker.capitalize(),
                "evidence_context": (evidence_context or "No evidence available.")[:1500],
                "claim_history": "\n".join(f"- {c}" for c in claim_history) or "(none yet)",
                "opponent": (opponent_speech or "No previous opponent speech.")[:800],
                "speech": speech[:1200],
            }
        )
        parsed = _safe_json(response.content)

        if not parsed:
            # LLM call succeeded but the completion wasn't valid/complete
            # JSON (most commonly: truncated mid-object because it ran out
            # of output tokens). Log it - this should be rare now that the
            # assessment call has its own token budget (ASSESSMENT_MAX_TOKENS),
            # but if it happens it must be visible, not silently zeroed.
            print(
                f"[run_combined_assessment] JSON parse failed for {speaker} - "
                f"raw completion length {len(response.content or '')} chars. "
                "Treating this turn's assessment as unavailable, not as a "
                "measured zero. If this repeats, raise ASSESSMENT_MAX_TOKENS."
            )
            return dict(fallback)

        for key, default in fallback.items():
            parsed.setdefault(key, default)
        parsed["assessment_status"] = "ok"

        # ---- normalize claim verdicts + overclaim flags ----
        claims = parsed.get("claims") or []
        normalized_claims = []
        for claim in claims[:3]:
            if not isinstance(claim, dict):
                continue
            normalized_claims.append(
                {
                    "claim": str(claim.get("claim", ""))[:200],
                    "verdict": normalize_verdict(claim.get("verdict")),
                    "overclaim": bool(claim.get("overclaim", False)),
                }
            )
        parsed["claims"] = normalized_claims

        parsed["citation_relevance"] = max(0, min(10, _to_number(parsed["citation_relevance"])))
        parsed["rebuttal"] = max(0, min(10, _to_number(parsed["rebuttal"])))
        parsed["logic"] = max(0, min(10, _to_number(parsed["logic"])))
        parsed["clarity"] = max(0, min(10, _to_number(parsed["clarity"])))

        engaged = str(parsed.get("engaged", "na")).strip().lower()
        parsed["engaged"] = engaged if engaged in ("direct", "partial", "none", "na") else "na"

        # Rebuttal guardrail: fluent but non-responsive can't buy a high score.
        if parsed["engaged"] == "none":
            parsed["rebuttal"] = min(parsed["rebuttal"], 4)

        # ---- blend grounding_score: 60% deterministic / 40% LLM ----
        llm_grounding = max(0, min(100, _to_number(parsed["grounding_score"])))
        deterministic_grounding = compute_deterministic_grounding(normalized_claims)
        if normalized_claims:
            parsed["grounding_score"] = round(
                0.6 * deterministic_grounding + 0.4 * llm_grounding, 2
            )
        else:
            # No claims extracted at all -> stay conservative, same as before.
            parsed["grounding_score"] = 0.0
        parsed["deterministic_grounding"] = deterministic_grounding

        # ---- blend citation_credibility: 50% rule-based / 50% LLM ----
        llm_credibility = max(0, min(10, _to_number(parsed["citation_credibility"])))
        if evidence_records:
            source_summary = score_source_credibility(evidence_records)
            parsed["citation_credibility"] = round(
                0.5 * source_summary["average"] + 0.5 * llm_credibility, 2
            )
            parsed["source_tiers"] = source_summary["tiers"]
        else:
            parsed["citation_credibility"] = llm_credibility

        return parsed

    except Exception as e:
        print(
            f"[run_combined_assessment failed] {speaker}: {e} - treating this "
            "turn's assessment as unavailable, not as a measured zero."
        )
        return dict(fallback)


def parse_search_results_structured(raw_response: dict, agent: str, turn: int, query: str) -> list:
    """
    Convert Tavily's raw response dict into structured evidence records
    (title/url/snippet + who used it and when), instead of only the
    flattened string blob used for prompting.
    """
    records = []

    for result in raw_response.get("results", []):
        records.append(
            {
                "title": result.get("title", "N/A"),
                "url": result.get("url", "N/A"),
                "snippet": (result.get("content", "") or "")[:250],
                "agent": agent,
                "turn": turn,
                "query": query,
            }
        )

    return records
