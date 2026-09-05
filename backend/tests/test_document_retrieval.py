"""
Regression tests for local document retrieval (search_documents).

Root cause: search_documents previously required the ENTIRE query string
to appear verbatim as a substring inside a document
(`if query.lower() in content.lower()`). Every real caller - the
research planner and tool_node - passes a full sentence (the debate
topic, or a phrase like "arguments against <topic> peer reviewed
studies") as the query, not a single keyword. That full sentence almost
never appears verbatim in any document, so the tool always fell through
to "No matching documents found." regardless of how many/how relevant
the local documents were. This was true even with a well-stocked
document folder, and independent of the local knowledge base being thin
(data/documents previously had a single generic AI.txt file).

search_documents now does genuine keyword-overlap matching (tokenize
query + document, ignore stopwords, match on shared significant words),
which matches the *stated* design intent in docs/rag_decision.md
("keyword-based document search") - the implementation had drifted from
that design, not the design itself being wrong. It also now indexes
.md files (not just .txt), since the new local knowledge base ships as
Markdown with structured metadata headers.
"""

import re
from pathlib import Path

from arena.tools import search_documents

DOCS_DIR = Path("data/documents")

_REQUIRED_METADATA_FIELDS = [
    "SOURCE:",
    "TITLE:",
    "AUTHOR/ORGANIZATION:",
    "DATE:",
    "URL:",
    "TOPIC:",
    "CONTENT:",
]


# ----------------------------------------------------------------------
# Core bug fix: full-sentence topic queries must now find real matches
# ----------------------------------------------------------------------

def test_full_sentence_topic_query_now_finds_matches():
    """
    This is the exact query shape tool_node passes: the raw debate topic
    as a full sentence. Previously this always fell through to
    'No matching documents found.' - it must not anymore, given the new
    knowledge base actually covers this topic.
    """
    result = search_documents.invoke(
        {"query": "Should artificial intelligence replace software developers?"}
    )

    assert result != "No matching documents found."
    assert "Document:" in result


def test_research_planner_style_query_finds_matches():
    """Mirrors the actual query shape produced by ResearchPlanner."""
    result = search_documents.invoke(
        {"query": "arguments against Should artificial intelligence replace software developers? peer reviewed studies"}
    )

    assert result != "No matching documents found."
    assert "Document:" in result


def test_all_five_reported_test_queries_return_relevant_documents():
    queries = [
        "Should artificial intelligence replace software developers?",
        "How does AI affect software developer productivity?",
        "What are the limitations of AI coding tools?",
        "Can AI replace human judgment in software engineering?",
        "How is AI changing software engineering jobs?",
    ]

    for query in queries:
        result = search_documents.invoke({"query": query})
        assert result != "No matching documents found.", f"No match for: {query}"
        assert "Document:" in result


# ----------------------------------------------------------------------
# Fallback must still exist for genuinely irrelevant/empty queries
# ----------------------------------------------------------------------

def test_irrelevant_query_still_returns_no_matching_documents():
    result = search_documents.invoke(
        {"query": "xyzzyplugh quokka underwater basket weaving festival"}
    )
    assert result == "No matching documents found."


def test_empty_query_returns_no_matching_documents():
    result = search_documents.invoke({"query": ""})
    assert result == "No matching documents found."


# ----------------------------------------------------------------------
# .md files are now indexed, not just .txt
# ----------------------------------------------------------------------

def test_markdown_documents_are_indexed():
    """
    search_documents previously only globbed *.txt. The new knowledge
    base ships as .md files with structured metadata headers, so the
    glob must pick those up too.
    """
    md_files = list(DOCS_DIR.glob("*.md"))
    assert md_files, "expected .md documents in data/documents"

    # Query using a keyword unique to one specific .md document's content
    result = search_documents.invoke(
        {"query": "GitHub Copilot pair programmer HTTP server experiment"}
    )
    assert "ai_developer_productivity.md" in result


# ----------------------------------------------------------------------
# Relevance ranking: best match should be first
# ----------------------------------------------------------------------

def test_results_are_ranked_by_keyword_overlap():
    result = search_documents.invoke(
        {"query": "AI security vulnerabilities insecure code developers"}
    )
    documents_in_order = re.findall(r"Document: (\S+)", result)
    assert documents_in_order, "expected at least one match"
    # the security-focused document should be the top (or a top) match
    assert "ai_security_and_reliability.md" in documents_in_order


