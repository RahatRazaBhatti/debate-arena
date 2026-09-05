import json
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from arena.tools import default_tools, ToolEvent, raw_web_search
from arena.config import load_llm
from arena.prompts import (
    build_agent_prompt,
    build_strategy_prompt,
    AgentProfile,
    ELENA,
    MARCUS,
)
from arena.momentum import compute_momentum
from arena.research_planner import ResearchPlanner
from arena.evidence import parse_search_results_structured, run_combined_assessment
from arena import phases

import os

_planner = ResearchPlanner()


def compress_argument(text: str, max_words: int = 20) -> str:
    words = text.split()

    if len(words) <= max_words:
        return text

    return " ".join(words[:max_words]) + "..."


def has_repeated_argument(
    current_argument: str,
    previous_arguments: list,
    ) -> bool:

    current = current_argument.lower()

    for argument in previous_arguments:
        if argument.lower() in current:
            return True

    return False


def elena_node(state: dict) -> dict:
    print("===== ELENA NODE =====")
    return agent_node(ELENA, state)


def marcus_node(state: dict) -> dict:
    print("===== MARCUS NODE =====")
    return agent_node(MARCUS, state)


def strategy_node(profile: AgentProfile, state: dict) -> dict:
    print(f"===== {profile.name.upper()} STRATEGY =====")

    prompt = build_strategy_prompt()
    chain = prompt | load_llm()

    last_opponent = "No previous opponent argument."

    for msg in reversed(state["messages"]):
        if getattr(msg, "name", None) != profile.key:
            last_opponent = msg.content
            break

    memory = state.get(
        "argument_memory",
        {
            "elena": [],
            "marcus": [],
        },
    )

    previous = "\n".join(memory.get(profile.key, []))

    response = chain.invoke(
        {
            "topic": state["topic"],
            "side": "Support" if profile.key == "marcus" else "Oppose",
            "opponent_argument": last_opponent,
            "argument_memory": previous,
            "tool_context": state.get(
                "tool_context",
                "No evidence available.",
            ),
        }
    )

    print(response.content)

    strategies = dict(
        state.get(
            "strategy_memory",
            {
                "elena": "",
                "marcus": "",
            },
        )
    )

    strategies[profile.key] = response.content

    return {
        "strategy_memory": strategies
    }


def elena_strategy_node(state: dict) -> dict:
    return strategy_node(ELENA, state)


def marcus_strategy_node(state: dict) -> dict:
    return strategy_node(MARCUS, state)


def agent_node(profile: AgentProfile, state: dict) -> dict:
    print("=" * 50)
    print(f"AGENT: {profile.name}")

    prompt = build_agent_prompt(profile)
    chain = prompt | load_llm()

    last_opponent_message = "No previous opponent message."

    for msg in reversed(state["messages"]):
        if getattr(msg, "name", None) != profile.key:
            last_opponent_message = msg.content
            break

    # -----------------------------
    # Agent Memory
    # -----------------------------
    agent_memory = state.get(
        "argument_memory",
        {
            "elena": [],
            "marcus": [],
        },
    )

    previous_arguments = "\n".join(
        agent_memory.get(profile.key, [])
    )

    strategy_memory = state.get(
    "strategy_memory",
    {
        "elena": "",
        "marcus": "",
    },
    )

    current_strategy = strategy_memory.get(
        profile.key,
        "",
    )

    # -----------------------------
    # Debate Phase
    # -----------------------------
    current_phase = phases.get_phase(state.get("turn_count", 0))

    response = chain.invoke(
        {
            "topic": state["topic"],

            "tool_context": state.get(
                "tool_context",
                "No evidence available.",
            ),

            "recent_tools": ", ".join(
                state.get("recent_tools", [])
            ),

            "opponent_message": last_opponent_message,

            "history": state["messages"][-4:],

            "argument_memory": previous_arguments,

            "strategy": current_strategy,
            "input": state["topic"],

            "phase": current_phase["name"],
            "phase_instruction": current_phase["instruction"],
        }
    )

    print(response.content)
    print("=" * 50)

    # -----------------------------
    # Update Memory
    # -----------------------------
    updated_memory = {
        "elena": list(agent_memory.get("elena", [])),
        "marcus": list(agent_memory.get("marcus", [])),
    }

    compressed = compress_argument(response.content)

    is_repeat = has_repeated_argument(
        compressed,
        updated_memory.get(profile.key, []),
    )

    if is_repeat:
        print(f"⚠ {profile.name} repeated a previous argument.")

    updated_memory[profile.key].append(compressed)
    print("\n========== ARGUMENT MEMORY ==========")

    for agent, memories in updated_memory.items():
        print(f"\n{agent.upper()} MEMORY:")

        if not memories:
            print("  (empty)")
        else:
            for i, arg in enumerate(memories, 1):
                print(f"  {i}. {arg}")

    print("=====================================\n")
    return {
        "messages": [
            AIMessage(
                content=response.content,
                name=profile.key,
            )
        ],
        "argument_memory": updated_memory,
        "phase": current_phase["name"],
    }


