import pytest
import asyncio

discord = pytest.importorskip("discord")

from COGS import TeamsDistribution as teams_distribution_module
from COGS.TeamsDistribution import TeamsDistribution, calculate_teams_left


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


def test_get_group_role_for_country_uses_linked_group_role_id(monkeypatch):
    class DummyGuild:
        def __init__(self):
            self.requested_role_id = None

        def get_role(self, role_id):
            self.requested_role_id = role_id
            return f"role-{role_id}"

    # The cog only needs a bot reference for this helper, so a simple object works.
    cog = TeamsDistribution(bot=object())
    guild = DummyGuild()

    monkeypatch.setattr(
        teams_distribution_module,
        "load_json",
        lambda _path: {"France": {"group": "Group B", "group_role_id": 9876}},
    )

    role = asyncio.run(cog.get_group_role_for_country(guild, "France"))
    assert role == "role-9876"
    assert guild.requested_role_id == 9876
