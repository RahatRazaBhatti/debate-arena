"""
Regression tests for the VERIFY -> SCORE state propagation bug.

Root cause (see arena/state.py): verify_node stashes its combined
claim-verification / AI-judge / contradiction assessment in
state["last_assessment"], which contradiction_node and score_node read
back out on the same turn. That key was never declared as a field on the
DebateState TypedDict, so LangGraph silently dropped it when merging
verify_node's return value into graph state (any key returned by a node
that isn't part of the schema passed to StateGraph(...) is discarded, not
an error). That made rebuttal/logic/clarity/grounding_score always come
back as 0 in score_node, and contradiction_node never fire, even though
verify_node computed everything correctly.

Calling score_node(state) or contradiction_node(state) directly with a
hand-built dict (as tests/test_score_node.py does) can't catch this class
of bug, because it bypasses LangGraph's channel merge entirely. These
tests instead run the real compiled graph (arena.graph.build_app) so the
schema is actually exercised.
"""

import os

import pytest
from langchain_core.messages import AIMessage

from arena.state import DebateState
from arena.graph import build_app
import arena.agents as agents_module


def _base_state(max_turns=1, topic="Should homework be banned?"):
    return {
        "messages": [],
        "topic": topic,
        "current_speaker": "elena",
        "last_speaker": None,
        "pending_interrupt": None,
        "moderator_prompt": "",
        "turn_count": 0,
        "max_turns": max_turns,
        "should_continue": True,
        "scores": {},
        "last_score": None,
        "judge_history": [],
        "tool_log": [],
        "recent_tools": [],
        "tool_context": None,
        "cached_topic": None,
        "cached_tool_context": None,
        "argument_memory": {"elena": [], "marcus": []},
        "strategy_memory": {"elena": "", "marcus": ""},
        "final_summary": None,
        "exit_requested": False,
    }


# ----------------------------------------------------------------------
# Schema guard: last_assessment must stay declared on DebateState, or
# this whole bug class comes back silently (LangGraph won't error).
# ----------------------------------------------------------------------

def test_debate_state_declares_last_assessment_field():
    assert "last_assessment" in DebateState.__annotations__, (
        "last_assessment must be declared on DebateState - verify_node "
        "writes it and contradiction_node/score_node read it back on the "
        "same turn. If LangGraph doesn't know about the field it silently "
        "drops it during the state merge, which is the exact bug this "
        "test suite regressed against."
    )


# ----------------------------------------------------------------------
# Minimal graph-merge test: proves ANY key a node returns that IS
# declared on the schema survives the hop to the next node. This is the
# generic mechanism, independent of any LLM/agents code.
# ----------------------------------------------------------------------

def test_langgraph_preserves_declared_schema_fields_between_nodes():
    from langgraph.graph import StateGraph, START, END

    def writer(state):
        return {"last_assessment": {"rebuttal": 7, "logic": 6, "clarity": 5}}

    def reader(state):
        assert state.get("last_assessment") == {
            "rebuttal": 7,
            "logic": 6,
            "clarity": 5,
        }
        return {}

    g = StateGraph(DebateState)
    g.add_node("writer", writer)
    g.add_node("reader", reader)
    g.add_edge(START, "writer")
    g.add_edge("writer", "reader")
    g.add_edge("reader", END)

    app = g.compile()
    app.invoke(_base_state())


# ----------------------------------------------------------------------
# Full graph, offline mode: VERIFY's judge fields must reach SCORE.
# ----------------------------------------------------------------------

@pytest.fixture
def offline_mode(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "offline")
    monkeypatch.setenv("LITE_MODE", "false")

    # arena.agents / arena.contradiction / arena.evidence each call
    # load_llm() once at import time and cache the result module-level,
    # so within a single pytest session they all share ONE OfflineEchoLLM
    # instance (see the fix in arena/config.py). That's correct for a
    # real single-debate process, but across many unrelated tests in one
    # pytest run its response cursor (`.i`) keeps advancing from
    # whatever earlier tests left it at. Reset it here so each test that
    # actually exercises canned LLM output starts from a known state.
    from arena import config as config_module

    if hasattr(config_module.load_llm, "_offline_singleton"):
        config_module.load_llm._offline_singleton.i = 0


def test_verify_judge_scores_reach_score_node_through_real_graph(offline_mode):
    """
    This is the exact bug from the report: VERIFY computes non-zero
    rebuttal/logic/clarity, but SCORE saw zeros. Run one real turn
    through the compiled graph (not score_node called directly) and
    assert the judge fields are NOT silently zeroed.
    """
    app = build_app()

    result = app.invoke(_base_state(max_turns=1))

    assert result["last_score"] is not None
    # The offline mock judge response is {"rebuttal": 8, "logic": 8, "clarity": 9}
    assert result["last_score"]["rebuttal"] > 0
    assert result["last_score"]["logic"] > 0
    assert result["last_score"]["clarity"] > 0

    assert result["last_weighted"]["rebuttal_x10"] > 0
    assert result["last_weighted"]["logic_x10"] > 0
    assert result["last_weighted"]["clarity_x10"] > 0

    # Composite must reflect more than just the engagement/activity term.
    assert result["last_weighted"]["composite"] > result["last_weighted"]["engagement_x10"] * 0.10


