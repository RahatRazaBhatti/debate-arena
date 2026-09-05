"""
Debate phases.

Turns a flat "Elena -> Marcus -> Elena -> Marcus..." alternation into a
structured debate with distinct stages, each with its own instruction to
the agents. Purely a lookup over turn_count - no LLM calls, deterministic.

TURNS_PER_PHASE (env, default 1) controls debate length: 1 = 5 total
turns (one per side per phase), 2 = 10 total turns. Lower is cheaper on
API usage - this is the single biggest lever for free-tier Groq quotas,
since it scales every other LLM call linearly. Read dynamically (not
baked in at import time) so it can be changed per-run without a reimport.
"""

import os

_PHASE_DEFS = [
    (
        "Opening",
        "This is your OPENING statement. State your position clearly "
        "and confidently. Do not rebut your opponent yet - you are "
        "establishing your stance and your strongest initial reasoning.",
    ),
    (
        "Evidence",
        "This is the EVIDENCE phase. Present your strongest supporting "
        "evidence for your position. Lean heavily on the retrieved "
        "data, statistics, and sources available to you.",
    ),
    (
        "Rebuttal",
        "This is the REBUTTAL phase. Directly attack the weakest point "
        "in your opponent's most recent argument. Name or paraphrase "
        "their specific claim before explaining why it fails.",
    ),
    (
        "Cross-Examination",
        "This is CROSS-EXAMINATION. The moderator has posed a direct "
        "question. Answer it specifically and honestly before "
        "returning to your broader argument. Do not dodge the question.",
    ),
    (
        "Closing",
        "This is your CLOSING statement. Summarize your strongest "
        "points and explain why your position should prevail. Do not "
        "introduce major new evidence - synthesize what has already "
        "been argued.",
    ),
]


def _turns_per_phase() -> int:
    try:
        return max(1, int(os.getenv("TURNS_PER_PHASE", "1")))
    except ValueError:
        return 1


def _phases() -> list:
    turns = _turns_per_phase()
    return [{"name": name, "turns": turns, "instruction": instr} for name, instr in _PHASE_DEFS]


# Kept for anything that wants to inspect names/count without recomputing.
PHASES = _phases()


def total_turns() -> int:
    """Total turns across all phases (used as the default max_turns)."""
    return sum(p["turns"] for p in _phases())


def get_phase(turn_count: int) -> dict:
    """
    Return the phase for the turn ABOUT TO happen.

    turn_count is the number of turns already completed, so the upcoming
    turn is turn_count + 1.
    """
    phases = _phases()
    upcoming_turn = turn_count + 1
    cursor = 0

    for phase in phases:
        cursor += phase["turns"]
        if upcoming_turn <= cursor:
            return phase

    # Past the defined schedule (e.g. max_turns was overridden higher) -
    # fall back to repeating the closing phase's framing.
    return phases[-1]


def is_cross_examination(turn_count: int) -> bool:
    return get_phase(turn_count)["name"] == "Cross-Examination"


DEFAULT_CROSS_EXAM_QUESTIONS = [
    "What is the single strongest piece of evidence against your own position, and how do you address it?",
    "If you had to concede one point to your opponent, what would it be and why?",
]
