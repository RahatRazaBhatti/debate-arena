from langchain_core.messages import HumanMessage

from arena.agents import (
    moderator_node,
    compress_argument,
    has_repeated_argument,
)


# ----------------------------
# Utility Functions
# ----------------------------

def test_compress_argument():
    text = "one two three four five six seven eight nine ten eleven twelve"

    result = compress_argument(text, max_words=5)

    assert result == "one two three four five..."


def test_has_repeated_argument_true():
    previous = [
        "AI improves education",
        "AI reduces workload",
    ]

    assert has_repeated_argument(
        "AI improves education significantly",
        previous,
    )


def test_has_repeated_argument_false():
    previous = [
        "AI improves education",
    ]

    assert not has_repeated_argument(
        "AI helps medical diagnosis",
        previous,
    )


# ----------------------------
# Moderator
# ----------------------------

def test_moderator_exit():
    state = {
        "moderator_prompt": "exit"
    }

    result = moderator_node(state)

    assert result["exit_requested"] is True


def test_moderator_interrupt_elena():
    state = {
        "moderator_prompt": "Elena respond now"
    }

    result = moderator_node(state)

    assert result["pending_interrupt"] == "elena"


def test_moderator_interrupt_marcus():
    state = {
        "moderator_prompt": "Marcus answer"
    }

    result = moderator_node(state)

    assert result["pending_interrupt"] == "marcus"


def test_moderator_message():
    state = {
        "moderator_prompt": "Continue debate"
    }

    result = moderator_node(state)

    assert isinstance(result["messages"][0], HumanMessage)