def _load_stats() -> dict:
    stats_path = Path("data/stats.json")

    if not stats_path.exists():
        return {}

    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _find_matching_metrics(topic: str, stats: dict) -> list:
    """
    Find dataset metrics (query_dataset keys) that are actually relevant
    to the debate topic, so the stats tool is only invoked when it can
    contribute real evidence rather than being called blindly every turn.
    """
    topic_lower = topic.lower()
    matches = []

    for metric_key in stats.keys():
        words = [w for w in metric_key.split("_") if len(w) > 3]

        if any(word in topic_lower for word in words):
            matches.append(metric_key)

    return matches


def _first_number(text: str):
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def tool_node(state: dict) -> dict:
    print("===== TOOL NODE =====")

    topic = state.get("topic", "")
    speaker = state.get("current_speaker", "unknown")
    turn_number = state.get("turn_count", 0) + 1

    # -----------------------------
    # Research plan (drives targeted, PER-TURN-ROTATING search queries)
    # -----------------------------
    last_opponent_argument = "No previous opponent argument."

    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "name", None) != speaker:
            last_opponent_argument = msg.content
            break

    plan = _planner.create_plan(
        topic=topic,
        speaker=speaker,
        opponent_argument=last_opponent_argument,
        strategy=state.get("strategy_memory", {}).get(speaker, ""),
        argument_memory="\n".join(
            state.get("argument_memory", {}).get(speaker, [])
        ),
    )

    tools_by_name = {t.name: t for t in default_tools()}

    tool_context = []
    recent_tools = []
    tool_log = state.get("tool_log", [])
    evidence_log = list(state.get("evidence_log", []))

    def log_result(tool_name, args, result):
        result = str(result)[:700]
        tool_context.append(result)
        recent_tools.append(tool_name)
        tool_log.append(
            ToolEvent(agent=speaker, tool=tool_name, args=str(args), result=result)
        )
        return result

    # ---- shared stance-specific, per-turn-rotating query -----------------
    # Both web_search and search_documents should pull evidence relevant to
    # THIS speaker's stance and turn, not the raw topic verbatim. The
    # planner already builds stance-specific queries (Elena: "arguments
    # against X" / "negative effects of X"; Marcus: "arguments supporting
    # X" / "benefits of X") for web_search - reuse the exact same query
    # for search_documents instead of a fixed, speaker-independent
    # "topic" string, so local retrieval also varies by stance and turn
    # instead of both speakers always matching whichever document has the
    # most topic-generic keyword overlap.
    speaker_turn_index = len(
        state.get("argument_memory", {}).get(speaker, [])
    )

    if plan.search_queries:
        search_query = plan.search_queries[
            speaker_turn_index % len(plan.search_queries)
        ]
    else:
        search_query = f"{topic} evidence research studies statistics"

    # ---- web_search: rotate through the planner's stance-specific queries so
    # each of THIS speaker's turns pulls fresh evidence instead of repeating
    # turn 1's results. Also keep STRUCTURED (title/url/snippet) records for
    # source-level attribution, not just the flattened text blob. ----
    try:
        raw = raw_web_search(search_query)
        structured = parse_search_results_structured(
            raw, agent=speaker, turn=turn_number, query=search_query
        )
        evidence_log.extend(structured)

        if structured:
            formatted = "\n\n".join(
                f"Title: {r['title']}\nURL: {r['url']}\nSummary: {r['snippet']}"
                for r in structured
            )
        else:
            formatted = "No search results found."

        log_result("web_search", search_query, formatted)
    except Exception as e:
        print(f"[web_search failed] {e}")

    # ---- search_documents: use the same stance-specific query as web_search
    # (see above) rather than the raw topic, so local retrieval is also
    # stance- and turn-aware instead of identical for every speaker/turn. ----
    try:
        result = tools_by_name["search_documents"].invoke({"query": search_query})
        log_result("search_documents", search_query, result)
    except Exception as e:
        print(f"[search_documents failed] {e}")

    # ---- query_dataset: only for metrics genuinely relevant to the topic ----
    stats = _load_stats()
    matched_metrics = _find_matching_metrics(topic, stats)
    dataset_numeric_hits = {}

    for metric in matched_metrics:
        try:
            result = tools_by_name["query_dataset"].invoke({"metric": metric})
            log_result("query_dataset", metric, result)

            value = stats.get(metric)
            if isinstance(value, (int, float)):
                dataset_numeric_hits[metric] = value
        except Exception as e:
            print(f"[query_dataset failed for {metric}] {e}")

    # ---- execute_math: compare a dataset stat against a number the opponent cited ----
    opponent_number = _first_number(last_opponent_argument)

    if dataset_numeric_hits and opponent_number is not None:
        metric, value = next(iter(dataset_numeric_hits.items()))
        try:
            expression = f"{value} - {opponent_number}"
            result = tools_by_name["execute_math"].invoke({"expression": expression})
            annotated = (
                f"Comparative calculation: dataset value for '{metric}' is {value}. "
                f"Opponent cited {opponent_number}. Difference = {result}."
            )
            log_result("execute_math", expression, annotated)
        except Exception as e:
            print(f"[execute_math failed] {e}")

    # ---- simulate_growth: project a matched numeric stat forward as trend evidence ----
    if dataset_numeric_hits:
        metric, value = next(iter(dataset_numeric_hits.items()))
        try:
            result = tools_by_name["simulate_growth"].invoke(
                {
                    "initial_value": float(value),
                    "growth_rate": 2.5,
                    "years": 5,
                }
            )
            annotated = (
                f"5-year illustrative trend projection for '{metric}' "
                f"(starting at {value}, 2.5%/yr):\n{result}"
            )
            log_result("simulate_growth", metric, annotated)
        except Exception as e:
            print(f"[simulate_growth failed] {e}")

    final_context = "\n\n".join(tool_context)
    print("\n========== TOOL CONTEXT ==========")
    print(final_context.encode("ascii", "backslashreplace").decode("ascii"))
    print("==================================\n")

    return {
        "tool_context": final_context,
        "recent_tools": recent_tools,
        "tool_log": tool_log,
        "evidence_log": evidence_log,
    }


