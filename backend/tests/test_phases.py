import importlib

from arena import phases as phases_module


def test_default_total_turns_is_five():
    # default TURNS_PER_PHASE=1 -> 5 phases x 1 turn = 5 total turns
    assert phases_module.total_turns() == 5


def test_phase_schedule_in_order_default():
    seen = []
    for t in range(phases_module.total_turns()):
        name = phases_module.get_phase(t)["name"]
        if not seen or seen[-1] != name:
            seen.append(name)

    assert seen == [
        "Opening",
        "Evidence",
        "Rebuttal",
        "Cross-Examination",
        "Closing",
    ]


def test_turns_per_phase_env_is_respected(monkeypatch):
    monkeypatch.setenv("TURNS_PER_PHASE", "2")
    assert phases_module.total_turns() == 10

    seen = []
    for t in range(10):
        name = phases_module.get_phase(t)["name"]
        if not seen or seen[-1] != name:
            seen.append(name)

    assert seen == [
        "Opening",
        "Evidence",
        "Rebuttal",
        "Cross-Examination",
        "Closing",
    ]

    # turns 6 and 7 (0-indexed turn_count) fall in Cross-Examination when
    # each phase gets 2 turns
    assert phases_module.is_cross_examination(6) is True
    assert phases_module.is_cross_examination(7) is True
    assert phases_module.is_cross_examination(0) is False


def test_invalid_turns_per_phase_falls_back_to_one(monkeypatch):
    monkeypatch.setenv("TURNS_PER_PHASE", "not-a-number")
    assert phases_module.total_turns() == 5


def test_get_phase_past_schedule_falls_back_to_last_phase():
    phase = phases_module.get_phase(phases_module.total_turns() + 10)
    assert phase["name"] == "Closing"
