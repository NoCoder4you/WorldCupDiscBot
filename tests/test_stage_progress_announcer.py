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


def test_eliminated_stage_uses_group_channel_from_team_meta(tmp_path):
    ann = _stub()
    ann.country_group_links_path = str(tmp_path / "JSON" / "country_group_links.json")
    ann.team_meta_path = str(tmp_path / "JSON" / "team_meta.json")
    (tmp_path / "JSON").mkdir()
    (tmp_path / "JSON" / "team_meta.json").write_text(
        '{"groups": {"C": ["Haïti", "England"]}}',
        encoding="utf-8",
    )

    assert ann._group_channel_for_team("Haïti") == "group-c"


def test_eliminated_stage_uses_group_channel_links_first(tmp_path):
    ann = _stub()
    ann.country_group_links_path = str(tmp_path / "JSON" / "country_group_links.json")
    ann.team_meta_path = str(tmp_path / "JSON" / "team_meta.json")
    (tmp_path / "JSON").mkdir()
    (tmp_path / "JSON" / "country_group_links.json").write_text(
        '{"Haïti": {"group": "Group C", "group_role_id": 123}}',
        encoding="utf-8",
    )

    assert ann._group_channel_for_team("Haïti") == "group-c"


def test_group_stage_updates_use_team_group_channel(tmp_path):
    ann = _stub()
    ann.country_group_links_path = str(tmp_path / "JSON" / "country_group_links.json")
    ann.team_meta_path = str(tmp_path / "JSON" / "team_meta.json")
    (tmp_path / "JSON").mkdir()
    (tmp_path / "JSON" / "country_group_links.json").write_text(
        '{"Haïti": {"group": "Group C", "group_role_id": 123}}',
        encoding="utf-8",
    )

    assert ann._stage_update_channel("Haïti", "Group Stage", "announcements") == "group-c"


def test_knockout_stage_updates_still_use_stage_channel(tmp_path):
    ann = _stub()
    ann.country_group_links_path = str(tmp_path / "JSON" / "country_group_links.json")
    ann.team_meta_path = str(tmp_path / "JSON" / "team_meta.json")
    (tmp_path / "JSON").mkdir()
    (tmp_path / "JSON" / "country_group_links.json").write_text(
        '{"Haïti": {"group": "Group C", "group_role_id": 123}}',
        encoding="utf-8",
    )

    assert ann._stage_update_channel("Haïti", "Round of 16", "announcements") == "round-of-16"
