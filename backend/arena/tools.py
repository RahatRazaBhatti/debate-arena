import os
import json
import ast
import re
import math
import operator
from collections import Counter
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient
from pathlib import Path
load_dotenv()

client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

def raw_web_search(query: str, max_results: int = 3) -> dict:
    """
    Hit Tavily directly and return the raw structured response
    ({"results": [{"title", "url", "content"}, ...]}), so callers that
    need per-source attribution (not just a flattened text blob) can use
    it. Never raises - returns {"results": []} on failure.
    """
    try:
        return client.search(query=query, max_results=max_results)
    except Exception as e:
        return {"results": [], "error": str(e)}


@tool
def web_search(query: str) -> str:
    """Search the web using Tavily and return relevant results."""

    response = raw_web_search(query)
    results = response.get("results", [])

    if not results:
        return "No search results found."

    formatted_results = []

    for result in results:
        formatted_results.append(
            f"Title: {result.get('title', 'N/A')}\n"
            f"URL: {result.get('url', 'N/A')}\n"
            f"Summary: {result.get('content', 'N/A')}"
        )

    return "\n\n".join(formatted_results)



# Small stopword list so single-word overlaps like "the"/"and" don't count
# as a meaningful match. This keeps the search a plain keyword search (per
# docs/rag_decision.md's design decision - no embeddings/vector store,
# corpus is intentionally small) while actually behaving like keyword
# search instead of requiring the entire query string as one substring.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "and", "or", "for", "with", "this", "that",
    "it", "as", "by", "have", "has", "had", "do", "does", "did", "not",
    "no", "but", "if", "than", "then", "which", "who", "what", "when",
    "where", "why", "how", "can", "will", "should", "would", "could",
    "i", "you", "we", "they", "he", "she", "them", "their", "our",
    "your", "my", "us", "at", "from", "into", "about", "up", "so",
}

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']+")

# The debate topic and generated queries often spell out "artificial
# intelligence" in full, while almost every local document (reasonably)
# just says "AI". Without normalizing these to the same token, "AI" - the
# single most central term in this entire knowledge base - would barely
# ever match, and the two rare literal words "artificial"/"intelligence"
# would instead dominate scoring for whichever one or two documents
# happen to spell it out, unrelated to actual topical relevance.
_AI_SYNONYM_RE = re.compile(r"\bartificial\s+intelligence\b", re.IGNORECASE)


def _word_counts(text: str) -> Counter:
    text = _AI_SYNONYM_RE.sub(" AI ", text)
    counts = Counter()
    for raw in _WORD_RE.findall(text):
        word = raw.lower()
        if word in _STOPWORDS:
            continue
        # Keep short (2-4 letter) domain acronyms like "AI", "ML", "QA",
        # "NLP" even though they'd otherwise fail the length filter below -
        # these are exactly the terms most likely to matter in a technical
        # debate, and dropping them (as the previous len(w) > 2 check did)
        # silently starved the ranking of its most important signal.
        is_short_acronym = raw.isupper() and 2 <= len(raw) <= 4
        if len(raw) > 2 or is_short_acronym:
            counts[word] += 1
    return counts


@tool
def search_documents(query: str) -> str:
    """Search local documents for relevant information."""

    documents_path = Path("data/documents")

    if not documents_path.exists():
        return "Documents folder not found."

    doc_files = sorted(documents_path.glob("*.txt")) + sorted(documents_path.glob("*.md"))

    if not doc_files:
        return "No text documents found."

    query_keywords = set(_word_counts(query))

    if not query_keywords:
        return "No matching documents found."

    docs = [
        (file_path.name, file_path.read_text(encoding="utf-8"))
        for file_path in doc_files
    ]
    doc_word_counts = {name: _word_counts(content) for name, content in docs}

    # Plain keyword-based TF-IDF-style ranking (no embeddings/vector store -
    # see docs/rag_decision.md). A document's score rewards query terms
    # that appear multiple times in that document (term frequency) and
    # that are relatively rare across the local corpus as a whole (inverse
    # document frequency), so a handful of broad terms every AI/software
    # document shares ("AI", "software", "developers") can't let one long,
    # keyword-dense document dominate every query regardless of topical
    # fit. This is what previously made ai_and_developer_employment.md win
    # almost every query - it simply contained the most distinct keywords.
    num_docs = len(docs)
    doc_frequency = Counter()
    for counts in doc_word_counts.values():
        doc_frequency.update(counts.keys())

    def idf(word: str) -> float:
        df = doc_frequency.get(word, 0)
        return math.log((num_docs + 1) / (df + 1)) + 1  # smoothed, always > 0

    scored = []
    for name, content in docs:
        counts = doc_word_counts[name]
        overlap = query_keywords & set(counts)
        if not overlap:
            continue
        # Log-dampened term frequency (standard TF-IDF practice): a word
        # appearing 17 times in one document shouldn't count 17x more than
        # the same word appearing once elsewhere - that let documents which
        # simply repeat a common word like "AI" many times drown out
        # documents that were more specifically on-topic for the query's
        # actually distinguishing terms.
        relevance = sum(
            (1 + math.log(counts[word])) * idf(word) for word in overlap
        )
        scored.append((relevance, len(overlap), name, content))

    if not scored:
        return "No matching documents found."

    # Highest relevance score first; cap to the top 3 so one query doesn't
    # dump the entire local corpus into context.
    scored.sort(key=lambda item: item[0], reverse=True)
    top_matches = scored[:3]

    matching_results = [
        f"Document: {name} (matched keywords: {overlap_count}, relevance score: {relevance:.2f})\n\n{content}"
        for relevance, overlap_count, name, content in top_matches
    ]

    return "\n\n".join(matching_results)

@tool
def query_dataset(metric: str) -> str:
    """Query the local statistics dataset."""

    dataset_path = Path("data/stats.json")

    if not dataset_path.exists():
        return "Statistics dataset not found."

    with open(dataset_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    value = data.get(metric.lower())

    if value is None:
        return f"Metric '{metric}' not found."

    return f"{metric}: {value}"


_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluate(node):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)

    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numbers are allowed.")

    elif isinstance(node, ast.BinOp):
        left = _evaluate(node.left)
        right = _evaluate(node.right)

        op_type = type(node.op)

        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Operator {op_type.__name__} is not allowed.")

        return _ALLOWED_OPERATORS[op_type](left, right)

    elif isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand)

        op_type = type(node.op)

        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Operator {op_type.__name__} is not allowed.")

        return _ALLOWED_OPERATORS[op_type](operand)

    raise ValueError("Invalid mathematical expression.")


@tool
def execute_math(expression: str) -> str:
    """Safely evaluate a mathematical expression."""

    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate(tree)
        return str(result)

    except Exception as e:
        return f"Math Error: {e}"


@tool
def simulate_growth(
    initial_value: float,
    growth_rate: float,
    years: int,
) -> str:
    """Simulate compound growth over multiple years."""

    current_value = initial_value
    results = []

    for year in range(1, years + 1):
        current_value *= (1 + growth_rate / 100)

        results.append(
            f"Year {year}: {current_value:.2f}"
        )

    return "\n".join(results)

@dataclass
class ToolEvent:
    agent: str
    tool: str
    args: str
    result: str

def default_tools():
    return [
        web_search,
        search_documents,
        query_dataset,
        execute_math,
        simulate_growth,
    ]