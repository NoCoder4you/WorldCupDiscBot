import json

import pytest

discord = pytest.importorskip("discord")

from COGS.TextQuickOptions import TextQuickOptions


class DummyBot:
    def __init__(self, base_dir):
        self.BASE_DIR = str(base_dir)


def _cog(tmp_path):
    (tmp_path / "JSON").mkdir(exist_ok=True)
    return TextQuickOptions(DummyBot(tmp_path))


def test_parse_event_details_accepts_multi_word_country(tmp_path):
    cog = _cog(tmp_path)

    country, match_time = cog._parse_event_details("Costa Rica 67+2", "Brazil", "Costa Rica")

    assert country == "Costa Rica"
    assert match_time == "67+2"


def test_find_fixture_supports_wrapped_fixtures(tmp_path):
    cog = _cog(tmp_path)
    cog._write_json_atomic(cog.matches_path, {"fixtures": [{"id": "M1", "home": "A", "away": "B"}]})

    fixture, fixtures, container, key = cog._find_fixture("m1")

    assert fixture["home"] == "A"
    assert fixtures == container["fixtures"]
    assert key == "fixtures"


def test_enqueue_command_appends_jsonl_record(tmp_path):
    cog = _cog(tmp_path)

    cog._enqueue_command("quick_match_announcement", {"fixture_id": "M1"})

    lines = (tmp_path / "JSON" / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["kind"] == "quick_match_announcement"
    assert record["data"]["fixture_id"] == "M1"


def test_active_channel_fixtures_ignores_completed_matches(tmp_path):
    cog = _cog(tmp_path)
    cog._write_json_atomic(cog.matches_path, [
        {"id": "old", "home": "Sweden", "away": "Norway", "channel": "match-live", "status": "completed"},
        {"id": "live", "home": "Sweden", "away": "Denmark", "channel": "match-live", "status": "live"},
    ])

    matches, fixtures, container, key = cog._active_channel_fixtures("match-live")

    assert [m["id"] for m in matches] == ["live"]
    assert container is None
    assert key == ""


def test_fixture_id_prefers_existing_fixture_identifier(tmp_path):
    cog = _cog(tmp_path)

    assert cog._fixture_id({"match_id": "M7", "fixture_id": "fallback"}) == "M7"


def test_disallowed_goal_event_removes_latest_matching_goal(tmp_path):
    cog = _cog(tmp_path)
    fixture = {
        "id": "M1",
        "home": "A",
        "away": "B",
        "channel": "match-live",
        "live_stats": [
            {"event_type": "goal", "label": "Goal", "country": "A", "match_time": "10"},
            {"event_type": "goal", "label": "Goal", "country": "A", "match_time": "30"},
        ],
    }
    fixtures = [fixture]

    class DummyCtx:
        class Message:
            async def delete(self):
                return None
        message = Message()
        sent = []
        async def send(self, message, delete_after=None):
            self.sent.append(message)

    import asyncio
    asyncio.run(cog._queue_event_for_fixture(DummyCtx(), fixture, fixtures, None, "", "disallowed_goal", "A 31"))

    assert [(event["event_type"], event.get("match_time")) for event in fixture["live_stats"]] == [
        ("goal", "10"),
        ("disallowed_goal", "31"),
    ]
    record = json.loads((tmp_path / "JSON" / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["data"]["event_label"] == "Goal Disallowed"
    assert record["data"]["home_score"] == 1
