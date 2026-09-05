"""
Local persistence for debates.

Not the production-grade Postgres checkpointer LangGraph supports (that's
a genuine follow-up if this needs to run as a real service) - this is a
simpler local-file autosave that satisfies the actual FYP-scope
requirement: a crash or Ctrl-C mid-debate shouldn't lose the transcript,
and past debates should be reviewable/resumable.

Every turn is written to data/debates/<id>.json. Messages, tool events,
and other non-JSON-native objects are serialized to plain dicts on save
and reconstructed back into LangChain message / dataclass objects on load
so the graph can actually resume from them.
"""

import json
import uuid
import datetime
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from arena.tools import ToolEvent

DEBATES_DIR = Path("data/debates")


def new_debate_id() -> str:
    return uuid.uuid4().hex[:8]


def _serialize_state(state: dict) -> dict:
    out = dict(state)

    messages = []
    for m in state.get("messages", []):
        messages.append(
            {
                "type": m.__class__.__name__,
                "name": getattr(m, "name", None),
                "content": m.content,
            }
        )
    out["messages"] = messages

    out["tool_log"] = [
        {"agent": t.agent, "tool": t.tool, "args": t.args, "result": t.result}
        for t in state.get("tool_log", [])
    ]

    out["saved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return out


def _deserialize_state(data: dict) -> dict:
    out = dict(data)

    messages = []
    for m in data.get("messages", []):
        if m.get("type") == "HumanMessage":
            messages.append(HumanMessage(content=m.get("content", "")))
        else:
            messages.append(AIMessage(content=m.get("content", ""), name=m.get("name")))
    out["messages"] = messages

    out["tool_log"] = [
        ToolEvent(agent=t["agent"], tool=t["tool"], args=t["args"], result=t["result"])
        for t in data.get("tool_log", [])
    ]

    return out


def autosave(debate_id: str, state: dict) -> None:
    try:
        DEBATES_DIR.mkdir(parents=True, exist_ok=True)
        path = DEBATES_DIR / f"{debate_id}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(_serialize_state(state), f, indent=2, default=str)

    except Exception as e:
        print(f"[autosave failed] {e}")


def list_debates() -> list:
    DEBATES_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for path in sorted(DEBATES_DIR.glob("*.json"), reverse=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            results.append(
                {
                    "id": path.stem,
                    "topic": data.get("topic"),
                    "saved_at": data.get("saved_at"),
                    "turn_count": data.get("turn_count"),
                    "winner": data.get("winner"),
                    "final_summary": bool(data.get("final_summary")),
                }
            )
        except Exception:
            continue

    return results


def load_debate_raw(debate_id: str) -> dict:
    """Load the raw JSON as-saved (for replay - no need to reconstruct message objects)."""
    path = DEBATES_DIR / f"{debate_id}.json"

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_debate_for_resume(debate_id: str) -> dict:
    """Load and reconstruct into a state dict the graph can be invoked with again."""
    return _deserialize_state(load_debate_raw(debate_id))
