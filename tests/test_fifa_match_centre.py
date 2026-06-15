import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest

discord = pytest.importorskip("discord")

from COGS.FifaMatchCentre import FifaMatchCentre


MATCH_URL = "https://www.fifa.com/en/match-centre/match/17/285023/289273/400021482"


def _cog_stub():
    """Construct the cog without starting its background task."""
    cog = FifaMatchCentre.__new__(FifaMatchCentre)
    cog._last_capture_at = 0
    cog._last_image_hash = ""
    cog._save_state = lambda: None
    cog.matches_path = "/missing/matches.json"
    cog.legacy_matches_path = "/missing/legacy-matches.json"
    cog.team_meta_path = "/missing/team-meta.json"
    return cog


def test_discord_settings_override_legacy_config(tmp_path):
    cog = _cog_stub()
    cog.settings_path = str(tmp_path / "JSON" / "fifa_match_centre_settings.json")
    cog.config_path = str(tmp_path / "config.json")
    with open(cog.config_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "FIFA_MATCH_CENTRE_ENABLED": False,
                "FIFA_MATCH_CENTRE_CHANNEL_ID": "111",
            },
            handle,
        )

    cog._save_settings(
        {
            "enabled": True,
            "url": MATCH_URL,
            "fixture_id": "M12",
            "guild_id": "123",
            "interval_minutes": 7,
        }
    )

    assert cog._settings() == {
        "enabled": True,
        "url": MATCH_URL,
        "fixture_id": "M12",
        "guild_id": "123",
        "interval_minutes": 7,
    }


def test_settings_recover_from_invalid_interval(tmp_path):
    cog = _cog_stub()
    cog.settings_path = str(tmp_path / "settings.json")
    cog.config_path = str(tmp_path / "missing-config.json")
    with open(cog.settings_path, "w", encoding="utf-8") as handle:
        json.dump({"interval_minutes": "not-a-number"}, handle)

    assert cog._settings()["interval_minutes"] == 5


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (MATCH_URL, True),
        ("https://inside.fifa.com/tournament", True),
        ("http://www.fifa.com/match", False),
        ("https://fifa.com.evil.example/match", False),
        ("https://example.com/match", False),
    ],
)
def test_fifa_url_validation_prevents_arbitrary_browser_targets(url, expected):
    cog = _cog_stub()

    assert cog._valid_fifa_url(url) is expected


def test_capture_schedule_respects_configured_interval():
    cog = _cog_stub()
    cog._last_capture_at = 1_000

    assert cog._capture_is_due(5, now=1_299) is False
    assert cog._capture_is_due(5, now=1_300) is True


def test_settings_have_no_default_match_or_fixture(tmp_path):
    cog = _cog_stub()
    cog.settings_path = str(tmp_path / "missing-settings.json")
    cog.config_path = str(tmp_path / "missing-config.json")

    settings = cog._settings()

    assert settings["url"] == ""
    assert settings["fixture_id"] == ""


def test_fixture_channel_uses_group_and_knockout_stage(tmp_path):
    cog = _cog_stub()
    cog.team_meta_path = str(tmp_path / "missing-team-meta.json")

    assert cog._channel_name_for_fixture(
        {"id": "M12", "home": "USA", "away": "Canada", "group": "B"}
    ) == "group-b"
    assert cog._channel_name_for_fixture(
        {"id": "M97", "home": "USA", "away": "Canada", "stage": "Quarter-finals"}
    ) == "quarter-finals"


def test_find_fixture_supports_common_id_fields(tmp_path):
    cog = _cog_stub()
    cog.matches_path = str(tmp_path / "matches.json")
    with open(cog.matches_path, "w", encoding="utf-8") as handle:
        json.dump([{"fixture_id": "M12", "home": "USA", "away": "Canada"}], handle)

    assert cog._find_fixture("m12")["home"] == "USA"
    assert cog._find_fixture("missing") is None


def test_embed_links_to_fifa_and_uses_attachment_image():
    cog = _cog_stub()

    embed = cog._build_embed(MATCH_URL)

    assert embed.title == "FIFA Match Centre"
    assert embed.url == MATCH_URL
    assert embed.image.url == "attachment://fifa-match-centre.png"
    assert embed.footer.text == "Source: FIFA.com"


def test_publish_skips_unchanged_automatic_capture(monkeypatch):
    cog = _cog_stub()
    image = b"stable screenshot"
    cog._last_image_hash = hashlib.sha256(image).hexdigest()
    cog._settings = lambda: {
        "enabled": True,
        "url": MATCH_URL,
        "fixture_id": "M12",
        "guild_id": "123",
        "interval_minutes": 5,
    }
    cog._capture_match_centre = AsyncMock(return_value=image)
    cog._resolve_fixture_channel = AsyncMock()
    monkeypatch.setattr("COGS.FifaMatchCentre.time.time", lambda: 2_000)

    result = asyncio.run(cog._publish())

    assert result == "unchanged"
    assert cog._last_capture_at == 2_000
    cog._resolve_fixture_channel.assert_not_awaited()


def test_forced_publish_posts_even_when_capture_is_unchanged(monkeypatch):
    cog = _cog_stub()
    image = b"stable screenshot"
    cog._last_image_hash = hashlib.sha256(image).hexdigest()
    cog._settings = lambda: {
        "enabled": False,
        "url": MATCH_URL,
        "fixture_id": "M12",
        "guild_id": "123",
        "interval_minutes": 5,
    }
    cog._capture_match_centre = AsyncMock(return_value=image)
    channel = AsyncMock()
    cog._resolve_fixture_channel = AsyncMock(return_value=channel)
    monkeypatch.setattr("COGS.FifaMatchCentre.time.time", lambda: 2_000)

    result = asyncio.run(cog._publish(force=True))

    assert result == "published"
    channel.send.assert_awaited_once()
    sent = channel.send.await_args.kwargs
    assert sent["file"].filename == "fifa-match-centre.png"
    assert sent["embed"].image.url == "attachment://fifa-match-centre.png"
