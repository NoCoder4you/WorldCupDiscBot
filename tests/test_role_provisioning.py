import pytest

discord = pytest.importorskip("discord")

from COGS.RoleProvisioning import group_label


def test_group_label_formats_world_cup_group_names():
    assert group_label("a") == "Group A"
    assert group_label(" B ") == "Group B"


def test_group_label_handles_blank_input():
    assert group_label("") == ""
