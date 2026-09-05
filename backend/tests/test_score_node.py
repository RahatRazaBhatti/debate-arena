from langchain_core.messages import AIMessage

from arena.agents import score_node


def test_score_node():
    """
    score_node no longer makes its own LLM call - it reads judge scores
    from state["last_assessment"], which verify_node populates in one
    combined call upstream (see evidence.run_combined_assessment). This
    cut the assessment stage from 3 LLM calls/turn down to 1.
    """

    state = {
        "topic": "Should homework be banned?",
        "tool_context": "",
        "messages": [
            AIMessage(
                content="Homework should be banned.",
                name="elena",
            )
        ],
        "scores": {},
        "judge_history": [],
        "turn_count": 0,
        "max_turns": 2,
        "current_speaker": "elena",
        "last_assessment": {
            "rebuttal": 9,
            "logic": 8,
            "clarity": 8,
            "grounding_score": 70,
        },
    }

    result = score_node(state)

    assert result["turn_count"] == 1

    # AI Judge subtotal is rebuttal + logic + clarity (out of 30)
    assert result["scores"]["elena"] == 25

    assert len(result["judge_history"]) == 1

    assert result["last_score"]["logic"] == 8

    assert result["current_speaker"] == "marcus"

    assert result["should_continue"] is True

    # Weighted composite (the actual winner-deciding score) should also
    # have been computed for this turn.
    assert "weighted_scores" in result
    assert result["weighted_scores"]["elena"] > 0


def test_score_node_lite_mode(monkeypatch):
    """In LITE_MODE, score_node should never touch last_assessment's LLM
    fields and should score purely off the free rule-based Activity Score."""

    monkeypatch.setenv("LITE_MODE", "true")

    state = {
        "topic": "Should homework be banned?",
        "tool_context": "",
        "messages": [
            AIMessage(
                content="Homework should be banned because 62 percent of students report stress.",
                name="elena",
            )
        ],
        "scores": {},
        "judge_history": [],
        "turn_count": 0,
        "max_turns": 2,
        "current_speaker": "elena",
        "last_assessment": None,
    }

    result = score_node(state)

    assert result["scores"]["elena"] == 0  # no judge call happened
    assert result["weighted_scores"]["elena"] >= 0