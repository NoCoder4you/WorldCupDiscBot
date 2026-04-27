import pytest


discord = pytest.importorskip("discord")

from COGS.SplitOwnership import can_request_split


def test_can_request_split_when_user_owns_team():
    """Owning any team should keep split eligibility unchanged."""
    players = {
        "101": {
            "display_name": "Owner",
            "teams": [{"team": "Brazil", "ownership": {"main_owner": 101, "split_with": []}}],
        }
    }

    assert can_request_split(players, {"verified_users": []}, "101") is True


def test_can_request_split_when_verified_without_players_record():
    """Verified users should be allowed even when absent from players.json."""
    players = {}
    verified = {"verified_users": [{"discord_id": "202", "habbo_name": "Foo"}]}

    assert can_request_split(players, verified, "202") is True


def test_cannot_request_split_when_unverified_player_without_team():
    """Users without teams must be verified to request a split."""
    players = {"303": {"display_name": "Unverified", "teams": []}}
    verified = {"verified_users": []}

    assert can_request_split(players, verified, "303") is False
