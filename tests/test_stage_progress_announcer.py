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


def test_eliminated_from_knockout_uses_previous_stage_channel(tmp_path):
    ann = _stub()
    ann.country_group_links_path = str(tmp_path / "JSON" / "country_group_links.json")
    ann.team_meta_path = str(tmp_path / "JSON" / "team_meta.json")
    (tmp_path / "JSON").mkdir()
    (tmp_path / "JSON" / "country_group_links.json").write_text(
        '{"Haïti": {"group": "Group C", "group_role_id": 123}}',
        encoding="utf-8",
    )

    assert ann._stage_update_channel(
        "Haïti", "Eliminated", "announcements", "Round of 16"
    ) == "round-of-16"


def test_eliminated_from_group_stage_uses_team_group_channel(tmp_path):
    ann = _stub()
    ann.country_group_links_path = str(tmp_path / "JSON" / "country_group_links.json")
    ann.team_meta_path = str(tmp_path / "JSON" / "team_meta.json")
    (tmp_path / "JSON").mkdir()
    (tmp_path / "JSON" / "country_group_links.json").write_text(
        '{"Haïti": {"group": "Group C", "group_role_id": 123}}',
        encoding="utf-8",
    )

    assert ann._stage_update_channel(
        "Haïti", "Eliminated", "announcements", "Group Stage"
    ) == "group-c"


def test_final_placement_embeds_use_placement_language():
    """Placement embeds must say a team finished in-place rather than advanced."""
    ann = _stub()

    public = ann._public_embed("Brazil", "2nd Place", None)
    dm = ann._dm_embed("Croatia", "3rd Place", None)
    winner = ann._public_embed("Argentina", "Winner", None)

    assert public.title == "🥈 Final Placement"
    assert public.description == "**Brazil** finished in **2nd Place**."
    assert dm.title == "🥉 Final Placement"
    assert dm.description == "**Croatia** finished in **3rd Place**."
    assert winner.description == "**Argentina** finished in **1st Place**."


def test_placement_stage_updates_use_configured_stage_channels():
    """New placement stages should resolve to public channels so embeds can be sent."""
    ann = _stub()

    assert ann._stage_update_channel("Brazil", "2nd Place", "announcements", "Final") == "final"
    assert ann._stage_update_channel("Croatia", "3rd Place", "announcements", "Third Place Play-off") == "third-place-play"
