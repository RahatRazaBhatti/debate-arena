import pytest

from arena.tools import (
    execute_math,
    simulate_growth,
    search_documents,
    query_dataset,
)


# ----------------------------
# execute_math()
# ----------------------------

def test_execute_math_addition():
    result = execute_math.invoke({"expression": "2+3"})
    assert result == "5"


def test_execute_math_power():
    result = execute_math.invoke({"expression": "2**5"})
    assert result == "32"


def test_execute_math_invalid():
    result = execute_math.invoke({"expression": "abc"})
    assert "Math Error" in result


# ----------------------------
# simulate_growth()
# ----------------------------

def test_simulate_growth():
    result = simulate_growth.invoke(
        {
            "initial_value": 100,
            "growth_rate": 10,
            "years": 2,
        }
    )

    assert "Year 1: 110.00" in result
    assert "Year 2: 121.00" in result


# ----------------------------
# search_documents()
# ----------------------------

def test_search_documents():
    result = search_documents.invoke(
        {
            "query": "AI"
        }
    )

    assert isinstance(result, str)


# ----------------------------
# query_dataset()
# ----------------------------

def test_query_dataset():
    result = query_dataset.invoke(
        {
            "metric": "population"
        }
    )

    assert isinstance(result, str)


# ----------------------------
# Per-turn evidence rotation (regression test)
# ----------------------------
# Previously tool_node cached results by topic alone, and since the topic
# never changes across a debate, every turn after the first silently reused
# turn 1's evidence. This checks that a speaker's Nth turn pulls a
# genuinely different web_search query than their (N-1)th turn.

def test_web_search_query_rotates_per_turn_for_same_speaker():
    from arena.agents import tool_node

    topic = "Should renewable energy subsidies be increased?"
    queries = []

    for turn_index in range(3):
        state = {
            "topic": topic,
            "current_speaker": "elena",
            "messages": [],
            "argument_memory": {"elena": ["prev arg"] * turn_index, "marcus": []},
            "strategy_memory": {"elena": "", "marcus": ""},
            "tool_log": [],
        }
        result = tool_node(state)
        query = next(
            (l.args for l in result["tool_log"] if l.tool == "web_search"),
            None,
        )
        queries.append(query)

    assert len(set(queries)) == len(queries), (
        f"web_search queries did not rotate per turn: {queries}"
    )