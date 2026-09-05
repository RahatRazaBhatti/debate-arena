"""
Rule-based, transparent "momentum" scoring.

The AI Judge in `agents.score_node` gives a rich but subjective LLM
impression of each turn. This module implements the *other* half of the
scoring system: a fully deterministic, auditable score built from four
explicit signals, computed directly off the raw turn data (no LLM call):

    1. Tool use        - did the speaker's turn actually get grounded in
                          a retrieval/lookup tool this round?
    2. Concrete numbers - does the speech cite quantifiable data
                          (percentages, counts, statistics)?
    3. Engagement       - does the speech directly reference/engage with
                          the opponent's previous point (lexical overlap)?
    4. Verbosity        - is the turn a substantive, on-brief length
                          (neither a one-liner nor a rambling wall of text)?

Because every component is a pure function of the speech text + tool log,
the same transcript always reproduces the same score - that reproducibility
is what makes it "auditable" rather than a black-box impression.
"""

import re
import string

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "because",
    "of", "to", "in", "on", "for", "with", "as", "is", "are", "was",
    "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "by", "at", "from", "not", "no", "you", "your", "i",
    "we", "our", "they", "their", "he", "she", "his", "her", "which",
    "who", "what", "when", "where", "how", "why", "do", "does", "did",
    "can", "could", "would", "should", "will", "shall", "has", "have",
    "had", "there", "also", "than", "more", "most", "such", "only",
    "just", "about",
}

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")

# ---- Component weights / caps (documented so the scoring is transparent) ----

TOOL_USE_POINTS_PER_TOOL = 5
TOOL_USE_CAP = 15

NUMBER_POINTS_EACH = 2
NUMBER_CAP = 10

ENGAGEMENT_CAP = 10

VERBOSITY_CAP = 5
VERBOSITY_TARGET_MIN = 90
VERBOSITY_TARGET_MAX = 140


def _significant_words(text: str) -> set:
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return {w for w in text.split() if w not in _STOPWORDS and len(w) > 3}


def score_tool_use(recent_tools: list) -> float:
    """Points for actually invoking evidence tools this turn."""
    return min(len(recent_tools) * TOOL_USE_POINTS_PER_TOOL, TOOL_USE_CAP)


def score_concrete_numbers(speech: str) -> float:
    """Points for citing quantifiable data in the speech."""
    matches = _NUMBER_RE.findall(speech or "")
    return min(len(matches) * NUMBER_POINTS_EACH, NUMBER_CAP)


def score_engagement(speech: str, opponent_speech: str) -> float:
    """
    Points for directly engaging with the opponent's previous point,
    measured as lexical overlap between the two speeches.
    """
    if not opponent_speech or "No previous" in opponent_speech or "No opponent" in opponent_speech:
        return 0.0

    speech_words = _significant_words(speech or "")
    opponent_words = _significant_words(opponent_speech)

    if not opponent_words:
        return 0.0

    overlap = speech_words & opponent_words
    ratio = len(overlap) / len(opponent_words)

    return round(min(ratio, 1.0) * ENGAGEMENT_CAP, 2)


def score_verbosity(speech: str) -> float:
    """
    Points for landing in the target substantive-response range
    (90-140 words, matching the agents' own output-length instructions
    in prompts.py). Falls off linearly outside the range rather than
    being a hard cutoff.
    """
    word_count = len((speech or "").split())

    if word_count <= 0:
        return 0.0

    if VERBOSITY_TARGET_MIN <= word_count <= VERBOSITY_TARGET_MAX:
        return float(VERBOSITY_CAP)

    if word_count < VERBOSITY_TARGET_MIN:
        ratio = word_count / VERBOSITY_TARGET_MIN
    else:
        overflow = word_count - VERBOSITY_TARGET_MAX
        ratio = max(0.0, 1 - (overflow / VERBOSITY_TARGET_MAX))

    return round(max(0.0, ratio) * VERBOSITY_CAP, 2)


def compute_momentum(speech: str, opponent_speech: str, recent_tools: list) -> dict:
    """
    Compute the full, auditable momentum breakdown for one turn.

    Returns the four component scores plus their total. Every value here
    is independently re-derivable from the raw turn data - that's the
    "transparent, rule-based" measure the debate is scored against,
    distinct from (and computed alongside) the subjective AI Judge score.
    """
    tool_use = score_tool_use(recent_tools or [])
    numbers = score_concrete_numbers(speech)
    engagement = score_engagement(speech, opponent_speech)
    verbosity = score_verbosity(speech)

    return {
        "tool_use": tool_use,
        "concrete_numbers": numbers,
        "engagement": engagement,
        "verbosity": verbosity,
        "total": round(tool_use + numbers + engagement + verbosity, 2),
    }
