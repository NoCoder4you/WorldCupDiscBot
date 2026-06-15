import pytest

discord = pytest.importorskip("discord")

from COGS.FanZoneAnnouncer import FanZoneAnnouncer


def test_official_result_embed_includes_score_without_repeated_winner_text():
    """A home winner should be obvious from the trophy without a second outcome line."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("USA", "Canada", 2, 1)

    assert embed.title == "FULL TIME RESULT"
    assert "🏆 USA 2 – 1 Canada" in embed.description
    assert "Canada 🏆" not in embed.description
    assert "USA won" not in embed.description


def test_official_result_embed_identifies_draw():
    """A draw should not display a trophy beside either country."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("France", "Germany", 0, 0)

    assert "France 0 – 0 Germany" in embed.description
    assert "Draw" not in embed.description
    assert "🏆" not in embed.description


def test_official_result_embed_places_trophy_after_away_winner():
    """An away winner should have the trophy immediately right of its country."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("USA", "Canada", 0, 1)

    assert "USA 0 – 1 Canada 🏆" in embed.description
    assert "🏆 USA" not in embed.description


def test_official_tied_result_embed_uses_penalty_winner():
    """A tied official score should still display the selected shootout winner."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("USA", "Canada", 1, 1, "away")

    assert "USA 1 – 1 Canada 🏆" in embed.description
    assert "Canada won" not in embed.description


def test_official_tied_result_embed_displays_penalty_score():
    """Shootout scores should occupy the former redundant winner-text line."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed("USA", "Canada", 1, 1, "home", [], 5, 4)

    assert "Penalties: USA 5 – 4 Canada" in embed.description
    assert "USA won" not in embed.description


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


def test_quick_announcement_embed_uses_selected_country_flag_thumbnail():
    """Live event cards should display the selected team's flag as their thumbnail."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)
    announcer.team_iso = {"brazil": "br", "morocco": "ma"}

    embed = announcer._quick_announcement_embed({
        "event_type": "goal",
        "event_label": "Goal",
        "message": "Brazil 32'",
        "country": "Brazil",
        "home": "Brazil",
        "away": "Morocco",
    })

    assert embed.thumbnail.url == "https://flagcdn.com/w80/br.png"
    assert embed.description == "GOAL: Brazil 32'"


def test_quick_announcement_embed_omits_thumbnail_without_known_flag():
    """Unknown team mappings should not produce a broken thumbnail URL."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)
    announcer.team_iso = {}

    embed = announcer._quick_announcement_embed({
        "event_type": "yellow_card",
        "event_label": "Yellow Card",
        "message": "Unknown Team 40'",
        "country": "Unknown Team",
        "home": "Unknown Team",
        "away": "Morocco",
    })

    assert embed.thumbnail.url is None
