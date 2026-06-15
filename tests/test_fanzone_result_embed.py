import pytest

discord = pytest.importorskip("discord")

from COGS.FanZoneAnnouncer import FanZoneAnnouncer


def test_official_result_embed_includes_score_and_outcome():
    """Discord's dedicated result embed should mirror the saved fixture score."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("USA", "Canada", 2, 1)

    assert embed.title == "Official Match Result"
    assert "USA 2 – 1 Canada" in embed.description
    assert "USA won" in embed.description


def test_official_result_embed_identifies_draw():
    """Equal scores should be announced as a draw rather than a declared winner."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("France", "Germany", 0, 0)

    assert "France 0 – 0 Germany" in embed.description
    assert "Draw" in embed.description
