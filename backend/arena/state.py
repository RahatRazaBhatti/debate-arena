from typing import Annotated, Dict, List, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from arena.tools import ToolEvent


class DebateState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

    topic: str

    current_speaker: str
    last_speaker: Optional[str]

    pending_interrupt: Optional[str]

    moderator_prompt: Optional[str]

    turn_count: int
    max_turns: int
    should_continue: bool

    scores: Dict[str, float]
    last_score: Optional[Dict[str, float]]
    judge_history: List[Dict]

    momentum_scores: Dict[str, float]
    last_momentum: Optional[Dict[str, float]]
    momentum_history: List[Dict]

    # Structured evidence: {title, url, snippet, agent, turn, query}
    evidence_log: List[Dict]

    # Claim verification + citation quality (per turn) and grounding score
    claims_log: List[Dict]
    grounding_scores: Dict[str, float]
    grounding_history: Dict[str, List[float]]
    last_verification: Optional[Dict]

    # Combined verify/judge/contradiction assessment from
    # evidence.run_combined_assessment (see arena/agents.py verify_node).
    # contradiction_node and score_node both read this back out of state
    # on the same turn - it MUST be declared here, or LangGraph silently
    # drops it when merging verify_node's return value into state (any
    # key a node returns that isn't part of this TypedDict schema is
    # discarded, not an error), which is what caused rebuttal/logic/
    # clarity/grounding_score to always come back as 0 downstream even
    # though verify_node computed them correctly.
    last_assessment: Optional[Dict]

    # Contradiction detection (a speaker vs. their own earlier claims)
    contradictions: List[Dict]

    # Weighted composite score - THIS decides the winner:
    # evidence grounding 35%, rebuttal 25%, logic 20%, engagement 10%, clarity 10%
    weighted_scores: Dict[str, float]
    last_weighted: Optional[Dict]

    # Debate phase (Opening / Evidence / Rebuttal / Cross-Examination / Closing)
    phase: str

    # Structured moderator action, alternative to free-text moderator_prompt
    moderator_action: Optional[str]

    # Persistence
    debate_id: Optional[str]

    winner: Optional[str]
    winning_margin: Optional[float]
    judge_winner: Optional[str]

    # Audit finding (Core Problem #12): margin-relative confidence label
    # ("HIGH" / "MODERATE" / "TOO_CLOSE_TO_CALL"), computed in
    # summary_node. Declared here for the same reason last_assessment is -
    # any key a node returns that isn't in this TypedDict is silently
    # dropped when LangGraph merges state.
    confidence: Optional[str]

    tool_log: List[ToolEvent]
    recent_tools: List[str]
    tool_context: Optional[str]
    cached_topic: Optional[str]
    cached_tool_context: Optional[str]
    argument_memory: Dict[str, List[str]]
    strategy_memory: Dict[str, str]


    final_summary: Optional[str]
    
    exit_requested: bool