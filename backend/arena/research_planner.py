import re
from dataclasses import dataclass, field

# Audit finding (Core Problem #5): the original planner only ever built
# queries off the debate TOPIC ("arguments against X" / "arguments
# supporting X"), so a mid-debate rebuttal turn fetched the same kind of
# evidence as the opening turn instead of evidence targeted at whatever
# the opponent had just specifically claimed. _key_phrase() pulls a short,
# content-bearing fragment out of the opponent's actual last argument so
# a claim-targeted query can be added alongside (not instead of) the
# existing topic-level queries.

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "because",
    "of", "to", "in", "on", "for", "with", "as", "is", "are", "was",
    "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "by", "at", "from", "not", "no", "you", "your", "i",
    "we", "our", "they", "their", "he", "she", "his", "her", "which",
    "who", "what", "when", "where", "how", "why", "do", "does", "did",
    "can", "could", "would", "should", "will", "shall", "has", "have",
    "had", "there", "also", "than", "more", "most", "such", "only",
    "just", "about", "however", "therefore", "suggests", "suggest",
}

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']+")

_NO_OPPONENT_PREFIX = "no previous opponent"


def _key_phrase(text: str, max_words: int = 6) -> str:
    """Extract up to max_words content-bearing words from the opponent's
    most recent argument, preserving order of first appearance, so a
    query can target what was actually just said instead of the topic
    in the abstract. Returns "" if there's no real opponent text yet
    (e.g. the opening turn - callers use various "No previous opponent
    ...." placeholder strings, so match on the shared prefix rather than
    one exact string)."""
    if not text or text.strip().lower().startswith(_NO_OPPONENT_PREFIX):
        return ""

    words = []
    seen = set()
    for raw in _WORD_RE.findall(text):
        word = raw.lower()
        if word in _STOPWORDS or word in seen or len(word) <= 2:
            continue
        seen.add(word)
        words.append(word)
        if len(words) >= max_words:
            break

    return " ".join(words)


@dataclass
class ResearchPlan:
    """
    Plan generated before tool execution.
    """

    search_queries: list[str] = field(default_factory=list)

    required_tools: list[str] = field(default_factory=list)

    evidence_goals: list[str] = field(default_factory=list)

    reasoning_focus: str = ""

    rebuttal_focus: str = ""

    priority: str = "medium"


class ResearchPlanner:

    def create_plan(
        self,
        topic: str,
        speaker: str,
        opponent_argument: str,
        strategy: str,
        argument_memory: str,
    ) -> ResearchPlan:

        plan = ResearchPlan()

        topic_lower = topic.lower()

        if speaker.lower() == "elena":

            plan.search_queries = [
                f"arguments against {topic_lower}",
                f"negative effects of {topic_lower}",
                f"{topic_lower} peer reviewed studies",
                f"{topic_lower} statistics",
            ]

            plan.evidence_goals = [
                "counter evidence",
                "scientific studies",
                "statistics",
            ]

        else:

            plan.search_queries = [
                f"arguments supporting {topic_lower}",
                f"benefits of {topic_lower}",
                f"{topic_lower} peer reviewed studies",
                f"{topic_lower} statistics",
            ]

            plan.evidence_goals = [
                "supporting evidence",
                "scientific studies",
                "statistics",
            ]

        # Claim-targeted query (Core Problem #5): additive, appended after
        # the topic-level queries above so both speakers still get their
        # existing broad coverage, plus - once there's an actual opponent
        # argument to react to - a query aimed at what was specifically
        # just said, not just the topic in the abstract. Symmetric: both
        # speakers get exactly one extra query, built the same way.
        key_phrase = _key_phrase(opponent_argument)
        if key_phrase:
            plan.search_queries.append(f"{key_phrase} evidence {topic_lower}")
            plan.evidence_goals.append("rebuttal-targeted evidence")

        plan.required_tools = [
            "web_search",
            "search_documents",
            "query_dataset",
        ]

        plan.reasoning_focus = strategy

        plan.rebuttal_focus = opponent_argument

        return plan