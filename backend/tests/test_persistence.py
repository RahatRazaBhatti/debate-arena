import shutil

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from arena.tools import ToolEvent
from arena import persistence


@pytest.fixture(autouse=True)
def temp_debates_dir(tmp_path, monkeypatch):
    test_dir = tmp_path / "debates"
    monkeypatch.setattr(persistence, "DEBATES_DIR", test_dir)
    yield test_dir
    shutil.rmtree(test_dir, ignore_errors=True)


def _sample_state():
    return {
        "topic": "Should AI replace human workers?",
        "messages": [
            AIMessage(content="AI improves efficiency.", name="marcus"),
            HumanMessage(content="Moderator challenge"),
        ],
        "turn_count": 3,
        "winner": "marcus",
        "final_summary": "Marcus won.",
        "tool_log": [
            ToolEvent(agent="marcus", tool="web_search", args="q", result="r"),
        ],
    }


def test_autosave_creates_file():
    debate_id = persistence.new_debate_id()
    persistence.autosave(debate_id, _sample_state())

    saved_path = persistence.DEBATES_DIR / f"{debate_id}.json"
    assert saved_path.exists()


def test_list_debates_includes_saved_debate():
    debate_id = persistence.new_debate_id()
    persistence.autosave(debate_id, _sample_state())

    debates = persistence.list_debates()
    ids = [d["id"] for d in debates]

    assert debate_id in ids


def test_load_debate_for_resume_reconstructs_messages():
    debate_id = persistence.new_debate_id()
    persistence.autosave(debate_id, _sample_state())

    resumed = persistence.load_debate_for_resume(debate_id)

    assert len(resumed["messages"]) == 2
    assert isinstance(resumed["messages"][0], AIMessage)
    assert resumed["messages"][0].name == "marcus"
    assert isinstance(resumed["messages"][1], HumanMessage)


def test_load_debate_for_resume_reconstructs_tool_log():
    debate_id = persistence.new_debate_id()
    persistence.autosave(debate_id, _sample_state())

    resumed = persistence.load_debate_for_resume(debate_id)

    assert len(resumed["tool_log"]) == 1
    assert isinstance(resumed["tool_log"][0], ToolEvent)
    assert resumed["tool_log"][0].agent == "marcus"


def test_new_debate_id_is_unique():
    ids = {persistence.new_debate_id() for _ in range(20)}
    assert len(ids) == 20
