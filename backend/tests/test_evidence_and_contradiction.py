from arena.evidence import verify_claims, parse_search_results_structured, _safe_json
from arena.contradiction import check_contradiction


# ----------------------------
# _safe_json
# ----------------------------

def test_safe_json_parses_clean_json():
    assert _safe_json('{"a": 1}') == {"a": 1}


def test_safe_json_strips_markdown_fences():
    assert _safe_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_safe_json_recovers_embedded_json():
    assert _safe_json('Sure, here you go: {"a": 1} - hope that helps!') == {"a": 1}


def test_safe_json_returns_empty_dict_on_garbage():
    assert _safe_json("not json at all") == {}


# ----------------------------
# verify_claims - fallback behavior
# ----------------------------

def test_verify_claims_returns_zero_grounding_with_no_evidence():
    result = verify_claims(speech="AI improves productivity by 40%.", evidence_context="")
    assert result["grounding_score"] == 0
    assert result["claims"] == []


# ----------------------------
# parse_search_results_structured
# ----------------------------

def test_parse_search_results_structured_extracts_fields():
    raw = {
        "results": [
            {"title": "Study A", "url": "https://example.com/a", "content": "Some content here."},
        ]
    }

    records = parse_search_results_structured(raw, agent="elena", turn=2, query="test query")

    assert len(records) == 1
    assert records[0]["title"] == "Study A"
    assert records[0]["url"] == "https://example.com/a"
    assert records[0]["agent"] == "elena"
    assert records[0]["turn"] == 2
    assert records[0]["query"] == "test query"


def test_parse_search_results_structured_handles_empty_results():
    assert parse_search_results_structured({"results": []}, "elena", 1, "q") == []


# ----------------------------
# check_contradiction - fallback behavior
# ----------------------------

def test_check_contradiction_no_history_returns_not_found():
    result = check_contradiction("elena", ["new claim"], [])
    assert result["found"] is False


def test_check_contradiction_no_new_claims_returns_not_found():
    result = check_contradiction("elena", [], ["old claim"])
    assert result["found"] is False