# ==========================================================
# Structured moderator actions
# ==========================================================
# Each action maps to a canned prompt template + which agent (if any) it
# should redirect to. "CONTINUE" and "END" are handled directly in
# main.py without touching the graph.

ACTION_TEMPLATES = {
    "CHALLENGE_ELENA": ("elena", "The moderator is challenging you: defend your position more rigorously and address its weakest point directly."),
    "CHALLENGE_MARCUS": ("marcus", "The moderator is challenging you: defend your position more rigorously and address its weakest point directly."),
    "REQUEST_EVIDENCE": (None, "The moderator is requesting a source: cite specific evidence for your previous claim."),
    "REQUEST_REBUTTAL": (None, "The moderator is requesting a rebuttal: directly address your opponent's most recent point before continuing."),
    "ASK_CLARIFICATION": (None, "The moderator is asking you to clarify: restate your last claim more precisely."),
}


def moderator_node(state: dict) -> dict:
    action = (state.get("moderator_action") or "").strip()
    prompt = state.get("moderator_prompt", "").strip()

    # -----------------------------
    # Structured action (menu choice) takes priority over free text
    # -----------------------------
    if action and action in ACTION_TEMPLATES:
        target, template_text = ACTION_TEMPLATES[action]

        return {
            "messages": [HumanMessage(content=template_text)],
            "pending_interrupt": target,
            "moderator_prompt": "",
            "moderator_action": "",
        }

    # -----------------------------
    # Auto cross-examination question if the moderator gave nothing and
    # the upcoming turn falls in the Cross-Examination phase
    # -----------------------------
    upcoming_phase = phases.get_phase(state.get("turn_count", 0))

    if not prompt and not action and upcoming_phase["name"] == "Cross-Examination":
        turn_index = state.get("turn_count", 0)
        question = phases.DEFAULT_CROSS_EXAM_QUESTIONS[
            turn_index % len(phases.DEFAULT_CROSS_EXAM_QUESTIONS)
        ]

        return {
            "messages": [HumanMessage(content=question)],
            "moderator_prompt": "",
        }

    if not prompt:
        return {}

    lower_prompt = prompt.lower()

    if "exit" in lower_prompt or "quit" in lower_prompt:
        return {
            "exit_requested": True,
        }

    pending_interrupt = None

    if "elena" in lower_prompt:
        pending_interrupt = "elena"

    elif "marcus" in lower_prompt:
        pending_interrupt = "marcus"

    return {
        "messages": [
            HumanMessage(content=prompt)
        ],
        "pending_interrupt": pending_interrupt,
        "moderator_prompt": "",
    }


