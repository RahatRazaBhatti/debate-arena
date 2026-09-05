import os

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_groq import ChatGroq

load_dotenv(override=False)

DEFAULT_MODEL = "llama-3.1-8b-instant"
DEFAULT_TEMP = 0.4


class OfflineEchoLLM(FakeListChatModel):
    def __init__(self):
        super().__init__(
            responses=[
        # Strategy
        "This is an offline mock strategy.",

        # Elena argument
        "Homework should be banned because it causes unnecessary stress and reduces students' free time.",

        # Judge JSON (rebuttal/logic/clarity only - evidence is measured
        # separately by verify_node, not judged subjectively anymore)
        """
        {
            "rebuttal": 8,
            "logic": 8,
            "clarity": 9,
            "feedback": "Good argument."
        }
        """,

        # Marcus strategy
        "This is another offline strategy.",

        # Marcus argument
        "Homework should not be banned because it reinforces classroom learning.",

        # Judge JSON
        """
        {
            "rebuttal": 8,
            "logic": 7,
            "clarity": 8,
            "feedback": "Reasonable counter argument."
        }
        """,

        # Final Summary
        "Offline debate completed successfully."
    ]
        )


def load_llm() -> BaseChatModel:
    provider = os.getenv("MODEL_PROVIDER", "groq").lower()
    model_name = os.getenv("MODEL_NAME", DEFAULT_MODEL)
    groq_key = os.getenv("GROQ_API_KEY")

    if not getattr(load_llm, "_banner_printed", False):
        print("=" * 50)
        print("MODEL_PROVIDER:", provider)
        print("MODEL_NAME:", model_name)
        print("GROQ KEY FOUND:", bool(groq_key))
        print("=" * 50)
        load_llm._banner_printed = True

    if provider == "offline":
        # agents.py, contradiction.py, and evidence.py each call
        # load_llm() once at import time and keep the result as a
        # module-level `llm`. If we returned a fresh OfflineEchoLLM()
        # per call, each of those three modules would get its own
        # canned-response list with its own cursor starting back at
        # index 0 - so evidence.py's very first call would consume
        # response[0] ("This is an offline mock strategy.") instead of
        # the Judge JSON entry, and _safe_json would silently fail to
        # parse it, making offline-mode judge scores look broken even
        # after the real state-propagation bug is fixed. Sharing one
        # instance keeps the cursor advancing in true call order across
        # all three modules, matching the comments in OfflineEchoLLM.
        if not hasattr(load_llm, "_offline_singleton"):
            load_llm._offline_singleton = OfflineEchoLLM()
        return load_llm._offline_singleton

    if provider == "groq":
        if not groq_key:
            raise ValueError("GROQ_API_KEY is missing.")

        return ChatGroq(
            model=model_name,
            temperature=0.3,
            max_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "200")),
            api_key=groq_key,
        )

    raise ValueError(f"Unknown MODEL_PROVIDER '{provider}'")


def load_assessment_llm() -> BaseChatModel:
    """
    Dedicated LLM instance for the compact JSON claim-verification /
    AI-judge / contradiction call (arena/evidence.py::run_combined_assessment).

    Root-cause fix for a reproducible bug: that call and full debate-speech
    generation (agents.py) used to share ONE `load_llm()` instance, so they
    also shared ONE `max_tokens` budget (MAX_OUTPUT_TOKENS, default 200).
    Raising MAX_OUTPUT_TOKENS enough to stop debate speeches truncating
    does nothing to guarantee the JSON assessment call has enough room -
    and that call's JSON schema is non-trivial (up to 3 claims, each with
    a claim string + a 5-way verdict enum + an overclaim flag, plus 6
    scored fields and 3 contradiction fields). When Groq truncates that
    completion mid-JSON, `_safe_json` can't parse it, `run_combined_assessment`
    falls back to its all-zero fallback dict, and the result is a debate
    that visibly produced real evidence and arguments but shows
    "Evidence Grounding: 0.0%" / "AI Judge: 0.0" for the entire debate,
    every single turn - while the composite score still looks slightly
    non-zero because the rule-based Activity/engagement term never goes
    through the LLM at all.

    Bound to its OWN env var (ASSESSMENT_MAX_TOKENS) specifically so tuning
    one call's budget can never silently starve the other.
    """
    provider = os.getenv("MODEL_PROVIDER", "groq").lower()

    if provider == "offline":
        # Shares the same canned-response singleton as load_llm() - see
        # the comment on that function about why this must be shared,
        # not a fresh instance.
        return load_llm()

    if provider == "groq":
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY is missing.")
        model_name = os.getenv("MODEL_NAME", DEFAULT_MODEL)
        return ChatGroq(
            model=model_name,
            temperature=0.2,
            max_tokens=int(os.getenv("ASSESSMENT_MAX_TOKENS", "2000")),
            api_key=groq_key,
        )

    raise ValueError(f"Unknown MODEL_PROVIDER '{provider}'")