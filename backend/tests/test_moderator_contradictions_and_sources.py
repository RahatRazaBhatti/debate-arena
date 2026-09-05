import pytest

from arena.graph import route_after_score
from server import ModeratorRequest, _resolve_moderator_update, serialize_state


def test_expose_contradiction_resolves_latest_unresolved_item():
    state = {
        "contradictions": [
            {
                "agent": "elena",
                "turn": 2,
                "conflicting_claim": "earlier claim",
                "explanation": "claims conflict",
                "resolved": False,
            }
        ]
    }

    update = _resolve_moderator_update(
        state, ModeratorRequest(choice="EXPOSE_CONTRADICTION")
    )

    assert state["contradictions"][0]["resolved"] is True
    assert update["contradictions"][0]["resolved"] is True
    assert update["moderator_prompt"]


def test_expose_contradiction_without_unresolved_item_returns_400():
    state = {"contradictions": [{"resolved": True}]}

    with pytest.raises(Exception) as exc_info:
        _resolve_moderator_update(
            state, ModeratorRequest(choice="EXPOSE_CONTRADICTION")
        )

    assert getattr(exc_info.value, "status_code", None) == 400
    assert "no unresolved contradictions" in str(exc_info.value.detail)


def test_resolved_contradiction_allows_summary_routing():
    state = {
        "should_continue": False,
        "contradictions": [{"resolved": True}],
    }

    assert route_after_score(state) == "summary"


def test_serialize_state_preserves_source_fields_and_raw_messages():
    state = {
        "messages": [{"name": "elena", "content": "argument"}],
        "evidence_log": [
            {
                "title": "Research source",
                "url": "https://example.com/source",
                "snippet": "summary",
                "agent": "elena",
                "turn": 1,
                "query": "topic",
            }
        ],
        "tool_log": [],
        "turn_count": 1,
    }

    serialized = serialize_state(state)

    assert serialized["messages"][0]["content"] == "argument"
    assert serialized["evidence_log"][0]["title"] == "Research source"
    assert serialized["evidence_log"][0]["url"] == "https://example.com/source"
