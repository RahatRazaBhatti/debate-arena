from arena.momentum import (
    compute_momentum,
    score_tool_use,
    score_concrete_numbers,
    score_engagement,
    score_verbosity,
    TOOL_USE_CAP,
    NUMBER_CAP,
    ENGAGEMENT_CAP,
    VERBOSITY_CAP,
)


# ----------------------------
# score_tool_use()
# ----------------------------

def test_tool_use_scales_with_tool_count():
    assert score_tool_use([]) == 0
    assert score_tool_use(["web_search"]) == 5
    assert score_tool_use(["web_search", "query_dataset"]) == 10


def test_tool_use_is_capped():
    many_tools = ["web_search"] * 10
    assert score_tool_use(many_tools) == TOOL_USE_CAP


# ----------------------------
# score_concrete_numbers()
# ----------------------------

def test_concrete_numbers_counts_digits_and_percents():
    text = "Studies show 42% of people and 17 cases were reported."
    assert score_concrete_numbers(text) == 4  # 42% + 17 -> 2 matches * 2 pts


def test_concrete_numbers_zero_when_no_digits():
    assert score_concrete_numbers("No numbers mentioned here at all.") == 0


def test_concrete_numbers_is_capped():
    text = " ".join(str(n) for n in range(20))
    assert score_concrete_numbers(text) == NUMBER_CAP


# ----------------------------
# score_engagement()
# ----------------------------

def test_engagement_zero_with_no_opponent_speech():
    assert score_engagement("some speech", "No previous opponent speech.") == 0


def test_engagement_rewards_shared_vocabulary():
    speech = "Renewable subsidies reduce emissions significantly."
    opponent = "Renewable subsidies are costly for taxpayers."
    score = score_engagement(speech, opponent)
    assert 0 < score <= ENGAGEMENT_CAP


# ----------------------------
# score_verbosity()
# ----------------------------

def test_verbosity_full_marks_in_target_range():
    speech = " ".join(["word"] * 100)
    assert score_verbosity(speech) == VERBOSITY_CAP


def test_verbosity_penalizes_too_short():
    speech = "Too short."
    assert score_verbosity(speech) < VERBOSITY_CAP


def test_verbosity_zero_for_empty():
    assert score_verbosity("") == 0


# ----------------------------
# compute_momentum()
# ----------------------------

def test_compute_momentum_is_deterministic():
    speech = "Renewable energy adoption reduced emissions by 30% over five years."
    opponent = "Renewable subsidies increase costs for taxpayers significantly."
    tools = ["web_search", "query_dataset"]

    result_a = compute_momentum(speech, opponent, tools)
    result_b = compute_momentum(speech, opponent, tools)

    assert result_a == result_b
    assert result_a["total"] == (
        result_a["tool_use"]
        + result_a["concrete_numbers"]
        + result_a["engagement"]
        + result_a["verbosity"]
    )


def test_compute_momentum_handles_empty_inputs():
    result = compute_momentum("", "", [])
    assert result["total"] == 0
