import pytest

discord = pytest.importorskip("discord")

from COGS.FanZoneAnnouncer import FanZoneAnnouncer


def test_official_result_embed_includes_score_and_outcome():
    """A home winner should have the trophy immediately left of its country."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("USA", "Canada", 2, 1)

    assert embed.title == "FULL TIME RESULT"
    assert "🏆 USA 2 – 1 Canada" in embed.description
    assert "Canada 🏆" not in embed.description
    assert "USA won" in embed.description


def test_official_result_embed_identifies_draw():
    """A draw should not display a trophy beside either country."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("France", "Germany", 0, 0)

    assert "France 0 – 0 Germany" in embed.description
    assert "Draw" in embed.description
    assert "🏆" not in embed.description


def test_official_result_embed_places_trophy_after_away_winner():
    """An away winner should have the trophy immediately right of its country."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("USA", "Canada", 0, 1)

    assert "USA 0 – 1 Canada 🏆" in embed.description
    assert "🏆 USA" not in embed.description


def test_match_picks_embed_includes_score_from_settlement():
    """The normal settlement embed should include scores entered in the UI."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._public_embed("USA", "Canada", "USA", "Canada", None, 2, 1)

    assert embed.title == "FULL TIME RESULT"
    assert "**🏆 USA** vs **Canada**" in embed.description
    assert "2 – 1" in embed.description
    assert "Winner: **USA**" in embed.description


def test_match_picks_embed_places_trophy_after_away_winner():
    """The settled Match Picks embed follows the away-side trophy placement."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._public_embed("USA", "Canada", "Canada", "USA", None, 0, 1)

    assert "**USA** vs **Canada 🏆**" in embed.description
    assert "🏆 USA" not in embed.description
