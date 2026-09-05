from arena.graph import build_app


def test_build_app():
    app = build_app()

    assert app is not None
    assert hasattr(app, "invoke")


def test_offline_debate():

    app = build_app()

    state = {
        "messages": [],
        "topic": "Should homework be banned?",

        "current_speaker": "elena",
        "last_speaker": None,

        "pending_interrupt": None,

        "moderator_prompt": "",

        "turn_count": 0,
        "max_turns": 2,

        "should_continue": True,

        "scores": {},
        "last_score": None,

        "judge_history": [],

        "tool_log": [],
        "recent_tools": [],
        "tool_context": None,
        "cached_topic": None,
        "cached_tool_context": None,

        "argument_memory": {
            "elena": [],
            "marcus": [],
        },

        "strategy_memory": {
            "elena": "",
            "marcus": "",
        },

        "final_summary": None,

        "exit_requested": False,
    }

    result = app.invoke(state)

    assert result is not None

    assert "turn_count" in result

    assert result["turn_count"] >= 1

    assert "scores" in result

    assert "judge_history" in result