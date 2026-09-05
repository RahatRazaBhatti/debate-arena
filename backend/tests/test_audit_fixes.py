"""
Tests for the audit-and-correction fixes (see AUDIT_AND_CORRECTION_PLAN.md).

These deliberately test the pure, deterministic pieces of the pipeline
(no LLM calls) - matching the existing style of test_momentum.py - plus
score_node's penalty application, which only needs a synthetic
state["last_assessment"] and doesn't call the LLM either.

None of these tests hardcode Elena or Marcus as the expected winner:
every "who wins" assertion is driven by which synthetic inputs were fed
in for that specific test case.
"""

from langchain_core.messages import AIMessage

from arena.evidence import (
    classify_source,
    compute_deterministic_grounding,
    normalize_verdict,
    score_source_credibility,
)
from arena.research_planner import ResearchPlanner
from arena.agents import score_node, summary_node


# summary_node() does call an LLM chain for the narrative text, but that
# call is wrapped in try/except with a safe string fallback, and the new
# `confidence` label is computed BEFORE the chain is invoked and assigned
# unconditionally afterward - so these tests don't need network access or
# a real API key to correctly exercise the confidence-banding logic.
# Reset the shared OfflineEchoLLM cursor if one is already active in this
# session (see the equivalent fixture in test_state_propagation.py),
# purely so the (unused-by-assertions) summary text doesn't accidentally
# desync other tests' expectations when run in the same session.
def _reset_offline_cursor():
    from arena import config as config_module

    if hasattr(config_module.load_llm, "_offline_singleton"):
        config_module.load_llm._offline_singleton.i = 0


# ==========================================================
# 1. Claim vs. evidence (Core Problem #1 / #7)
# ==========================================================

def test_grounding_fully_supported_claim_scores_high():
    claims = [{"verdict": "SUPPORTED", "overclaim": False}]
    assert compute_deterministic_grounding(claims) == 100.0


def test_grounding_overclaim_drags_down_a_supported_claim():
    supported_no_overclaim = compute_deterministic_grounding(
        [{"verdict": "SUPPORTED", "overclaim": False}]
    )
    supported_with_overclaim = compute_deterministic_grounding(
        [{"verdict": "SUPPORTED", "overclaim": True}]
    )
    assert supported_with_overclaim < supported_no_overclaim
    assert supported_with_overclaim == 75.0  # 100 - OVERCLAIM_PENALTY(25)


def test_grounding_not_supported_and_contradicted_score_zero():
    assert compute_deterministic_grounding([{"verdict": "NOT_SUPPORTED"}]) == 0.0
    assert compute_deterministic_grounding([{"verdict": "CONTRADICTED"}]) == 0.0


def test_grounding_partial_and_insufficient_are_between_zero_and_full():
    partial = compute_deterministic_grounding([{"verdict": "PARTIALLY_SUPPORTED"}])
    insufficient = compute_deterministic_grounding([{"verdict": "INSUFFICIENT_EVIDENCE"}])
    assert 0 < partial < 100
    assert 0 < insufficient < 100
    assert partial > insufficient  # partial support should score higher


def test_grounding_no_claims_is_conservative_zero():
    assert compute_deterministic_grounding([]) == 0.0


def test_normalize_verdict_handles_garbage_conservatively():
    # An invalid/garbage verdict string must not crash and must not be
    # treated as passing.
    assert normalize_verdict("definitely true!!") == "NOT_SUPPORTED"
    assert normalize_verdict("") == "NOT_SUPPORTED"
    assert normalize_verdict(None) == "NOT_SUPPORTED"
    assert normalize_verdict("supported") == "SUPPORTED"  # case-insensitive


# ==========================================================
# 2. Source credibility (Core Problem #6)
# ==========================================================

def test_peer_reviewed_domain_is_high_tier():
    label, score = classify_source("https://www.nature.com/articles/some-study")
    assert label == "peer_reviewed"
    assert score >= 9


