"""
Regression tests for the reported bug: a completed debate's Composite
Score displayed real, non-zero numbers, but Evidence Grounding and AI
Judge both showed a flat 0.0 for the entire debate, even though the
final summary referenced real evidence and claims.

Root cause: arena/evidence.py::run_combined_assessment's JSON schema
grew (5-way verdict enum + overclaim + engaged flags) while it shared
one `max_tokens` budget with full debate-speech generation
(arena/config.py::load_llm). Raising that budget enough to stop speech
truncation didn't guarantee the compact JSON call had enough room, so
Groq could truncate it mid-object; `_safe_json` then failed to parse,
and the (pre-fix) code returned an all-zero fallback dict that was
indistinguishable from "the judge genuinely scored this turn zero" -
including feeding a hard 0 into the grounding running average on every
such turn.

Fix: a dedicated, decoupled token budget for the assessment call
(arena/config.py::load_assessment_llm), plus an explicit
"assessment_status" field ("ok" vs "unavailable") so a parse failure
can no longer be silently recorded as a measured zero.
"""

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

import arena.evidence as evidence_module
from arena.evidence import run_combined_assessment
import arena.agents as agents_module
from arena.agents import verify_node, score_node


# ---------------------------------------------------------------------
# run_combined_assessment: truncated/unparseable completion must be
# flagged, not silently treated as a real all-zero measurement.
# ---------------------------------------------------------------------

def test_truncated_json_response_is_marked_unavailable_not_zero(monkeypatch):
    # Simulates exactly what a max_tokens cutoff looks like: valid JSON
    # start, cut off mid-object, no closing brace.
    truncated = FakeListChatModel(
        responses=['{"claims": [{"claim": "AI tools can introduce bugs", "verdict": "SUPPORT']
    )
    monkeypatch.setattr(evidence_module, "assessment_llm", truncated)

    result = run_combined_assessment(
        topic="Should AI replace developers?",
        speaker="elena",
        speech="AI-generated code has reliability problems.",
        opponent_speech="AI improves developer productivity.",
        evidence_context="A study found code quality issues in AI-generated code.",
        claim_history=[],
    )

    assert result["assessment_status"] == "unavailable"
    # The old bug: these being 0 was indistinguishable from a real score.
    # They're still 0 here (there's nothing else to show), but now
    # callers can tell the difference via assessment_status.
    assert result["grounding_score"] == 0
    assert result["rebuttal"] == 0


def test_complete_json_response_is_marked_ok():
    complete = FakeListChatModel(
        responses=[
            """
            {
              "claims": [{"claim": "Code quality issues found", "verdict": "SUPPORTED", "overclaim": false}],
              "grounding_score": 80,
              "citation_relevance": 8,
              "citation_credibility": 7,
              "rebuttal": 7,
              "logic": 8,
              "clarity": 8,
              "engaged": "direct",
              "contradiction_found": false,
              "conflicting_claim": "",
              "contradiction_explanation": ""
            }
            """
        ]
    )

    old_llm = evidence_module.assessment_llm
    evidence_module.assessment_llm = complete
    try:
        result = run_combined_assessment(
            topic="Should AI replace developers?",
            speaker="elena",
            speech="AI-generated code has reliability problems.",
            opponent_speech="AI improves developer productivity.",
            evidence_context="A study found code quality issues in AI-generated code.",
            claim_history=[],
        )
    finally:
        evidence_module.assessment_llm = old_llm

    assert result["assessment_status"] == "ok"
    assert result["grounding_score"] > 0
    assert result["rebuttal"] > 0


# ---------------------------------------------------------------------
# verify_node: a failed/truncated turn must not drag a real running
# grounding average down to 0.
# ---------------------------------------------------------------------

def _verify_state(grounding_history=None, turn_count=1, speaker="elena"):
    return {
        "topic": "Should AI replace developers?",
        "tool_context": "",
        "messages": [AIMessage(content="Some argument text.", name=speaker)],
        "claims_log": [],
        "turn_count": turn_count,
        "grounding_history": grounding_history or {},
        "evidence_log": [],
    }


def test_failed_assessment_does_not_zero_out_a_real_grounding_average(monkeypatch):
    # Turn 1 already produced a real grounding_score of 80, recorded in
    # grounding_history. Turn 2's assessment fails/truncates.
    monkeypatch.setattr(
        agents_module,
        "run_combined_assessment",
        lambda **kwargs: {
            "claims": [],
            "grounding_score": 0,
            "rebuttal": 0,
            "logic": 0,
            "clarity": 0,
            "citation_relevance": 0,
            "citation_credibility": 0,
            "engaged": "na",
            "contradiction_found": False,
            "assessment_status": "unavailable",
        },
    )

    state = _verify_state(grounding_history={"elena": [80.0], "marcus": []}, turn_count=1)
    result = verify_node(state)

    # The bug: this used to append the failed turn's 0 into the average,
    # dropping it from 80.0 to 40.0. It must stay 80.0 (unchanged).
    assert result["grounding_scores"]["elena"] == 80.0
    assert result["grounding_history"]["elena"] == [80.0]


def test_successful_assessment_still_updates_the_average(monkeypatch):
    monkeypatch.setattr(
        agents_module,
        "run_combined_assessment",
        lambda **kwargs: {
            "claims": [],
            "grounding_score": 60,
            "rebuttal": 7,
            "logic": 7,
            "clarity": 7,
            "citation_relevance": 7,
            "citation_credibility": 7,
            "engaged": "direct",
            "contradiction_found": False,
            "assessment_status": "ok",
        },
    )

    state = _verify_state(grounding_history={"elena": [80.0], "marcus": []}, turn_count=1)
    result = verify_node(state)

    assert result["grounding_scores"]["elena"] == 70.0  # avg(80, 60)
    assert result["grounding_history"]["elena"] == [80.0, 60.0]


# ---------------------------------------------------------------------
# score_node: assessment_status is surfaced for debuggability.
# ---------------------------------------------------------------------

def test_score_node_surfaces_assessment_status():
    ok_state = {
        "topic": "t",
        "tool_context": "",
        "messages": [AIMessage(content="x", name="elena")],
        "scores": {},
        "judge_history": [],
        "turn_count": 0,
        "max_turns": 2,
        "current_speaker": "elena",
        "last_assessment": {
            "rebuttal": 7, "logic": 7, "clarity": 7, "grounding_score": 70,
            "claims": [], "contradiction_found": False, "assessment_status": "ok",
        },
    }
    failed_state = dict(ok_state)
    failed_state["last_assessment"] = {
        "rebuttal": 0, "logic": 0, "clarity": 0, "grounding_score": 0,
        "claims": [], "contradiction_found": False, "assessment_status": "unavailable",
    }

    assert score_node(ok_state)["last_weighted"]["assessment_status"] == "ok"
    assert score_node(failed_state)["last_weighted"]["assessment_status"] == "unavailable"