# ==========================================================
# Claim verification + citation quality
# ==========================================================

# ==========================================================
# Claim verification + citation quality + AI Judge + contradiction check
# ==========================================================
# All THREE of these used to be separate LLM calls (verify_node,
# score_node's judge call, contradiction_node). They're now ONE call
# (evidence.run_combined_assessment), stashed in state["last_assessment"],
# which contradiction_node and score_node just read from - cutting the
# assessment stage from 3 LLM calls/turn down to 1.
#
# Set LITE_MODE=true in .env to skip this call entirely and score purely
# off the free, rule-based Activity Score (arena/momentum.py) - useful
# for stretching a free-tier Groq quota across more/longer debates.

def _lite_mode() -> bool:
    return os.getenv("LITE_MODE", "false").strip().lower() in ("1", "true", "yes")


def verify_node(state: dict) -> dict:
    print("===== VERIFY NODE =====")

    if _lite_mode():
        print("LITE_MODE on - skipping verification/judge/contradiction LLM call.")
        return {"last_assessment": None, "last_verification": None}

    last_message = state["messages"][-1]
    speaker = getattr(last_message, "name", "unknown")

    last_opponent = "No previous opponent speech."
    for msg in reversed(state["messages"][:-1]):
        if getattr(msg, "name", None) != speaker:
            last_opponent = msg.content
            break

    claims_log = state.get("claims_log", [])
    turn_number = state.get("turn_count", 0) + 1

    prior_claims = [
        c["claim"]
        for c in claims_log
        if c["agent"] == speaker and c["turn"] < turn_number and c.get("claim")
    ]

    # This turn's own retrieved web sources (agent+turn match), so
    # run_combined_assessment can blend the LLM's citation_credibility
    # guess with a rule-based domain-tier score instead of trusting the
    # guess alone (Core Problem #6).
    this_turn_evidence = [
        e for e in state.get("evidence_log", [])
        if e.get("agent") == speaker and e.get("turn") == turn_number
    ]

    assessment = run_combined_assessment(
        topic=state.get("topic", ""),
        speaker=speaker,
        speech=last_message.content,
        opponent_speech=last_opponent,
        evidence_context=state.get("tool_context", ""),
        claim_history=prior_claims,
        evidence_records=this_turn_evidence,
    )

    print(assessment)

    updated_claims_log = list(claims_log)
    for claim in assessment.get("claims", []):
        updated_claims_log.append(
            {
                "agent": speaker,
                "turn": turn_number,
                "claim": claim.get("claim", ""),
                "verdict": claim.get("verdict", "NOT_SUPPORTED"),
                "overclaim": bool(claim.get("overclaim", False)),
            }
        )

    grounding_history = dict(state.get("grounding_history", {}))
    grounding_history.setdefault("elena", [])
    grounding_history.setdefault("marcus", [])

    # Bug fix: only fold this turn's grounding_score into the running
    # average when the assessment actually completed ("ok"). Previously a
    # truncated/unparseable LLM response fell back to grounding_score=0,
    # and that 0 was pushed into the average exactly like a real
    # measurement - so a handful of truncated turns (or, before the fix in
    # arena/config.py::load_assessment_llm, potentially every turn) could
    # permanently drag Evidence Grounding to 0.0% even though real,
    # non-zero assessments happened on other turns. A missing measurement
    # must not silently become a measured zero.
    if assessment.get("assessment_status") == "ok":
        grounding_history[speaker] = grounding_history.get(speaker, []) + [
            assessment.get("grounding_score", 0)
        ]
    else:
        print(
            f"[verify_node] Turn {turn_number} ({speaker}): assessment "
            "unavailable - grounding average left unchanged this turn "
            "(not recorded as a zero)."
        )

    grounding_scores = {
        agent: (round(sum(vals) / len(vals), 2) if vals else 0)
        for agent, vals in grounding_history.items()
    }

    return {
        "claims_log": updated_claims_log,
        "last_assessment": assessment,
        "last_verification": assessment,  # kept for backward compatibility
        "grounding_history": grounding_history,
        "grounding_scores": grounding_scores,
    }