# ----------------------------------------------------------------------
# Knowledge base quality: every real document should carry attribution
# metadata (source/title/author/date/url) and not be fabricated
# ----------------------------------------------------------------------

def test_all_markdown_documents_have_required_metadata():
    md_files = list(DOCS_DIR.glob("*.md"))
    assert len(md_files) >= 8, "expected the new knowledge base documents to be present"

    for path in md_files:
        content = path.read_text(encoding="utf-8")
        for field in _REQUIRED_METADATA_FIELDS:
            assert field in content, f"{path.name} is missing required '{field}' metadata"


def test_knowledge_base_covers_both_sides_of_the_debate():
    """
    Sanity check that the knowledge base isn't one-sided: at least one
    document should support AI capability/productivity, and at least one
    should support AI limitations/human-oversight, per the requirement
    that Elena and Marcus both have real evidence available.
    """
    pro_ai_hit = search_documents.invoke(
        {"query": "AI coding assistants improve developer productivity"}
    )
    limitations_hit = search_documents.invoke(
        {"query": "AI coding tools limitations security risks human oversight"}
    )

    assert pro_ai_hit != "No matching documents found."
    assert limitations_hit != "No matching documents found."


# ----------------------------------------------------------------------
# Retrieval-quality fix: Elena and Marcus must get DIFFERENT queries (and
# therefore a real chance at different top documents), not the raw topic
# string every time. Root cause: tool_node previously called
# search_documents with the fixed `topic`, while web_search already used
# the planner's stance-specific, per-turn-rotating query - so local
# retrieval was speaker- and turn-independent even though web search was
# not.
# ----------------------------------------------------------------------

def test_both_speakers_retrieve_real_local_documents_through_tool_node():
    from arena.agents import tool_node

    for speaker in ("elena", "marcus"):
        state = {
            "topic": "Should artificial intelligence replace software developers?",
            "current_speaker": speaker,
            "messages": [],
            "argument_memory": {"elena": [], "marcus": []},
            "strategy_memory": {"elena": "", "marcus": ""},
            "tool_log": [],
        }
        result = tool_node(state)
        doc_search_entries = [
            ev for ev in result["tool_log"] if ev.tool == "search_documents"
        ]
        assert len(doc_search_entries) == 1
        assert doc_search_entries[0].result != "No matching documents found."
        assert "Document:" in doc_search_entries[0].result


def test_elena_and_marcus_get_different_search_documents_queries():
    from arena.agents import tool_node

    def make_state(speaker):
        return {
            "topic": "Should artificial intelligence replace software developers?",
            "current_speaker": speaker,
            "messages": [],
            "argument_memory": {"elena": [], "marcus": []},
            "strategy_memory": {"elena": "", "marcus": ""},
            "tool_log": [],
        }

    elena_result = tool_node(make_state("elena"))
    marcus_result = tool_node(make_state("marcus"))

    elena_query = next(
        ev.args for ev in elena_result["tool_log"] if ev.tool == "search_documents"
    )
    marcus_query = next(
        ev.args for ev in marcus_result["tool_log"] if ev.tool == "search_documents"
    )

    assert elena_query != marcus_query
    # not just different - stance-shaped, matching the planner's design
    assert "against" in elena_query or "negative" in elena_query
    assert "supporting" in marcus_query or "benefits" in marcus_query


def test_search_documents_query_rotates_across_speaker_turns():
    """
    A speaker's OWN successive turns should also pull different local
    evidence (mirrors the existing web_search rotation), not repeat the
    same query every turn.
    """
    from arena.agents import tool_node

    state = {
        "topic": "Should artificial intelligence replace software developers?",
        "current_speaker": "elena",
        "messages": [],
        "strategy_memory": {"elena": "", "marcus": ""},
        "tool_log": [],
    }

    queries = []
    for turn_arguments_so_far in range(3):
        state["argument_memory"] = {
            "elena": ["placeholder argument"] * turn_arguments_so_far,
            "marcus": [],
        }
        state["tool_log"] = []  # tool_node mutates this list in place
        result = tool_node(state)
        query = next(
            ev.args for ev in result["tool_log"] if ev.tool == "search_documents"
        )
        queries.append(query)

    assert len(set(queries)) > 1, "expected the query to rotate across turns"


