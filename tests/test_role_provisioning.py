import pytest

discord = pytest.importorskip("discord")

from COGS.RoleProvisioning import coerce_country_role_ids, group_label


def test_group_label_formats_world_cup_group_names():
    assert group_label("a") == "Group A"
    assert group_label(" B ") == "Group B"


def test_group_label_handles_blank_input():
    assert group_label("") == ""


def test_coerce_country_role_ids_preserves_scalar_values_and_extracts_dict_ids():
    raw = {
        "USA": 123,
        "Canada": {"role_id": 456, "group": "Group B", "group_role_id": 999},
        "Scotland": {"group": "Group C"},
    }
    assert coerce_country_role_ids(raw) == {"USA": 123, "Canada": 456}
