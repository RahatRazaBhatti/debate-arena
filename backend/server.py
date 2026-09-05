"""
Web API layer for AI Debate Arena.

This file does NOT change any debate logic. It is a thin orchestration
layer around the existing, untouched `arena` package (the same
`build_app()` graph, `persistence` module, and `phases` module that
`main.py` already uses for the terminal version). It exposes that exact
same turn-by-turn invoke loop over HTTP so a web frontend can drive it
instead of a terminal prompt.

Run with:
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from arena.graph import build_app
from arena import persistence, phases
from main import build_initial_state, MODERATOR_MENU  # reuse, don't reimplement

app = FastAPI(title="AI Debate Arena API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory registry of live (in-progress) debate states, keyed by debate_id.
# Mirrors what main.py holds locally in its `state`/`result` variables --
# we just need it to survive between HTTP requests instead of loop iterations.
_graph_app = build_app()
_live_states: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Serialization helpers (JSON can't carry LangChain message objects or
# ToolEvent dataclasses directly)
# ---------------------------------------------------------------------------

def serialize_state(state: dict) -> dict:
    out = dict(state)

    messages = []
    for m in state.get("messages", []):
        if isinstance(m, dict):
            messages.append(
                {
                    "type": m.get("type", "Message"),
                    "name": m.get("name") or "Moderator",
                    "content": m.get("content", ""),
                }
            )
            continue
        messages.append(
            {
                "type": m.__class__.__name__,
                "name": getattr(m, "name", None) or "Moderator",
                "content": m.content,
            }
        )
    out["messages"] = messages

    out["tool_log"] = [
        dataclasses.asdict(t) if dataclasses.is_dataclass(t) else t
        for t in state.get("tool_log", [])
    ]
    out["evidence_log"] = [
        dict(source) if isinstance(source, dict) else source
        for source in state.get("evidence_log", [])
    ]

    phase_name = state.get("phase") or phases.get_phase(state.get("turn_count", 0))["name"]
    out["phase"] = phase_name

    unresolved = [c for c in state.get("contradictions", []) if not c.get("resolved")]
    out["unresolved_contradictions"] = unresolved

    # Not JSON serializable / not useful to the client
    out.pop("tool_context", None)
    out.pop("cached_tool_context", None)

    return out


def _run_turn(state: dict) -> dict:
    """Invoke the graph exactly once, same as main.py's run_debate loop body."""
    result = _graph_app.invoke(state)
    persistence.autosave(result.get("debate_id", "unknown"), result)
    _live_states[result["debate_id"]] = result
    return result


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class NewDebateRequest(BaseModel):
    topic: str
    max_turns: Optional[int] = None


class ModeratorRequest(BaseModel):
    # One of: a MODERATOR_MENU key ("1".."8"), an action name
    # (e.g. "CHALLENGE_ELENA"), or free-form text challenge.
    choice: Optional[str] = None
    text: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/moderator-actions")
def moderator_actions():
    """Expose the same structured menu main.py's CLI uses, for UI buttons."""
    return {
        key: {"action": action, "kind": kind}
        for key, (action, kind) in MODERATOR_MENU.items()
    }


@app.post("/api/debates")
def create_debate(req: NewDebateRequest):
    if not req.topic or not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic is required")

    state = build_initial_state(req.topic.strip(), req.max_turns)
    result = _run_turn(state)
    return serialize_state(result)


@app.get("/api/debates")
def list_debates():
    return persistence.list_debates()


@app.get("/api/debates/{debate_id}")
def get_debate(debate_id: str):
    state = _live_states.get(debate_id)
    if state is None:
        try:
            state = persistence.load_debate_raw(debate_id)
        except Exception:
            raise HTTPException(status_code=404, detail="debate not found")
        return serialize_state(state)
    return serialize_state(state)


@app.get("/api/debates/{debate_id}/full")
def get_debate_full(debate_id: str):
    """Raw saved JSON, for replay - same data main.py --replay reads."""
    try:
        return persistence.load_debate_raw(debate_id)
    except Exception:
        raise HTTPException(status_code=404, detail="debate not found")


@app.post("/api/debates/{debate_id}/resume")
def resume_debate(debate_id: str):
    try:
        state = persistence.load_debate_for_resume(debate_id)
    except Exception:
        raise HTTPException(status_code=404, detail="debate not found")

    if state.get("final_summary"):
        raise HTTPException(status_code=400, detail="debate already finished, use replay")

    state["debate_id"] = debate_id
    _live_states[debate_id] = state
    return serialize_state(state)


@app.post("/api/debates/{debate_id}/moderator")
def moderator_step(debate_id: str, req: ModeratorRequest):
    """
    Apply one moderator decision and advance the debate by exactly one turn -
    identical semantics to main.py's prompt_moderator() + run_debate() loop
    body, just driven by an HTTP call instead of input().
    """
    state = _live_states.get(debate_id)
    if state is None:
        raise HTTPException(status_code=404, detail="debate not found or not in-memory")

    if state.get("final_summary") or state.get("exit_requested"):
        raise HTTPException(status_code=400, detail="debate already finished")

    update = _resolve_moderator_update(state, req)
    state.update(update)

    if state.get("exit_requested"):
        persistence.autosave(state.get("debate_id", "unknown"), state)
        _live_states[debate_id] = state
        return serialize_state(state)

    result = _run_turn(state)
    return serialize_state(result)


def _resolve_moderator_update(state: dict, req: ModeratorRequest) -> Dict[str, Any]:
    choice = (req.choice or "").strip()

    action_name = choice.upper()
    if action_name == "REQUEST_CLARIFICATION":
        action_name = "ASK_CLARIFICATION"
    for key, (action, _kind) in MODERATOR_MENU.items():
        if action_name == action:
            choice = key
            break

    if choice in MODERATOR_MENU:
        action, kind = MODERATOR_MENU[choice]

        if kind is None:  # "1" - Continue
            return {"moderator_prompt": ""}

        if action == "END":
            return {"exit_requested": True}

        if action == "EXPOSE_CONTRADICTION":
            unresolved = [c for c in state.get("contradictions", []) if not c.get("resolved")]
            if not unresolved:
                raise HTTPException(status_code=400, detail="no unresolved contradictions")

            latest = unresolved[-1]
            latest["resolved"] = True
            challenge_text = (
                f"{latest['agent'].capitalize()}, your latest claim appears "
                f"inconsistent with what you said earlier "
                f"(\"{latest['conflicting_claim']}\"). {latest['explanation']} "
                f"Please clarify."
            )
            return {
                "moderator_prompt": challenge_text,
                "contradictions": state.get("contradictions", []),
            }

        return {"moderator_action": action}

    text = (req.text or "").strip()
    if text.lower() in ["exit", "quit"]:
        return {"exit_requested": True}

    return {"moderator_prompt": text}