def test_contradiction_node_fires_through_real_graph(monkeypatch, offline_mode):
    """
    contradiction_node reads the same state["last_assessment"] key as
    score_node. Force a contradiction in the (mocked) combined assessment
    and confirm it actually gets recorded via the real graph - not just
    when contradiction_node is called directly with a hand-built dict.
    """

    def fake_combined_assessment(**kwargs):
        return {
            "claims": [],
            "grounding_score": 50,
            "citation_relevance": 5,
            "citation_credibility": 5,
            "rebuttal": 6,
            "logic": 6,
            "clarity": 6,
            "engaged": "direct",
            "contradiction_found": True,
            "conflicting_claim": "Homework is beneficial.",
            "contradiction_explanation": "Speaker previously argued the opposite.",
            # A mocked SUCCESSFUL assessment must include this - see
            # verify_node's grounding_history handling in arena/agents.py,
            # which now only records a turn's grounding_score into the
            # running average when assessment_status == "ok" (added to fix
            # a bug where truncated/failed LLM calls silently zeroed
            # Evidence Grounding). Omitting it here would make this test's
            # mock look like a failed call, which isn't what it simulates.
            "assessment_status": "ok",
        }

    monkeypatch.setattr(
        agents_module, "run_combined_assessment", fake_combined_assessment
    )

    app = build_app()
    result = app.invoke(_base_state(max_turns=1))

    assert len(result["contradictions"]) == 1
    assert result["contradictions"][0]["agent"] == "elena"
    assert result["contradictions"][0]["conflicting_claim"] == "Homework is beneficial."


def test_elena_and_marcus_scores_stay_separate_over_multiple_turns(offline_mode):
    """
    route_after_score intentionally returns END after every single turn
    (not just once the whole debate finishes) so main.py can re-invoke
    once per turn and inject moderator interrupts in between. Mirror that
    driving loop here instead of a single app.invoke() call.
    """
    app = build_app()

    state = _base_state(max_turns=2)
    while True:
        state = app.invoke(state)
        if not state.get("should_continue"):
            break

    assert state["scores"]["elena"] > 0
    assert state["scores"]["marcus"] > 0
    assert len(state["judge_history"]) == 2

    speakers = {entry["speaker"] for entry in state["judge_history"]}
    assert speakers == {"elena", "marcus"}


# ----------------------------------------------------------------------
# score_node unit test with the exact numbers from the bug report:
# grounding=80, rebuttal=6, logic=8, clarity=9 must NOT become zero.
# ----------------------------------------------------------------------

def test_score_node_consumes_reported_bug_values_correctly():
    from arena.agents import score_node

    state = {
        "topic": "Should homework be banned?",
        "tool_context": "",
        "messages": [AIMessage(content="Homework should be banned.", name="marcus")],
        "scores": {},
        "judge_history": [],
        "turn_count": 3,
        "max_turns": 5,
        "current_speaker": "marcus",
        "recent_tools": [],
        "momentum_scores": {},
        "momentum_history": [],
        "weighted_scores": {},
        "last_assessment": {
            "grounding_score": 80.0,
            "rebuttal": 6.0,
            "logic": 8.0,
            "clarity": 9.0,
        },
    }

    result = score_node(state)

    assert result["last_score"] == {"rebuttal": 6.0, "logic": 8.0, "clarity": 9.0}
    assert result["last_weighted"]["grounding_score"] == 80.0
    assert result["last_weighted"]["rebuttal_x10"] == 60.0
    assert result["last_weighted"]["logic_x10"] == 80.0
    assert result["last_weighted"]["clarity_x10"] == 90.0

    # composite must be driven by the real values, not just engagement
    expected_non_engagement = 0.35 * 80.0 + 0.25 * 60.0 + 0.20 * 80.0 + 0.10 * 90.0
    assert result["last_weighted"]["composite"] >= expected_non_engagement


# ----------------------------------------------------------------------
# Offline LLM cursor fix: load_llm() must return the SAME instance for
# MODEL_PROVIDER=offline across every module that calls it, or the
# canned response list gets consumed out of order per-module.
# ----------------------------------------------------------------------

def test_offline_llm_is_a_shared_singleton(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "offline")
    # reset the cached singleton for a clean test
    from arena import config as config_module

    if hasattr(config_module.load_llm, "_offline_singleton"):
        del config_module.load_llm._offline_singleton

    llm1 = config_module.load_llm()
    llm2 = config_module.load_llm()

    assert llm1 is llm2
