import pytest

discord = pytest.importorskip("discord")

from COGS.StageProgressAnnouncer import StageProgressAnnouncer


def _stub():
    return StageProgressAnnouncer.__new__(StageProgressAnnouncer)


def test_announcement_channel_uses_stage_map():
    ann = _stub()
    assert ann._announcement_channel("Semi-finals", "announcements") == "semi-finals"


def test_announcement_channel_falls_back_to_requested_channel():
    ann = _stub()
    assert ann._announcement_channel("Unknown", "custom-feed") == "custom-feed"