# ==========================================================
# Contradiction detection
# ==========================================================

def contradiction_node(state: dict) -> dict:
    print("===== CONTRADICTION NODE =====")

    assessment = state.get("last_assessment")

    if not assessment or not assessment.get("contradiction_found"):
        return {}

    last_message = state["messages"][-1]
    speaker = getattr(last_message, "name", "unknown")
    turn_number = state.get("turn_count", 0) + 1

    print(f"[WARNING] Contradiction detected for {speaker}")

    contradictions = list(state.get("contradictions", []))
    contradictions.append(
        {
            "agent": speaker,
            "turn": turn_number,
            "conflicting_claim": assessment.get("conflicting_claim", ""),
            "explanation": assessment.get("contradiction_explanation", ""),
            "resolved": False,
        }
    )

    return {"contradictions": contradictions}


# ==========================================================
# Score Node - weighted composite decides the winner
# ==========================================================
# Per the reweighted scoring spec:
#   Evidence quality/support   35%  <- verify_node's measured grounding_score
#   Rebuttal quality           25%  <- AI Judge (subjective, LLM-scored)
#   Logical consistency        20%  <- AI Judge (subjective, LLM-scored)
#   Direct engagement          10%  <- momentum.py's deterministic lexical overlap
#   Clarity                    10%  <- AI Judge (subjective, LLM-scored)
#
# Tool usage is intentionally NOT a direct winning signal anymore - it
# only earns credit indirectly, by producing evidence that raises the
# grounding score. The rule-based "momentum" score from before is still
# computed and shown (renamed to an Activity Score) but no longer decides
# the winner on its own.

def _safe_json(text: str) -> dict:
    text = text.strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