def test_gov_domain_is_high_tier():
    label, score = classify_source("https://www.nist.gov/report")
    assert label == "government_or_academic"
    assert score >= 9


def test_forum_domain_is_low_tier_and_lower_than_gov():
    forum_label, forum_score = classify_source("https://www.linkedin.com/posts/someone_ai")
    gov_label, gov_score = classify_source("https://www.nist.gov/report")

    assert forum_label != gov_label
    assert forum_score < gov_score  # a LinkedIn post must NOT score like a .gov source


def test_unknown_domain_gets_neutral_default_not_high_or_low():
    label, score = classify_source("https://some-random-unclassified-site.example")
    assert label == "unclassified"
    assert 3 <= score <= 6


def test_score_source_credibility_averages_across_records():
    records = [
        {"url": "https://www.nature.com/x"},   # 9.5
        {"url": "https://www.linkedin.com/y"},  # 2.0
    ]
    summary = score_source_credibility(records)
    assert summary["count"] == 2
    assert 5.0 < summary["average"] < 6.0  # roughly the midpoint


def test_score_source_credibility_empty_is_neutral_not_zero():
    summary = score_source_credibility([])
    assert summary["count"] == 0
    assert summary["average"] > 0  # must not silently punish "no sources this turn"


# ==========================================================
# 3. Claim-targeted evidence retrieval (Core Problem #5)
# ==========================================================

def test_research_planner_queries_change_with_opponent_claim():
    planner = ResearchPlanner()

    plan_a = planner.create_plan(
        topic="Should AI replace developers?",
        speaker="elena",
        opponent_argument="The METR study found AI improves developer productivity significantly.",
        strategy="",
        argument_memory="",
    )
    plan_b = planner.create_plan(
        topic="Should AI replace developers?",
        speaker="elena",
        opponent_argument="Generated code frequently contains security vulnerabilities.",
        strategy="",
        argument_memory="",
    )

    # The claim-targeted query (last one appended) must differ when the
    # opponent's actual claim differs, even though the topic is identical.
    assert plan_a.search_queries[-1] != plan_b.search_queries[-1]


def test_research_planner_no_opponent_argument_yet_has_no_claim_query():
    planner = ResearchPlanner()
    plan = planner.create_plan(
        topic="Should AI replace developers?",
        speaker="elena",
        opponent_argument="No previous opponent argument.",
        strategy="",
        argument_memory="",
    )
    # Opening turn: only the 4 topic-level queries, no claim-targeted 5th.
    assert len(plan.search_queries) == 4


def test_research_planner_symmetric_between_elena_and_marcus():
    planner = ResearchPlanner()
    common_opponent = "AI adoption is accelerating across the industry."

    elena_plan = planner.create_plan(
        topic="Should AI replace developers?",
        speaker="elena",
        opponent_argument=common_opponent,
        strategy="",
        argument_memory="",
    )
    marcus_plan = planner.create_plan(
        topic="Should AI replace developers?",
        speaker="marcus",
        opponent_argument=common_opponent,
        strategy="",
        argument_memory="",
    )

    # Same number of queries, same number of evidence goals - neither
    # agent gets an easier/harder research task (Core Problem #4 guard).
    assert len(elena_plan.search_queries) == len(marcus_plan.search_queries)
    assert len(elena_plan.evidence_goals) == len(marcus_plan.evidence_goals)


# ==========================================================
# 4. Contradiction / overclaim penalties actually cost points
#    (Core Problems #8 / #9 / #11)
# ==========================================================

def _base_state(assessment_overrides=None, speaker="elena"):
    assessment = {
        "rebuttal": 8,
        "logic": 8,
        "clarity": 8,
        "grounding_score": 80,
        "claims": [],
        "contradiction_found": False,
    }
    if assessment_overrides:
        assessment.update(assessment_overrides)

    return {
        "topic": "Should AI replace developers?",
        "tool_context": "",
        "messages": [AIMessage(content="Some argument text here.", name=speaker)],
        "scores": {},
        "judge_history": [],
        "turn_count": 0,
        "max_turns": 2,
        "current_speaker": speaker,
        "last_assessment": assessment,
    }


