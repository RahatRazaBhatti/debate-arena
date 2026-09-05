from langgraph.graph import END

from arena.graph import route_next, route_after_score


# ----------------------------
# route_after_score()
# ----------------------------
# This is the core fix: previously it returned "moderator", which looped
# the ENTIRE multi-turn debate inside a single app.invoke() call and made
# the moderator interrupt unreachable from main.py. It must now return
# END so control comes back to the caller after every single turn.

def test_route_after_score_yields_control_when_continuing():
    state = {"should_continue": True}
    assert route_after_score(state) == END


def test_route_after_score_goes_to_summary_when_done():
    state = {"should_continue": False}
    assert route_after_score(state) == "summary"


# ----------------------------
# route_next()
# ----------------------------

def test_route_next_respects_exit():
    state = {"exit_requested": True, "turn_count": 0, "max_turns": 6}
    assert route_next(state) == END


def test_route_next_goes_to_summary_at_max_turns():
    state = {"exit_requested": False, "turn_count": 6, "max_turns": 6}
    assert route_next(state) == "summary"


def test_route_next_honors_moderator_redirect_to_elena():
    state = {
        "exit_requested": False,
        "turn_count": 1,
        "max_turns": 6,
        "pending_interrupt": "elena",
        "current_speaker": "marcus",  # would normally be marcus's turn
    }
    assert route_next(state) == "elena_tools"


def test_route_next_honors_moderator_redirect_to_marcus():
    state = {
        "exit_requested": False,
        "turn_count": 1,
        "max_turns": 6,
        "pending_interrupt": "marcus",
        "current_speaker": "elena",  # would normally be elena's turn
    }
    assert route_next(state) == "marcus_tools"


def test_route_next_default_alternation_without_interrupt():
    state = {
        "exit_requested": False,
        "turn_count": 1,
        "max_turns": 6,
        "pending_interrupt": None,
        "current_speaker": "marcus",
    }
    assert route_next(state) == "marcus_tools"