def score_node(state: dict) -> dict:
    print("===== SCORE NODE =====")

    last_message = state["messages"][-1]
    speaker = getattr(last_message, "name", "Unknown")

    print("Speaker:", speaker)
    print(last_message.content)
    last_opponent = "No previous opponent speech."

    for msg in reversed(state["messages"][:-1]):
        if getattr(msg, "name", None) != speaker:
            last_opponent = msg.content
            break

    # -----------------------------
    # AI Judge (subjective): rebuttal / logic / clarity -
    # now read from the ONE combined call made in verify_node instead of
    # a separate LLM call here (see arena/evidence.py::run_combined_assessment)
    # -----------------------------
    assessment = state.get("last_assessment") or {}

    result = {
        "rebuttal": assessment.get("rebuttal", 0),
        "logic": assessment.get("logic", 0),
        "clarity": assessment.get("clarity", 0),
    }

    judge_total = result["rebuttal"] + result["logic"] + result["clarity"]

    print("\n===== AI JUDGE (subjective) =====")
    print(result)
    print(f"Judge subtotal (out of 30): {judge_total}")
    print("==================================\n")

    scores = dict(state.get("scores", {}))
    scores.setdefault("elena", 0)
    scores.setdefault("marcus", 0)
    scores[speaker] += judge_total

    history = list(state.get("judge_history", []))
    history.append({"speaker": speaker, **result, "total": judge_total})

    # -----------------------------
    # Evidence Grounding (measured, from verify_node's combined call)
    # -----------------------------
    grounding_score = assessment.get("grounding_score", 0)  # 0-100

    # -----------------------------
    # Rule-based Momentum / Activity Score (kept, but NOT a winning signal
    # unless LITE_MODE is on - free, no LLM call either way)
    # -----------------------------
    momentum = compute_momentum(
        speech=last_message.content,
        opponent_speech=last_opponent,
        recent_tools=state.get("recent_tools", []),
    )

    momentum_scores = dict(state.get("momentum_scores", {}))
    momentum_scores.setdefault("elena", 0)
    momentum_scores.setdefault("marcus", 0)
    momentum_scores[speaker] += momentum["total"]

    momentum_history = list(state.get("momentum_history", []))
    momentum_history.append({"speaker": speaker, **momentum})

    print("\n===== ACTIVITY SCORE (rule-based, informational only) =====")
    print(momentum)
    print("=============================================================\n")

    # -----------------------------
    # Weighted composite -> THIS decides the winner
    # -----------------------------
    engagement_0_100 = min(momentum["engagement"], 10) * 10  # momentum engagement caps at 10

    if _lite_mode():
        # No LLM assessment this turn - fall back to the free, rule-based
        # Activity Score as the sole decider (scaled to a comparable 0-100ish
        # range: momentum.total maxes at 40, so *2.5 roughly matches the
        # composite's scale).
        composite = round(momentum["total"] * 2.5, 2)
        contradiction_penalty = 0
        overclaim_penalty = 0
    else:
        composite = (
            0.35 * grounding_score
            + 0.25 * (result["rebuttal"] * 10)
            + 0.20 * (result["logic"] * 10)
            + 0.10 * engagement_0_100
            + 0.10 * (result["clarity"] * 10)
        )

        # Audit finding (Core Problems #8/#9/#11): contradictions and
        # overclaimed inferences were detected and displayed, but never
        # actually cost the speaker anything in the composite. Penalize
        # them directly instead of leaving them purely informational.
        # -10 composite points per contradiction *newly* flagged this
        # turn (contradiction_node only appends when the combined
        # assessment found one THIS turn, so this can't double-count
        # earlier turns). -5 per claim THIS turn flagged as an
        # unsupported inference stacked on real evidence.
        contradiction_penalty = 10 if assessment.get("contradiction_found") else 0
        overclaim_penalty = 5 * sum(
            1 for c in assessment.get("claims", []) if c.get("overclaim")
        )

        composite = round(max(0.0, composite - contradiction_penalty - overclaim_penalty), 2)

    weighted_scores = dict(state.get("weighted_scores", {}))
    weighted_scores.setdefault("elena", 0)
    weighted_scores.setdefault("marcus", 0)
    weighted_scores[speaker] += composite

    last_weighted = {
        "speaker": speaker,
        "grounding_score": grounding_score,
        "rebuttal_x10": result["rebuttal"] * 10,
        "logic_x10": result["logic"] * 10,
        "engagement_x10": engagement_0_100,
        "clarity_x10": result["clarity"] * 10,
        "contradiction_penalty": contradiction_penalty,
        "overclaim_penalty": overclaim_penalty,
        "composite": composite,
        # Surfaces whether rebuttal/logic/clarity/grounding above are real
        # measurements ("ok") or this turn's LLM assessment was unavailable
        # (parse failure / truncated JSON / API error), in which case they
        # contributed 0 to this turn only and should not be read as "the
        # judge rated this turn zero."
        "assessment_status": assessment.get("assessment_status", "ok"),
    }

    print("\n===== WEIGHTED COMPOSITE (decides winner) =====")
    print(last_weighted)
    print("Cumulative:", weighted_scores)
    print("=================================================\n")

    turn_count = state.get("turn_count", 0) + 1
    max_turns = state.get("max_turns", phases.total_turns())

    current = state.get("current_speaker", "elena")
    next_speaker = "marcus" if current == "elena" else "elena"

    return {
        "turn_count": turn_count,
        "should_continue": turn_count < max_turns,
        "last_speaker": current,
        "current_speaker": next_speaker,
        # moderator redirects are single-turn, not sticky: clear it so
        # normal alternation resumes on the next turn unless the
        # moderator redirects again
        "pending_interrupt": None,
        "scores": scores,
        "last_score": result,
        "judge_history": history,
        "momentum_scores": momentum_scores,
        "last_momentum": momentum,
        "momentum_history": momentum_history,
        "weighted_scores": weighted_scores,
        "last_weighted": last_weighted,
    }