# ----------------------------------------------------------------------
# Ranking must not let one broad, keyword-dense document dominate every
# query. Root cause: raw keyword-overlap COUNT (and later, raw term-
# frequency) favored whichever document simply contained the most/most-
# repeated shared vocabulary ("AI", "software", "developers"), regardless
# of actual topical fit - which is why ai_and_developer_employment.md
# kept winning regardless of query.
# ----------------------------------------------------------------------

def test_bls_employment_document_does_not_dominate_productivity_queries():
    result = search_documents.invoke(
        {"query": "How does AI improve developer productivity?"}
    )
    top_document = re.search(r"Document: (\S+)", result).group(1)
    assert top_document != "ai_and_developer_employment.md"


def test_bls_employment_document_does_not_dominate_limitations_queries():
    result = search_documents.invoke(
        {"query": "What are the limitations of AI coding tools?"}
    )
    top_document = re.search(r"Document: (\S+)", result).group(1)
    assert top_document != "ai_and_developer_employment.md"


def test_bls_employment_document_is_still_top_for_employment_queries():
    """It should still win when it's genuinely the best match."""
    result = search_documents.invoke(
        {"query": "How is AI changing software developer employment?"}
    )
    top_document = re.search(r"Document: (\S+)", result).group(1)
    assert top_document == "ai_and_developer_employment.md"


# ----------------------------------------------------------------------
# "AI" / "artificial intelligence" normalization: the debate topic spells
# it out in full, but almost every document (reasonably) abbreviates to
# "AI". Without normalizing these to the same token, "AI" - the single
# most central term in the whole knowledge base - was being dropped
# entirely (2-letter words failed the length filter), and the two rare
# literal words "artificial"/"intelligence" would instead dominate
# scoring for whichever one or two documents happened to spell it out.
# ----------------------------------------------------------------------

def test_ai_and_artificial_intelligence_are_treated_as_the_same_term():
    spelled_out = search_documents.invoke(
        {"query": "How does artificial intelligence affect developer productivity?"}
    )
    abbreviated = search_documents.invoke(
        {"query": "How does AI affect developer productivity?"}
    )

    spelled_out_docs = set(re.findall(r"Document: (\S+)", spelled_out))
    abbreviated_docs = set(re.findall(r"Document: (\S+)", abbreviated))

    assert spelled_out_docs == abbreviated_docs


def test_short_acronym_ai_is_not_dropped_as_too_short():
    from arena.tools import _word_counts

    counts = _word_counts("Will AI replace developers?")
    assert "ai" in counts


# ----------------------------------------------------------------------
# Full debate: Elena and Marcus should retrieve DIFFERENT top local
# documents over the course of a real debate, not always the same one.
# ----------------------------------------------------------------------

def test_elena_and_marcus_retrieve_different_documents_over_a_real_debate(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "offline")
    monkeypatch.setenv("LITE_MODE", "false")

    from arena import config as config_module
    if hasattr(config_module.load_llm, "_offline_singleton"):
        config_module.load_llm._offline_singleton.i = 0

    from arena.graph import build_app

    app = build_app()
    state = {
        "messages": [],
        "topic": "Should artificial intelligence replace software developers?",
        "current_speaker": "elena",
        "last_speaker": None,
        "pending_interrupt": None,
        "moderator_prompt": "",
        "turn_count": 0,
        "max_turns": 4,
        "should_continue": True,
        "scores": {},
        "last_score": None,
        "judge_history": [],
        "tool_log": [],
        "recent_tools": [],
        "tool_context": None,
        "cached_topic": None,
        "cached_tool_context": None,
        "argument_memory": {"elena": [], "marcus": []},
        "strategy_memory": {"elena": "", "marcus": ""},
        "final_summary": None,
        "exit_requested": False,
    }

    while True:
        state = app.invoke(state)
        if not state.get("should_continue"):
            break

    # Re-run each logged search_documents query directly (unfiltered by
    # the 700-char tool_log truncation) to see its full top-3 result.
    doc_events = [ev for ev in state["tool_log"] if ev.tool == "search_documents"]
    assert len(doc_events) == 4

    top_docs_per_turn = []
    for ev in doc_events:
        full_result = search_documents.invoke({"query": ev.args})
        top_docs_per_turn.append(re.search(r"Document: (\S+)", full_result).group(1))

    assert len(set(top_docs_per_turn)) > 1, (
        f"expected different top documents across turns, got {top_docs_per_turn}"
    )
