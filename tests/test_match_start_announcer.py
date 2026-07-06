import pytest
import json

discord = pytest.importorskip("discord")

from COGS.MatchStartAnnouncer import MatchStartAnnouncer


def _announcer_stub():
    # Build an instance without starting background loops.
    return MatchStartAnnouncer.__new__(MatchStartAnnouncer)


def test_parse_utc_ts_supports_iso_and_epoch():
    ann = _announcer_stub()

    iso_ts = ann._parse_utc_ts("2026-06-11T20:00:00Z")
    epoch_ts = ann._parse_utc_ts(str(iso_ts))

    assert iso_ts == epoch_ts


def test_resolve_channel_name_prefers_knockout_mapping():
    ann = _announcer_stub()
    ann._group_from_team_meta = lambda *_: ""

    fixture = {"stage": "Round of 16"}
    assert ann._resolve_channel_name(fixture, "France", "Brazil") == "round-of-16"


def test_resolve_channel_name_falls_back_to_group():
    ann = _announcer_stub()
    ann._group_from_team_meta = lambda *_: "B"

    fixture = {"stage": "Group Stage"}
    assert ann._resolve_channel_name(fixture, "France", "Brazil") == "group-b"


def test_reminder_kind_supports_one_hour_and_kickoff_windows():
    ann = _announcer_stub()

    # 59 minutes before kickoff -> one-hour reminder window.
    assert ann._reminder_kind(59 * 60) == "hour"
    # Exact kickoff and nearby poll drift -> kickoff reminder window.
    assert ann._reminder_kind(0) == "kickoff"
    assert ann._reminder_kind(-30) == "kickoff"
    # Out-of-window values should not trigger a reminder.
    assert ann._reminder_kind(3700) is None


def test_load_matches_prefers_json_directory(tmp_path):
    ann = _announcer_stub()
    ann.matches_path = str(tmp_path / "JSON" / "matches.json")
    ann.legacy_matches_path = str(tmp_path / "matches.json")

    (tmp_path / "JSON").mkdir(parents=True, exist_ok=True)
    with open(ann.matches_path, "w", encoding="utf-8") as f:
        json.dump([{"id": "json-fixture"}], f)
    with open(ann.legacy_matches_path, "w", encoding="utf-8") as f:
        json.dump([{"id": "legacy-fixture"}], f)

    matches = ann._load_matches()
    assert matches[0]["id"] == "json-fixture"


def test_kickoff_adjusted_embed_shows_previous_and_new_times():
    ann = _announcer_stub()
    previous_ts = ann._parse_utc_ts("2026-06-20T18:30:00Z")
    kickoff_ts = ann._parse_utc_ts("2026-06-20T17:30:00Z")

    embed = ann._kickoff_adjusted_embed("Japan", "Ghana", previous_ts, kickoff_ts, -1)

    assert "brought forward" in embed.title
    assert "Japan" in embed.description
    assert f"<t:{kickoff_ts}:F>" in embed.description
    assert embed.fields[0].name == "Previous kickoff"
    assert f"<t:{previous_ts}:F>" in embed.fields[0].value
    assert embed.fields[1].value == "Brought forward by 1 hour"


def test_delay_command_reader_uses_independent_offset(tmp_path):
    ann = _announcer_stub()
    ann.state_path = str(tmp_path / "JSON" / "match_start_announcer_state.json")
    ann.commands_path = str(tmp_path / "JSON" / "bot_commands.jsonl")
    ann._sent_hour_keys = set()
    ann._sent_kickoff_keys = set()
    ann._commands_offset = 0
    (tmp_path / "JSON").mkdir(parents=True, exist_ok=True)
    with open(ann.commands_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "quick_match_announcement", "data": {}}) + "\n")
        f.write(json.dumps({"kind": "fixture_kickoff_adjusted", "data": {"id": "M1"}}) + "\n")

    commands = ann._read_new_delay_commands()

    assert commands == [{"id": "M1"}]
    assert ann._read_new_delay_commands() == []
