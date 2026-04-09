import pytest

discord = pytest.importorskip("discord")

from COGS.TeamsDistribution import calculate_teams_left


def test_calculate_teams_left_counts_pending_and_assigned_slots():
    teams = [f"Team {i}" for i in range(48)]
    players = {
        "1": {"teams": [{"pending": True}]},
        "2": {"teams": [{"team": "Team 7"}]},
        "3": {"teams": ["Team 12"]},  # Legacy entry format.
    }

    assert calculate_teams_left(players, teams) == 45


def test_calculate_teams_left_never_goes_negative():
    teams = [f"Team {i}" for i in range(2)]
    players = {
        "1": {"teams": [{"pending": True}, {"pending": True}, {"team": "Team 1"}]},
    }

    assert calculate_teams_left(players, teams) == 0