def test_contradiction_penalty_lowers_composite():
    clean_state = _base_state({"contradiction_found": False})
    contradicted_state = _base_state({"contradiction_found": True})

    clean_result = score_node(clean_state)
    contradicted_result = score_node(contradicted_state)

    assert (
        contradicted_result["weighted_scores"]["elena"]
        < clean_result["weighted_scores"]["elena"]
    )
    assert contradicted_result["last_weighted"]["contradiction_penalty"] == 10
    assert clean_result["last_weighted"]["contradiction_penalty"] == 0


def test_overclaim_penalty_lowers_composite():
    clean_state = _base_state({"claims": [{"claim": "x", "verdict": "SUPPORTED", "overclaim": False}]})
    overclaimed_state = _base_state({"claims": [{"claim": "x", "verdict": "SUPPORTED", "overclaim": True}]})

    clean_result = score_node(clean_state)
    overclaimed_result = score_node(overclaimed_state)

    assert (
        overclaimed_result["weighted_scores"]["elena"]
        < clean_result["weighted_scores"]["elena"]
    )
    assert overclaimed_result["last_weighted"]["overclaim_penalty"] == 5
    assert clean_result["last_weighted"]["overclaim_penalty"] == 0


def test_composite_never_goes_negative():
    # Worst possible turn: zero scores + a contradiction + an overclaim.
    state = _base_state(
        {
            "rebuttal": 0,
            "logic": 0,
            "clarity": 0,
            "grounding_score": 0,
            "contradiction_found": True,
            "claims": [{"claim": "x", "verdict": "NOT_SUPPORTED", "overclaim": True}],
        }
    )
    result = score_node(state)
    assert result["last_weighted"]["composite"] >= 0


# ==========================================================
# 5. No hardcoded winner - the same function produces different
#    winners depending purely on the synthetic inputs (Core requirement:
#    "the winner must be an outcome of the evaluation, not a
#    predetermined property of either agent").
# ==========================================================

def test_score_node_elena_can_win_on_merit():
    state = _base_state(
        {"rebuttal": 9, "logic": 9, "clarity": 9, "grounding_score": 90},
        speaker="elena",
    )
    result = score_node(state)
    assert result["weighted_scores"]["elena"] > result["weighted_scores"].get("marcus", 0)


def test_score_node_marcus_can_win_on_merit():
    state = _base_state(
        {"rebuttal": 9, "logic": 9, "clarity": 9, "grounding_score": 90},
        speaker="marcus",
    )
    result = score_node(state)
    assert result["weighted_scores"]["marcus"] > result["weighted_scores"].get("elena", 0)


# ==========================================================
# 6. Winner confidence banding (Core Problem #12)
# ==========================================================

def _summary_state(elena_score, marcus_score):
    return {
        "messages": [],
        "weighted_scores": {"elena": elena_score, "marcus": marcus_score},
        "scores": {"elena": 1, "marcus": 1},
        "momentum_scores": {"elena": 1, "marcus": 1},
        "contradictions": [],
        "claims_log": [],
        "judge_history": [],
    }


def test_confidence_too_close_to_call_for_near_tied_scores():
    _reset_offline_cursor()
    state = _summary_state(200.0, 198.0)  # 1% margin
    result = summary_node(state)
    assert result["confidence"] == "TOO_CLOSE_TO_CALL"


def test_confidence_high_for_large_margin():
    _reset_offline_cursor()
    state = _summary_state(300.0, 100.0)  # 50% margin
    result = summary_node(state)
    assert result["confidence"] == "HIGH"


def test_confidence_moderate_for_mid_margin():
    _reset_offline_cursor()
    state = _summary_state(220.0, 180.0)  # 10% margin
    result = summary_node(state)
    assert result["confidence"] == "MODERATE"
