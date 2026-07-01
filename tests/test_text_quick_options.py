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


def test_penalty_event_records_decision_without_changing_score(tmp_path):
    cog = _cog(tmp_path)
    fixture = {
        "id": "M1",
        "home": "A",
        "away": "B",
        "channel": "match-live",
        "live_stats": [{"event_type": "goal", "label": "Goal", "country": "B", "match_time": "10"}],
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
    asyncio.run(cog._queue_event_for_fixture(DummyCtx(), fixture, fixtures, None, "", "penalty", "A 52"))

    assert [(event["event_type"], event.get("country"), event.get("match_time")) for event in fixture["live_stats"]] == [
        ("goal", "B", "10"),
        ("penalty", "A", "52"),
    ]
    record = json.loads((tmp_path / "JSON" / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["data"]["event_label"] == "Penalty"
    assert record["data"]["message"] == "A 0 - 1 B"
    assert record["data"]["home_score"] == 0
    assert record["data"]["away_score"] == 1


def test_var_decision_event_records_without_changing_score(tmp_path):
    cog = _cog(tmp_path)
    fixture = {
        "id": "M1",
        "home": "A",
        "away": "B",
        "channel": "match-live",
        "live_stats": [{"event_type": "goal", "label": "Goal", "country": "A", "match_time": "9"}],
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
    asyncio.run(cog._queue_event_for_fixture(DummyCtx(), fixture, fixtures, None, "", "var_decision", "B 64"))

    assert [(event["event_type"], event.get("country"), event.get("match_time")) for event in fixture["live_stats"]] == [
        ("goal", "A", "9"),
        ("var_decision", "B", "64"),
    ]
    record = json.loads((tmp_path / "JSON" / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["data"]["event_label"] == "VAR Decision"
    assert record["data"]["message"] == "A 1 - 0 B"
    assert record["data"]["home_score"] == 1
    assert record["data"]["away_score"] == 0


def test_extra_time_event_records_without_country_or_score_change(tmp_path):
    cog = _cog(tmp_path)
    fixture = {
        "id": "M1",
        "home": "A",
        "away": "B",
        "channel": "match-live",
        "live_stats": [{"event_type": "goal", "label": "Goal", "country": "B", "match_time": "88"}],
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
    asyncio.run(cog._queue_event_for_fixture(DummyCtx(), fixture, fixtures, None, "", "extra_time", ""))

    assert [(event["event_type"], event.get("country"), event.get("match_time")) for event in fixture["live_stats"]] == [
        ("goal", "B", "88"),
        ("extra_time", "", ""),
    ]
    record = json.loads((tmp_path / "JSON" / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["data"]["event_label"] == "Extra Time"
    assert record["data"]["country"] == ""
    assert record["data"]["message"] == "A 0 - 1 B"


def test_queue_fixture_result_embed_uses_saved_score_and_stats(tmp_path):
    cog = _cog(tmp_path)
    fixture = {
        "id": "M2",
        "home": "Belgium",
        "away": "Senegal",
        "channel": "belgium-senegal",
        "home_score": 3,
        "away_score": 2,
        "winner_side": "home",
        "live_stats": [{"event_type": "extra_time", "label": "Extra Time", "match_time": ""}],
    }

    queued, message = cog._queue_fixture_result_embed(fixture)

    assert queued is True
    assert message == "Queued full-time result embed: Belgium 3 - 2 Senegal."
    record = json.loads((tmp_path / "JSON" / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["kind"] == "fixture_result"
    assert record["data"] == {
        "fixture_id": "M2",
        "home": "Belgium",
        "away": "Senegal",
        "home_score": 3,
        "away_score": 2,
        "winner_side": "home",
        "channel": "belgium-senegal",
        "live_stats": [{"event_type": "extra_time", "label": "Extra Time", "match_time": ""}],
    }


def test_resolve_last_completed_channel_fixture_picks_latest_saved_match(tmp_path):
    cog = _cog(tmp_path)
    cog._write_json_atomic(cog.matches_path, [
        {"id": "old", "home": "A", "away": "B", "channel": "match-live", "status": "completed"},
        {"id": "live", "home": "A", "away": "C", "channel": "match-live", "status": "live"},
        {"id": "latest", "home": "A", "away": "D", "channel": "match-live", "status": "finished"},
    ])

    class DummyCtx:
        class Channel:
            name = "match-live"
        channel = Channel()

    fixture, fixtures, container, key, error = cog._resolve_last_completed_channel_fixture(DummyCtx())

    assert fixture["id"] == "latest"
    assert [item["id"] for item in fixtures] == ["old", "live", "latest"]
    assert container is None
    assert key == ""
    assert error == ""


def test_resolve_last_completed_channel_fixture_falls_back_to_last_completed_match(tmp_path):
    cog = _cog(tmp_path)
    cog._write_json_atomic(cog.matches_path, [
        {"id": "older", "home": "A", "away": "B", "channel": "group-a", "status": "completed"},
        {"id": "upcoming", "home": "A", "away": "C", "channel": "other", "status": "scheduled"},
        {"id": "last-on", "home": "A", "away": "D", "channel": "group-b", "status": "final"},
    ])

    class DummyCtx:
        class Channel:
            name = "admin-controls"
        channel = Channel()

    fixture, fixtures, container, key, error = cog._resolve_last_completed_channel_fixture(DummyCtx())

    assert fixture["id"] == "last-on"
    assert [item["id"] for item in fixtures] == ["older", "upcoming", "last-on"]
    assert container is None
    assert key == ""
    assert error == ""


def test_remake_embed_command_reposts_last_completed_channel_fixture(tmp_path):
    cog = _cog(tmp_path)
    cog._write_json_atomic(cog.matches_path, [
        {
            "id": "M3",
            "home": "France",
            "away": "Germany",
            "channel": "group-a",
            "status": "completed",
            "home_score": 1,
            "away_score": 1,
            "winner_side": "draw",
            "live_stats": [],
        }
    ])

    class DummyCtx:
        class Message:
            async def delete(self):
                return None
        class Channel:
            name = "group-a"
        message = Message()
        channel = Channel()
        sent = []
        async def send(self, message, delete_after=None):
            self.sent.append((message, delete_after))

    import asyncio
    ctx = DummyCtx()
    asyncio.run(cog.remake_embed.callback(cog, ctx))

    assert ctx.sent == [("Queued full-time result embed: France 1 - 1 Germany.", 12)]
    record = json.loads((tmp_path / "JSON" / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["kind"] == "fixture_result"
    assert record["data"]["fixture_id"] == "M3"
    assert record["data"]["winner_side"] == "draw"
