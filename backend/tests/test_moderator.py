from langchain_core.messages import HumanMessage

from arena.agents import moderator_node


def test_empty_prompt():
    state = {
        "moderator_prompt": "",
    }

    result = moderator_node(state)

    assert result == {}


def test_exit_command():
    state = {
        "moderator_prompt": "exit",
    }

    result = moderator_node(state)

    assert result["exit_requested"] is True


def test_quit_command():
    state = {
        "moderator_prompt": "quit",
    }

    result = moderator_node(state)

    assert result["exit_requested"] is True


def test_elena_interrupt():
    state = {
        "moderator_prompt": "Elena answer this.",
    }

    result = moderator_node(state)

    assert result["pending_interrupt"] == "elena"


def test_marcus_interrupt():
    state = {
        "moderator_prompt": "Marcus explain this.",
    }

    result = moderator_node(state)

    assert result["pending_interrupt"] == "marcus"


def test_human_message_added():
    state = {
        "moderator_prompt": "What is your evidence?",
    }

    result = moderator_node(state)

    assert isinstance(result["messages"][0], HumanMessage)
    assert result["messages"][0].content == "What is your evidence?"


def test_prompt_is_cleared():
    state = {
        "moderator_prompt": "continue",
    }

    result = moderator_node(state)

    assert result["moderator_prompt"] == ""