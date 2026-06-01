import pytest


discord = pytest.importorskip("discord")

from COGS.SplitOwnership import (
    calculate_effective_split_percentages,
    can_request_split,
    evaluate_split_request_abuse,
    format_owner_mentions,
    format_owner_share_label,
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


def test_public_embed_share_labels_follow_stored_percentages():
    """Discord ownership embeds should mirror the web page's custom split percentages."""
    ownership = {
        "main_owner": 200,
        "split_with": [100],
        "percentages": {"200": 90, "100": 10},
    }

    assert format_owner_share_label(200, 2, ownership) == "90%"
    assert format_owner_mentions([100], 2, ownership) == "<@100> (10%)"


def test_public_embed_share_labels_fall_back_to_equal_split_without_percentages():
    """Legacy ownership data without percentages should keep the old equal-share display."""
    ownership = {"main_owner": 200, "split_with": [100]}

    assert format_owner_share_label(200, 2, ownership) == "50%"
    assert format_owner_mentions([100], 2, ownership) == "<@100> (50%)"


def test_effective_split_percentages_match_logged_and_persisted_share():
    """Accepted split logging should use the same percentage map written to ownership data."""
    requested_share, percentages = calculate_effective_split_percentages(
        200,
        [300],
        100,
        {"requested_percentage": 10},
    )

    assert requested_share == 10.0
    assert percentages == {"200": 45.0, "300": 45.0, "100": 10.0}
