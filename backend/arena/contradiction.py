"""
Contradiction detection.

Checks whether an agent's new claims contradict something they
themselves said earlier in the same debate (not a disagreement with the
opponent - that's the whole point of a debate - but the same speaker
reversing their own position).
"""

import json
import re

from langchain_core.prompts import ChatPromptTemplate

from arena.config import load_llm

_CONTRADICTION_PROMPT = ChatPromptTemplate.from_template(
    """
You are checking ONE debater's internal consistency across a single
debate. You are NOT comparing them to their opponent.

{speaker}'s earlier claims in this debate:
{claim_history}

{speaker}'s NEWEST claim (this turn):
{new_claim}

Does the newest claim meaningfully contradict any of the earlier claims
listed above (the same speaker asserting the opposite, or a materially
inconsistent version, of something they already said)? Minor rephrasing,
narrowing, or adding nuance is NOT a contradiction.

Return ONLY valid JSON in exactly this shape:

{{
    "contradiction_found": false,
    "conflicting_claim": "",
    "explanation": ""
}}
"""
)


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


def check_contradiction(speaker: str, new_claims: list, claim_history: list) -> dict:
    """
    Check the new claims from this turn against the speaker's own prior
    claim history. Returns {"found": bool, "conflicting_claim": str,
    "explanation": str, "new_claim": str}. Never raises.
    """
    if not claim_history or not new_claims:
        return {"found": False}

    history_text = "\n".join(f"- {c}" for c in claim_history)
    new_claim_text = "\n".join(f"- {c}" for c in new_claims)

    try:
        chain = _CONTRADICTION_PROMPT | load_llm()
        response = chain.invoke(
            {
                "speaker": speaker.capitalize(),
                "claim_history": history_text,
                "new_claim": new_claim_text,
            }
        )
        parsed = _safe_json(response.content)

        if not parsed or not parsed.get("contradiction_found"):
            return {"found": False}

        return {
            "found": True,
            "conflicting_claim": parsed.get("conflicting_claim", ""),
            "explanation": parsed.get("explanation", ""),
            "new_claim": new_claim_text,
        }

    except Exception as e:
        print(f"[check_contradiction failed] {e}")
        return {"found": False}
