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


def test_official_result_embed_lists_event_times_without_repeating_scores():
    """The final summary should identify timed incidents without scoreline repetition."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed(
        "Spain",
        "Cape Verde",
        1,
        0,
        live_stats=[{
            "event_type": "yellow_card",
            "label": "Yellow Card",
            "message": "Spain 1 - 0 Cape Verde",
            "country": "Spain",
            "match_time": "38",
        }],
    )

    assert embed.fields[0].value == "**Yellow Card**  38'  Spain"
    assert "Spain 1 - 0 Cape Verde" not in embed.fields[0].value


def test_official_result_embed_uses_standard_half_time_clock():
    """Half-time summaries should state 45 minutes without requiring manual input."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed(
        "Spain",
        "Cape Verde",
        0,
        0,
        live_stats=[{
            "event_type": "half_time",
            "label": "Half Time",
            "message": "Spain 0 - 0 Cape Verde",
        }],
    )

    assert embed.fields[0].value == "**Half Time**  45'"


def test_official_result_embed_orders_late_entries_by_match_clock():
    """Late-entered incidents should appear where they occurred in the match."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)

    embed = announcer._result_embed(
        "Belgium",
        "Egypt",
        1,
        1,
        live_stats=[
            {"event_type": "goal", "label": "Goal", "country": "Belgium", "match_time": "66"},
            {"event_type": "half_time", "label": "Half Time", "country": "", "match_time": ""},
            {"event_type": "yellow_card", "label": "Yellow Card", "country": "Egypt", "match_time": "34"},
            {"event_type": "goal", "label": "Goal", "country": "Egypt", "match_time": "20"},
            {"event_type": "yellow_card", "label": "Yellow Card", "country": "Belgium", "match_time": "75"},
            {"event_type": "goal", "label": "Goal", "country": "Egypt", "match_time": "45+2"},
        ],
    )

    assert embed.fields[0].value.splitlines() == [
        "**Goal** - 20'  Egypt",
        "**Yellow Card** - 34'  Egypt",
        "**Goal** - 45+2'  Egypt",
        "**Half Time** - 45'",
        "**Goal** - 66'  Belgium",
        "**Yellow Card** - 75'  Belgium",
    ]


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
        "home_score": 1,
        "away_score": 0,
        "match_time": "32",
    })

    assert embed.thumbnail.url == "https://flagcdn.com/w80/br.png"
    assert embed.title == "⚽ - Goal  32'"
    assert embed.description is None
    assert embed.fields[0].name == "Match"
    assert embed.fields[0].value == "**Brazil 1 - 0 Morocco**"
    assert len(embed.fields) == 1


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


def test_half_time_embed_does_not_repeat_event_or_matchup():
    """Half time should use the compact action title and one scored matchup."""
    announcer = FanZoneAnnouncer.__new__(FanZoneAnnouncer)
    announcer.team_iso = {}

    embed = announcer._quick_announcement_embed({
        "event_type": "half_time",
        "event_label": "Half Time",
        "home": "Spain",
        "away": "Cape Verde",
        "home_score": 0,
        "away_score": 0,
    })

    assert embed.title == "⏸️ - Half Time  45'"
    assert embed.description is None
    assert embed.fields[0].value == "**Spain 0 - 0 Cape Verde**"
