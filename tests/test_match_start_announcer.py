import pytest

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