def summary_node(state: dict) -> dict:
    print("===== SUMMARY NODE =====")

    # -----------------------------
    # Build transcript
    # -----------------------------
    debate = []

    for msg in state["messages"]:
        speaker = getattr(msg, "name", "Unknown")
        debate.append(f"{speaker}: {msg.content}")

    transcript = "\n\n".join(debate)

    # -----------------------------
    # Final Scores
    # -----------------------------
    # Weighted composite (evidence grounding 35% + judge 55% + engagement 10%)
    # is the PRIMARY, decisive scoreboard.
    weighted_scores = state.get("weighted_scores", {"elena": 0, "marcus": 0})
    winner = max(weighted_scores, key=weighted_scores.get)
    margin = abs(weighted_scores["elena"] - weighted_scores["marcus"])

    # Audit finding (Core Problem #12): the system always named a winner
    # with no sense of how decisive that margin actually was. Band the
    # margin against the total points actually in play this debate so a
    # 2-point gap out of 400 cumulative points doesn't read the same as a
    # 2-point gap out of 40.
    total_points = weighted_scores["elena"] + weighted_scores["marcus"]
    margin_ratio = (margin / total_points) if total_points > 0 else 0.0
    if margin_ratio < 0.05:
        confidence = "TOO_CLOSE_TO_CALL"
    elif margin_ratio < 0.15:
        confidence = "MODERATE"
    else:
        confidence = "HIGH"

    # AI Judge alone (subjective, informational) and Activity Score
    # (rule-based, informational) are both kept and surfaced but do not
    # decide the winner on their own anymore.
    scores = state.get("scores", {"elena": 0, "marcus": 0})
    judge_winner = max(scores, key=scores.get)

    momentum_scores = state.get("momentum_scores", {"elena": 0, "marcus": 0})

    # Bug fix: the summary prompt used to receive only the cumulative
    # composite (weighted_scores) and judge_winner, never the actual
    # Evidence Grounding / AI Judge sub-scores shown on the dashboard. The
    # model would still write plausible-sounding component-level claims
    # ("scored strongest on Evidence Grounding and Rebuttal") because
    # nothing stopped it from inferring that from the winner's name alone
    # - producing exactly the kind of summary/dashboard mismatch this was
    # reported against (dashboard showed 0.0% grounding while the summary
    # praised "strong evidence grounding"). Pass the real numbers so any
    # component-level claim is either grounded in them or the model has no
    # basis to make it.
    grounding_scores = state.get("grounding_scores", {"elena": 0, "marcus": 0})

    contradictions = state.get("contradictions", [])

    # Audit finding (Core Problem #13): the summary used to be told only
    # a contradiction COUNT and had to free-associate "what was proven" -
    # risking a hallucinated "no contradictions" or "stronger evidence"
    # claim that doesn't match the actual claims_log. Build a real,
    # non-hallucinated verdict breakdown from claims_log instead and hand
    # it to the model as data, not as something to infer from the
    # transcript alone.
    claims_log = state.get("claims_log", [])

    def _verdict_breakdown(agent: str) -> dict:
        counts = {}
        for c in claims_log:
            if c.get("agent") == agent:
                v = c.get("verdict", "NOT_SUPPORTED")
                counts[v] = counts.get(v, 0) + 1
        return counts

    claim_breakdown = {
        "elena": _verdict_breakdown("elena"),
        "marcus": _verdict_breakdown("marcus"),
    }
    overclaimed = [
        f"{c['agent'].capitalize()}: {c['claim']}"
        for c in claims_log
        if c.get("overclaim")
    ][:5]

    # -----------------------------
    # Summary Prompt
    # -----------------------------
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are an impartial debate analyst.

The debate winner has ALREADY been decided by a weighted composite score:
Evidence Grounding 35%, Rebuttal 25%, Logical Consistency 20%, Direct
Engagement 10%, Clarity 10% (with point deductions for contradictions
and overclaimed inferences) - NOT by you.

Winner (by weighted composite):
{winner}

Confidence in this result: {confidence}
(TOO_CLOSE_TO_CALL means the margin was small relative to total points -
if so, say so plainly instead of overstating how decisive the result was.)

Final Weighted Scores:
{weighted_scores}

Winning Margin:
{margin}

