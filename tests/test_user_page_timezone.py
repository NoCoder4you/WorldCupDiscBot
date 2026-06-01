from pathlib import Path


USER_JS = Path(__file__).resolve().parents[1] / "WorldCupBot" / "static" / "user.js"


def test_user_matches_header_no_longer_says_utc():
    source = USER_JS.read_text()

    assert "<th>When</th>" in source
    assert "When (UTC)" not in source


def test_user_matches_use_selected_timezone_formatter():
    source = USER_JS.read_text()

    assert "const normalizeUtcKickoff" in source
    assert "formatter(utcIso)" in source
    assert "window.formatFixtureDateTimeCompact || window.formatFixtureDateTime" in source
    assert "window.addEventListener('timezonechange', refreshUser)" in source
