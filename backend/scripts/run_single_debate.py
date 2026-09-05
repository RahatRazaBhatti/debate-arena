"""
Run one debate for whichever topic is passed in, using whatever
MODEL_NAME / MODEL_PROVIDER is set in the environment for THIS process,
and print the result as a single JSON line to stdout.

Why a subprocess worker at all: arena/config.py's load_llm() is called
once at import time and cached as a module-level `llm` in agents.py,
evidence.py, and contradiction.py. Swapping models mid-process would
require refactoring that into a lazily-injected client - out of scope
here. Running each model in its own OS process sidesteps the problem
entirely (and is arguably a cleaner way to compare models anyway: fully
isolated state, no risk of cross-run leakage, real end-to-end latency).

Usage:
    MODEL_NAME=llama-3.3-70b-versatile python scripts/run_single_debate.py --topic "Should X?"
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.graph import build_app
from arena import phases


def run_one_debate(topic: str) -> dict:
    app = build_app()

    state = {
        "topic": topic,
        "messages": [],
        "current_speaker": "elena",
        "last_speaker": None,
        "pending_interrupt": None,
        "moderator_prompt": "",
        "moderator_action": "",
        "turn_count": 0,
        "max_turns": phases.total_turns(),
        "should_continue": True,
        "scores": {"elena": 0, "marcus": 0},
        "last_score": None,
        "judge_history": [],
        "momentum_scores": {"elena": 0, "marcus": 0},
        "last_momentum": None,
        "momentum_history": [],
        "evidence_log": [],
        "claims_log": [],
        "grounding_scores": {"elena": 0, "marcus": 0},
        "grounding_history": {"elena": [], "marcus": []},
        "last_verification": None,
        "contradictions": [],
        "weighted_scores": {"elena": 0, "marcus": 0},
        "last_weighted": None,
        "phase": "Opening",
        "debate_id": None,
        "winner": None,
        "winning_margin": None,
        "judge_winner": None,
        "tool_log": [],
        "recent_tools": [],
        "tool_context": None,
        "argument_memory": {"elena": [], "marcus": []},
        "strategy_memory": {"elena": "", "marcus": ""},
        "final_summary": None,
        "exit_requested": False,
    }

    start = time.time()

    # route_after_score yields control after every turn (the moderator-
    # interrupt fix) - so driving a full debate here is just repeated
    # invokes with no moderator input in between.
    while not state.get("final_summary") and not state.get("exit_requested"):
        state = app.invoke(state)

    elapsed = time.time() - start

    return {
        "topic": topic,
        "algorithm_winner": state.get("winner"),
        "weighted_elena": state.get("weighted_scores", {}).get("elena"),
        "weighted_marcus": state.get("weighted_scores", {}).get("marcus"),
        "judge_winner": state.get("judge_winner"),
        "elapsed_seconds": round(elapsed, 1),
        "contradictions_detected": len(state.get("contradictions", [])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()

    result = run_one_debate(args.topic)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
