from langgraph.graph import StateGraph, START, END

from arena.state import DebateState
from arena.agents import (
    moderator_node,
    tool_node,

    elena_strategy_node,
    marcus_strategy_node,

    elena_node,
    marcus_node,

    verify_node,
    contradiction_node,

    score_node,
    summary_node,
)

# ---------------- Moderator Routing ----------------

def route_next(state):
    """Decide where to go after the moderator."""

    print(
        "route_next ->",
        state.get("current_speaker"),
        state.get("turn_count"),
    )

    if state.get("exit_requested"):
        return END

    if state.get("turn_count", 0) >= state.get("max_turns", 0):
        return "summary"

    pending = state.get("pending_interrupt")

    if pending == "elena":
        return "elena_tools"

    if pending == "marcus":
        return "marcus_tools"

    speaker = state.get("current_speaker", "elena")

    if speaker == "marcus":
        return "marcus_tools"

    return "elena_tools"

# ---------------- Score Routing ----------------

def route_after_score(state):
    """
    Decide whether to continue the debate or finish.

    IMPORTANT: this returns END (not "moderator") when the debate should
    continue. That yields control back to the *caller* (main.py) after
    every single turn, instead of looping the entire multi-turn debate
    inside one graph.invoke() call. This is what makes the moderator
    interrupt mechanism actually reachable: main.py re-invokes the graph
    once per turn, and can inject a moderator prompt (a redirect to a
    specific agent, a structured action, or an exit) in between every
    turn - not just once the whole debate has already finished.
    """

    if state.get("should_continue"):
        return END

    unresolved_contradictions = any(
        not contradiction.get("resolved")
        for contradiction in state.get("contradictions", [])
    )
    if unresolved_contradictions:
        return END

    return "summary"


# ---------------- Build Graph ----------------

def build_app(checkpointer=None):
    graph = StateGraph(DebateState)

    # =====================
    # Register Nodes
    # =====================

    graph.add_node("moderator", moderator_node)

    graph.add_node("elena_tools", tool_node)
    graph.add_node("marcus_tools", tool_node)

    graph.add_node("elena_strategy", elena_strategy_node)
    graph.add_node("marcus_strategy", marcus_strategy_node)

    graph.add_node("elena", elena_node)
    graph.add_node("marcus", marcus_node)

    # Claim verification + contradiction detection run for BOTH agents
    # (single shared node functions - they read the current speaker off
    # the last message, same pattern as tool_node/score_node).
    graph.add_node("verify", verify_node)
    graph.add_node("contradiction_check", contradiction_node)

    graph.add_node("score", score_node)

    graph.add_node("summary", summary_node)

    # =====================
    # Start
    # =====================

    graph.add_edge(START, "moderator")

    # =====================
    # Moderator Routing
    # =====================

    graph.add_conditional_edges(
        "moderator",
        route_next,
        {
            "elena_tools": "elena_tools",
            "marcus_tools": "marcus_tools",
            "summary": "summary",
            END: END,
        },
    )

    # =====================
    # Tool -> Strategy -> Agent
    # =====================

    graph.add_edge("elena_tools", "elena_strategy")
    graph.add_edge("elena_strategy", "elena")

    graph.add_edge("marcus_tools", "marcus_strategy")
    graph.add_edge("marcus_strategy", "marcus")

    # =====================
    # Agent -> Verify -> Contradiction Check -> Score
    # =====================

    graph.add_edge("elena", "verify")
    graph.add_edge("marcus", "verify")

    graph.add_edge("verify", "contradiction_check")
    graph.add_edge("contradiction_check", "score")

    # =====================
    # Score Routing
    # =====================

    graph.add_conditional_edges(
        "score",
        route_after_score,
        {
            END: END,
            "summary": "summary",
        },
    )

    # =====================
    # Finish
    # ====================

    graph.add_edge("summary", END)

    return graph.compile(checkpointer=checkpointer)
