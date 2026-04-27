import pytest


discord = pytest.importorskip("discord")

from COGS.SplitOwnership import (
    can_request_split,
    evaluate_split_request_abuse,
    MAX_PENDING_SPLIT_REQUESTS_PER_USER,
    SPLIT_REQUEST_COOLDOWN_SECONDS,
)


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


def test_split_abuse_prevention_blocks_too_many_pending_requests():
    """Users should be blocked once they reach the pending-request limit."""
    now = 1_000_000.0
    requests = {
        f"202_Brazil_{int(now)-idx}": {
            "requester_id": "202",
            "team": f"Team-{idx}",
            "created_at": now - idx,
        }
        for idx in range(MAX_PENDING_SPLIT_REQUESTS_PER_USER)
    }

    allowed, title, _ = evaluate_split_request_abuse(requests, "202", now)

    assert allowed is False
    assert title == "Too Many Pending Requests"


def test_split_abuse_prevention_blocks_requests_during_cooldown():
    """Rapid-fire requests should trigger cooldown protection."""
    now = 2_000_000.0
    requests = {
        "303_Argentina_1999900": {
            "requester_id": "303",
            "team": "Argentina",
            "created_at": now - (SPLIT_REQUEST_COOLDOWN_SECONDS - 10),
        }
    }

    allowed, title, description = evaluate_split_request_abuse(requests, "303", now)

    assert allowed is False
    assert title == "Slow Down"
    assert "10 seconds" in description


def test_split_abuse_prevention_allows_request_after_cooldown():
    """Requests after cooldown should be allowed."""
    now = 3_000_000.0
    requests = {
        "404_Spain_2999000": {
            "requester_id": "404",
            "team": "Spain",
            "created_at": now - (SPLIT_REQUEST_COOLDOWN_SECONDS + 1),
        }
    }

    allowed, title, description = evaluate_split_request_abuse(requests, "404", now)

    assert allowed is True
    assert title is None
    assert description is None