For additional context:
- Evidence Grounding Score per agent (0-100, measured): {grounding_scores}
- AI Judge cumulative subjective score per agent (favored: {judge_winner}): {scores}
- Activity Score (tool use / numbers / engagement / verbosity): {momentum_scores}
- Contradictions detected: {contradiction_count}
- Claim verdict counts by agent (from actual fact-checking this debate,
  not your own read of the transcript) - use ONLY this data to describe
  what was proven/unproven, do not invent additional unsupported claims
  or additional contradictions beyond what's listed here:
  {claim_breakdown}
- Claims flagged as overclaimed (a narrower supported fact stretched into
  a bigger conclusion the evidence didn't establish): {overclaimed}

Debate Transcript:
{transcript}

Your job is NOT to choose the winner.

Instead explain WHY the weighted-composite winner deserved to win, and
briefly note whether the AI Judge's subjective opinion agreed. Mention
contradictions and overclaimed claims ONLY if the data above shows any -
never state "no contradictions" or "stronger evidence" as a generic
compliment without it being grounded in the data provided. In
particular: only say a specific agent had "stronger evidence grounding"
or "won on rebuttal" if the Evidence Grounding Score or AI Judge score
above actually shows that for that agent - if both scores are 0 or
missing, say the composite margin came from Activity/Engagement instead
of inventing a grounding/rebuttal explanation.

Produce the following sections:

1. Debate Summary

2. Why the winner won (reference the confidence level)

3. What was proven vs. partially supported vs. unproven (from the claim
   verdict counts above)

4. Best evidence used

5. Weakest argument / contradictions / overclaims (if any)

Maximum 150 words.

Be objective.
                """,
            ),
        ]
    )

    chain = prompt | load_llm()

    try:
        summary = chain.invoke(
            {
                "winner": winner.capitalize(),
                "confidence": confidence,
                "weighted_scores": weighted_scores,
                "margin": margin,
                "judge_winner": judge_winner.capitalize(),
                "grounding_scores": grounding_scores,
                "scores": scores,
                "momentum_scores": momentum_scores,
                "contradiction_count": len(contradictions),
                "claim_breakdown": claim_breakdown,
                "overclaimed": overclaimed or "(none)",
                "transcript": transcript,
            }
        )
        summary_content = summary.content
    except Exception as e:
        print(f"[summary generation failed] {e}")
        summary_content = (
            f"{winner.capitalize()} won by weighted composite score "
            f"({weighted_scores}), confidence: {confidence}. "
            f"Summary generation failed: {e}"
        )

    print("\n========== FINAL RESULT ==========")
    print(f"Winner (weighted composite) : {winner.capitalize()}")
    print(f"Confidence                   : {confidence}")
    print(f"Weighted Scores              : {weighted_scores}")
    print(f"Margin                       : {margin}")
    print(f"AI Judge favored             : {judge_winner.capitalize()}")
    print(f"Activity Scores              : {momentum_scores}")
    print(f"Contradictions detected      : {len(contradictions)}")
    print("===================================\n")

    print(summary_content)

    # -----------------------------
    # Debate Analytics
    # -----------------------------
    history = state.get("judge_history", [])

    print("\n========== DEBATE ANALYTICS ==========\n")

    print("Final Weighted Scores")
    print(f"Elena : {weighted_scores['elena']}")
    print(f"Marcus: {weighted_scores['marcus']}")
    print(f"Winner : {winner.capitalize()}")
    print(f"Winning Margin : {margin}")

    print("\n--------------------------------------")

    categories = ["rebuttal", "logic", "clarity"]

    for category in categories:

        elena_scores = [h[category] for h in history if h["speaker"] == "elena"]
        marcus_scores = [h[category] for h in history if h["speaker"] == "marcus"]

        elena_avg = sum(elena_scores) / len(elena_scores) if elena_scores else 0
        marcus_avg = sum(marcus_scores) / len(marcus_scores) if marcus_scores else 0

        print(f"\n{category.upper()}")
        print(f"Elena : {elena_avg:.2f}")
        print(f"Marcus: {marcus_avg:.2f}")

    print("\n======================================\n")

    state["final_summary"] = summary_content
    state["winner"] = winner
    state["winning_margin"] = margin
    state["judge_winner"] = judge_winner
    state["confidence"] = confidence

    return state
