import json
import time
from pathlib import Path

from flask import Flask

from routes_admin import create_admin_routes


def _build_admin_client(tmp_path: Path):
    """Create an app client wired with admin routes and a temporary BASE_DIR."""
    base_dir = tmp_path
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    # Admin authorization comes from the Discord Referee role captured at OAuth login.
    (base_dir / "config.json").write_text(json.dumps({}), encoding="utf-8")

    ctx = {
        "BASE_DIR": str(base_dir),
        "is_bot_running": lambda: False,
        "start_bot": lambda: True,
        "stop_bot": lambda: True,
        "restart_bot": lambda: True,
        "get_bot_resource_usage": lambda: {},
        "bot_last_start_ref": {"value": None},
        "bot_last_stop_ref": {"value": None},
    }

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(create_admin_routes(ctx))

    client = app.test_client()
    with client.session_transaction() as sess:
        # The admin route checks this exact session key and requires Referee role membership.
        sess["wc_user"] = {"discord_id": "123", "username": "admin", "roles": ["Referee"]}

    return client, json_dir


def test_enabling_maintenance_mode_enqueues_announcement_command(tmp_path):
    """Enabling maintenance mode should enqueue a Discord announcements message."""
    client, json_dir = _build_admin_client(tmp_path)

    resp = client.post("/admin/settings", json={"maintenance_mode": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["maintenance_mode"] is True

    queue_path = json_dir / "bot_commands.jsonl"
    assert queue_path.exists()

    commands = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    maintenance_cmds = [c for c in commands if c.get("kind") == "maintenance_mode_enabled"]
    assert len(maintenance_cmds) == 1

    cmd_data = maintenance_cmds[0].get("data") or {}
    assert cmd_data.get("channel") == "announcements"
    assert "Maintenance Mode Enabled" in str(cmd_data.get("message") or "")


def test_disabling_maintenance_mode_enqueues_disabled_announcement(tmp_path):
    """Disabling maintenance mode should enqueue a clear recovery announcement."""
    client, json_dir = _build_admin_client(tmp_path)

    # First enable mode so a later disable is a real state transition.
    first = client.post("/admin/settings", json={"maintenance_mode": True})
    assert first.status_code == 200

    second = client.post("/admin/settings", json={"maintenance_mode": False})
    assert second.status_code == 200
    payload = second.get_json()
    assert payload["maintenance_mode"] is False

    queue_path = json_dir / "bot_commands.jsonl"
    commands = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    enabled_cmds = [c for c in commands if c.get("kind") == "maintenance_mode_enabled"]
    disabled_cmds = [c for c in commands if c.get("kind") == "maintenance_mode_disabled"]

    # The first toggle-on emits the enable notice and toggle-off emits recovery.
    assert len(enabled_cmds) == 1
    assert len(disabled_cmds) == 1

    disabled_data = disabled_cmds[0].get("data") or {}
    assert disabled_data.get("channel") == "announcements"
    assert "Maintenance Mode Disabled" in str(disabled_data.get("message") or "")


def test_admin_fixture_result_updates_match_scores(tmp_path):
    """Saving a score should persist it and run the Match Picks settlement."""
    client, json_dir = _build_admin_client(tmp_path)
    matches_path = json_dir / "matches.json"
    matches_path.write_text(
        json.dumps(
            [
                {
                    "id": "M73",
                    "home": "2A",
                    "away": "2B",
                    "utc": "2026-06-28T19:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    (json_dir / "fan_votes.json").write_text(
        json.dumps({
            "fixtures": {
                "M73": {
                    "home": 1,
                    "away": 1,
                    "draw": 0,
                    "voters": {"10": "home", "20": "away"},
                }
            }
        }),
        encoding="utf-8",
    )

    resp = client.post(
        "/admin/fixtures/result",
        json={"match_id": "M73", "home_score": 2, "away_score": 1},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["home_score"] == 2
    assert payload["away_score"] == 1
    assert payload["winner_side"] == "home"

    stored = json.loads(matches_path.read_text(encoding="utf-8"))
    assert stored[0]["home_score"] == 2
    assert stored[0]["away_score"] == 1
    assert stored[0]["status"] == "final"
    assert stored[0]["result_source"] == "admin"
    assert isinstance(stored[0]["result_saved_at"], int)

    winners = json.loads((json_dir / "fan_winners.json").read_text(encoding="utf-8"))
    assert winners["M73"]["winner_side"] == "home"
    assert winners["M73"]["winner_team"] == "2A"

    snapshots = json.loads((json_dir / "fan_vote_snapshots.json").read_text(encoding="utf-8"))
    assert snapshots["fixtures"]["M73"]["home_votes"] == 1
    assert snapshots["fixtures"]["M73"]["away_votes"] == 1
    assert snapshots["fixtures"]["M73"]["winner_side"] == "home"

    settled_events = json.loads(
        (json_dir / "fan_zone_results.json").read_text(encoding="utf-8")
    )["events"]
    voter_results = {
        event["discord_id"]: event["result"]
        for event in settled_events
        if event.get("fixture_id") == "M73"
    }
    assert voter_results == {"10": "win", "20": "lose"}

    commands = [
        json.loads(line)
        for line in (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result_command = next(command for command in commands if command.get("kind") == "fanzone_winner")
    assert result_command["data"]["home"] == "2A"
    assert result_command["data"]["away"] == "2B"
    assert result_command["data"]["home_score"] == 2
    assert result_command["data"]["away_score"] == 1
    assert result_command["data"]["winner_side"] == "home"
    assert result_command["data"]["suppress_public"] is True

    fixture_command = next(command for command in commands if command.get("kind") == "fixture_result")
    assert fixture_command["data"]["home_score"] == 2
    assert fixture_command["data"]["away_score"] == 1
    assert fixture_command["data"]["winner_side"] == "home"
    assert fixture_command["data"]["channel"] == "fanzone"


def test_admin_fixture_result_unchanged_save_is_idempotent(tmp_path):
    """Re-saving the same result must not repeat announcements or notifications."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{"id": "M73", "home": "2A", "away": "2B"}]),
        encoding="utf-8",
    )

    payload = {"match_id": "M73", "home_score": 2, "away_score": 1}
    first = client.post("/admin/fixtures/result", json=payload)
    second = client.post("/admin/fixtures/result", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["unchanged"] is True
    commands = [
        json.loads(line)
        for line in (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [command["kind"] for command in commands].count("fanzone_winner") == 1
    assert [command["kind"] for command in commands].count("fixture_result") == 1


def test_knockout_progression_accepts_prefixed_match_ids(tmp_path):
    """Saving results for M/W-prefixed knockout IDs should populate the next bracket match."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([
            {"id": "W74", "home": "Germany", "away": "Paraguay", "stage": "Round of 32"},
            {"id": "M77", "home": "France", "away": "Sweden", "stage": "Round of 32"},
        ]),
        encoding="utf-8",
    )

    first = client.post(
        "/admin/fixtures/result",
        json={"match_id": "W74", "home_score": 2, "away_score": 0},
    )
    second = client.post(
        "/admin/fixtures/result",
        json={"match_id": "M77", "home_score": 1, "away_score": 3},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    slots = json.loads((json_dir / "bracket_slots.json").read_text(encoding="utf-8"))
    assert slots["Round of 16"]["left"]["1"]["home"] == "Germany"
    assert slots["Round of 16"]["left"]["1"]["away"] == "Sweden"
    assert slots["Round of 16"]["left"]["1"]["match_id"] == "89"

    stored = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))
    advanced = next(match for match in stored if match["id"] == "89")
    assert advanced["home"] == "Germany"
    assert advanced["away"] == "Sweden"
    assert advanced["stage"] == "Round of 16"
    assert advanced["bracket_slot"] == 1


def test_knockout_progression_partially_updates_and_preserves_real_fixture_id(tmp_path):
    """Round-of-16 slot 1 should advance each feeder independently without losing metadata."""
    client, json_dir = _build_admin_client(tmp_path)
    matches_path = json_dir / "matches.json"
    real_id = "BRKT-R16-L1-W74-W77"
    matches_path.write_text(
        json.dumps([
            {"id": "BRKT-R32-L2-GER-PAR", "label": "M74", "home": "Germany", "away": "Paraguay", "stage": "Round of 32"},
            {"id": "BRKT-R32-L5-SWE-NOR", "label": "M77", "home": "Norway", "away": "Sweden", "stage": "Round of 32"},
            {
                "id": real_id,
                "label": "M89",
                "home": "W74",
                "away": "W77",
                "utc": "2026-07-04T21:00:00Z",
                "stadium": "MetLife Stadium",
                "stage": "Round of 16",
                "bracket_slot": 1,
            },
        ]),
        encoding="utf-8",
    )
    (json_dir / "bracket_slots.json").write_text(
        json.dumps({
            "Round of 16": {
                "left": {
                    "1": {
                        "match_id": real_id,
                        "label": "M89",
                        "home": "W74",
                        "away": "W77",
                        "utc": "2026-07-04T21:00:00Z",
                    }
                }
            }
        }),
        encoding="utf-8",
    )

    first = client.post(
        "/admin/fixtures/result",
        json={"match_id": "BRKT-R32-L2-GER-PAR", "home_score": 1, "away_score": 1, "winner_side": "away"},
    )
    assert first.status_code == 200
    slots = json.loads((json_dir / "bracket_slots.json").read_text(encoding="utf-8"))
    assert slots["Round of 16"]["left"]["1"]["match_id"] == real_id
    assert slots["Round of 16"]["left"]["1"]["home"] == "Paraguay"
    assert slots["Round of 16"]["left"]["1"]["away"] == "W77"

    stored = json.loads(matches_path.read_text(encoding="utf-8"))
    advanced = next(match for match in stored if match["id"] == real_id)
    assert advanced["home"] == "Paraguay"
    assert advanced["away"] == "W77"
    assert advanced["utc"] == "2026-07-04T21:00:00Z"
    assert advanced["stadium"] == "MetLife Stadium"

    second = client.post(
        "/admin/fixtures/result",
        json={"match_id": "BRKT-R32-L5-SWE-NOR", "home_score": 0, "away_score": 2},
    )
    assert second.status_code == 200
    slots = json.loads((json_dir / "bracket_slots.json").read_text(encoding="utf-8"))
    assert slots["Round of 16"]["left"]["1"]["home"] == "Paraguay"
    assert slots["Round of 16"]["left"]["1"]["away"] == "Sweden"

    correction = client.post(
        "/admin/fixtures/result",
        json={"match_id": "BRKT-R32-L2-GER-PAR", "home_score": 2, "away_score": 0},
    )
    assert correction.status_code == 200
    slots = json.loads((json_dir / "bracket_slots.json").read_text(encoding="utf-8"))
    assert slots["Round of 16"]["left"]["1"]["home"] == "Germany"
    assert slots["Round of 16"]["left"]["1"]["away"] == "Sweden"
    stored = json.loads(matches_path.read_text(encoding="utf-8"))
    advanced = next(match for match in stored if match["id"] == real_id)
    assert advanced["home"] == "Germany"
    assert advanced["away"] == "Sweden"
    assert advanced["id"] == real_id


def test_admin_bracket_slot_edit_replaces_generated_placeholder_teams(tmp_path):
    """Editing a generated knockout fixture should replace W/M placeholders on the saved match."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "bracket_slots.json").write_text(
        json.dumps({
            "Round of 16": {
                "left": {
                    "1": {
                        "label": "",
                        "match_id": "W89",
                        "home": "W74",
                        "away": "W77",
                        "utc": "2026-07-04T21:00:00Z",
                    }
                }
            }
        }),
        encoding="utf-8",
    )
    (json_dir / "matches.json").write_text(
        json.dumps([
            {
                "id": "W89",
                "home": "W74",
                "away": "W77",
                "stage": "Round of 16",
                "bracket_slot": 1,
            }
        ]),
        encoding="utf-8",
    )

    response = client.post("/admin/bracket_slots", json={
        "stage": "Round of 16",
        "side": "left",
        "slot": 1,
        "match_id": "W89",
        "home": "Paraguay",
        "away": "W77",
        "utc": "2026-07-04T21:00:00Z",
    })

    assert response.status_code == 200
    matches = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))
    assert matches[0]["id"] == "W89"
    assert matches[0]["home"] == "Paraguay"
    assert matches[0]["away"] == "W77"

    slots = json.loads((json_dir / "bracket_slots.json").read_text(encoding="utf-8"))
    assert slots["Round of 16"]["left"]["1"]["home"] == "Paraguay"
    assert slots["Round of 16"]["left"]["1"]["away"] == "W77"

def test_quick_match_announcement_uses_group_channel(tmp_path):
    """Live group-stage updates should be queued for the fixture's group channel."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M12",
            "home": "Argentina",
            "away": "Algeria",
            "group": "J",
            "stage": "Group Stage",
            "utc": "2026-06-15T18:00:00Z",
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={
            "match_id": "M12",
            "event_type": "goal",
            "country": "Argentina",
            "match_time": "23",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["channel"] == "group-j"
    command = json.loads(
        (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )
    assert command["kind"] == "quick_match_announcement"
    assert command["data"]["event_label"] == "Goal"
    assert command["data"]["message"] == "Argentina 1 - 0 Algeria"
    assert command["data"]["home_score"] == 1
    assert command["data"]["away_score"] == 0
    assert command["data"]["country"] == "Argentina"
    assert command["data"]["channel"] == "group-j"

    stored = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))
    assert len(stored[0]["live_stats"]) == 1
    assert stored[0]["live_stats"][0]["event_type"] == "goal"
    assert stored[0]["live_stats"][0]["label"] == "Goal"
    assert stored[0]["live_stats"][0]["message"] == "Argentina 1 - 0 Algeria"
    assert stored[0]["live_stats"][0]["country"] == "Argentina"
    assert stored[0]["live_stats"][0]["match_time"] == "23"
    assert isinstance(stored[0]["live_stats"][0]["ts"], int)


def test_quick_match_announcement_uses_knockout_channel(tmp_path):
    """Knockout updates should use the dedicated channel mapped from their stage."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M88",
            "home": "France",
            "away": "Brazil",
            "stage": "Quarter-finals",
            "utc": "2026-07-09T19:00:00Z",
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={
            "match_id": "M88",
            "event_type": "yellow_card",
            "country": "France",
            "match_time": "90+1",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["channel"] == "quarter-finals"


def test_quick_match_announcement_validates_event_country_and_time(tmp_path):
    """Quick options must reject unsupported actions, teams, and match times."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{"id": "M12", "home": "A", "away": "B", "group": "A"}]),
        encoding="utf-8",
    )

    invalid_event = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "full_time", "country": "A", "match_time": "90"},
    )
    invalid_country = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "red_card", "country": "C", "match_time": "45"},
    )
    invalid_time = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "goal", "country": "A", "match_time": "90++1"},
    )

    assert invalid_event.status_code == 400
    assert invalid_event.get_json()["error"] == "invalid_event_type"
    assert invalid_country.status_code == 400
    assert invalid_country.get_json()["error"] == "invalid_country"
    assert invalid_time.status_code == 400
    assert invalid_time.get_json()["error"] == "invalid_match_time"


def test_half_time_quick_announcement_does_not_require_country_or_match_time(tmp_path):
    """Half-time updates should post without asking for a team or minute."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M12",
            "home": "A",
            "away": "B",
            "group": "A",
            "live_stats": [
                {"event_type": "goal", "country": "A", "match_time": "7"},
                {"event_type": "goal", "country": "B", "match_time": "45+2"},
                {"event_type": "goal", "country": "A", "match_time": "50"},
            ],
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "half_time"},
    )

    assert response.status_code == 200
    saved_match = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))[0]
    half_time = next(
        event for event in saved_match["live_stats"]
        if event["event_type"] == "half_time"
    )
    assert half_time["country"] == ""
    command = json.loads(
        (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )
    assert command["data"]["message"] == "A 1 - 1 B"
    assert command["data"]["home_score"] == 1
    assert command["data"]["away_score"] == 1
    assert command["data"]["country"] == ""
    assert command["data"]["match_time"] == ""


def test_quick_announcement_persists_late_event_in_match_clock_order(tmp_path):
    """A late-reported incident should be inserted into the saved timeline."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M12",
            "home": "A",
            "away": "B",
            "group": "A",
            "live_stats": [
                {"event_type": "half_time", "label": "Half Time", "match_time": ""},
                {"event_type": "goal", "label": "Goal", "country": "A", "match_time": "66"},
            ],
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "yellow_card", "country": "B", "match_time": "34"},
    )

    assert response.status_code == 200
    saved_match = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))[0]
    assert [
        (event["event_type"], event["match_time"])
        for event in saved_match["live_stats"]
    ] == [
        ("yellow_card", "34"),
        ("half_time", ""),
        ("goal", "66"),
    ]
    assert response.get_json()["live_stats"] == saved_match["live_stats"]


def test_fixture_result_includes_penalty_score_in_command(tmp_path):
    """A tied knockout result should preserve the entered shootout score."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M80",
            "home": "A",
            "away": "B",
            "stage": "Round of 16",
        }]),
        encoding="utf-8",
    )

    response = client.post("/admin/fixtures/result", json={
        "match_id": "M80",
        "home_score": 1,
        "away_score": 1,
        "winner_side": "home",
        "home_penalties": 5,
        "away_penalties": 4,
    })

    assert response.status_code == 200
    commands = [
        json.loads(line)
        for line in (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    fixture_command = next(command for command in commands if command["kind"] == "fixture_result")
    assert fixture_command["data"]["home_penalties"] == 5
    assert fixture_command["data"]["away_penalties"] == 4


def test_full_time_result_command_includes_persisted_live_stats(tmp_path):
    """Full time should automatically attach recorded events to the result embed payload."""
    client, json_dir = _build_admin_client(tmp_path)
    live_stats = [
        {
            "event_type": "goal",
            "label": "Goal",
            "message": "12' Team A opened the scoring.",
            "ts": 100,
        },
        {
            "event_type": "yellow_card",
            "label": "Yellow Card",
            "message": "44' Booking for Team B.",
            "ts": 200,
        },
    ]
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M20",
            "home": "Team A",
            "away": "Team B",
            "group": "A",
            "live_stats": live_stats,
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/result",
        json={"match_id": "M20", "home_score": 2, "away_score": 1},
    )

    assert response.status_code == 200
    commands = [
        json.loads(line)
        for line in (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result_command = next(command for command in commands if command["kind"] == "fixture_result")
    assert result_command["data"]["live_stats"] == live_stats
    settlement_command = next(command for command in commands if command["kind"] == "fanzone_winner")
    assert settlement_command["data"]["live_stats"] == live_stats


def test_admin_fixture_result_correction_replaces_events_without_owner_dms(tmp_path):
    """Corrections replace stored outcomes and do not send contradictory owner DMs."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{"id": "M73", "home": "2A", "away": "2B"}]),
        encoding="utf-8",
    )
    (json_dir / "fan_votes.json").write_text(
        json.dumps({
            "fixtures": {
                "M73": {
                    "home": 1,
                    "away": 1,
                    "draw": 0,
                    "voters": {"10": "home", "20": "away"},
                }
            }
        }),
        encoding="utf-8",
    )
    (json_dir / "players.json").write_text(
        json.dumps({
            "record-a": {
                "teams": [{"team": "2A", "ownership": {"main_owner": "100", "split_with": []}}]
            },
            "record-b": {
                "teams": [{"team": "2B", "ownership": {"main_owner": "200", "split_with": []}}]
            },
        }),
        encoding="utf-8",
    )

    first = client.post(
        "/admin/fixtures/result",
        json={"match_id": "M73", "home_score": 2, "away_score": 1},
    )
    correction = client.post(
        "/admin/fixtures/result",
        json={"match_id": "M73", "home_score": 1, "away_score": 2},
    )

    assert first.status_code == 200
    assert correction.status_code == 200
    assert correction.get_json()["corrected"] is True
    events = json.loads((json_dir / "fan_zone_results.json").read_text(encoding="utf-8"))["events"]
    voter_results = {
        event["discord_id"]: event["result"]
        for event in events
        if event.get("fixture_id") == "M73"
    }
    assert voter_results == {"10": "lose", "20": "win"}
    commands = [
        json.loads(line)
        for line in (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    settlements = [command for command in commands if command.get("kind") == "fanzone_winner"]
    assert settlements[0]["data"]["winner_owner_ids"] == ["100"]
    assert settlements[0]["data"]["loser_owner_ids"] == ["200"]
    assert settlements[1]["data"]["winner_owner_ids"] == []
    assert settlements[1]["data"]["loser_owner_ids"] == []
    fixture_results = [command for command in commands if command.get("kind") == "fixture_result"]
    assert len(fixture_results) == 2
    assert fixture_results[1]["data"]["corrected"] is True
    assert fixture_results[1]["data"]["winner_side"] == "away"


def test_admin_fixture_result_rejects_invalid_score(tmp_path):
    """Result endpoint should reject non-numeric or negative score values."""
    client, json_dir = _build_admin_client(tmp_path)
    matches_path = json_dir / "matches.json"
    matches_path.write_text(json.dumps([{"id": "M73"}]), encoding="utf-8")

    bad = client.post(
        "/admin/fixtures/result",
        json={"match_id": "M73", "home_score": -1, "away_score": "x"},
    )
    assert bad.status_code == 400
    payload = bad.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "invalid_score"


def test_admin_tied_fixture_result_accepts_penalty_winner(tmp_path):
    """A tied knockout score may settle to the separately selected advancing side."""
    client, json_dir = _build_admin_client(tmp_path)
    matches_path = json_dir / "matches.json"
    matches_path.write_text(
        json.dumps([{"id": "M97", "home": "USA", "away": "Canada", "stage": "Quarter-finals"}]),
        encoding="utf-8",
    )

    resp = client.post(
        "/admin/fixtures/result",
        json={
            "match_id": "M97",
            "home_score": 1,
            "away_score": 1,
            "winner_side": "away",
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["winner_side"] == "away"
    stored = json.loads(matches_path.read_text(encoding="utf-8"))
    assert stored[0]["home_score"] == 1
    assert stored[0]["away_score"] == 1
    assert stored[0]["winner_side"] == "away"
    winners = json.loads((json_dir / "fan_winners.json").read_text(encoding="utf-8"))
    assert winners["M97"]["winner_side"] == "away"
    assert winners["M97"]["winner_team"] == "Canada"


def test_admin_tied_fixture_result_derives_winner_from_penalty_score(tmp_path):
    """A shootout score should determine the advancing side without manual input."""
    client, json_dir = _build_admin_client(tmp_path)
    matches_path = json_dir / "matches.json"
    matches_path.write_text(
        json.dumps([{"id": "M97", "home": "USA", "away": "Canada", "stage": "Quarter-finals"}]),
        encoding="utf-8",
    )

    resp = client.post(
        "/admin/fixtures/result",
        json={
            "match_id": "M97",
            "home_score": 1,
            "away_score": 1,
            "home_penalties": 4,
            "away_penalties": 5,
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["winner_side"] == "away"
    stored = json.loads(matches_path.read_text(encoding="utf-8"))
    assert stored[0]["winner_side"] == "away"
    assert stored[0]["home_penalties"] == 4
    assert stored[0]["away_penalties"] == 5


def test_admin_fixture_result_rejects_penalty_winner_for_non_tied_score(tmp_path):
    """A shootout winner must not conflict with a decisive official score."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{"id": "M97", "home": "USA", "away": "Canada"}]),
        encoding="utf-8",
    )

    resp = client.post(
        "/admin/fixtures/result",
        json={
            "match_id": "M97",
            "home_score": 2,
            "away_score": 1,
            "winner_side": "away",
        },
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "winner_side_requires_tied_score"


def test_admin_fixture_result_rejects_penalty_winner_for_group_match(tmp_path):
    """Only knockout fixtures can name an advancing side after a tied score."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M10",
            "home": "USA",
            "away": "Canada",
            "stage": "Group Stage",
        }]),
        encoding="utf-8",
    )

    resp = client.post(
        "/admin/fixtures/result",
        json={
            "match_id": "M10",
            "home_score": 1,
            "away_score": 1,
            "winner_side": "home",
        },
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "winner_side_requires_knockout_match"


def test_auto_backup_runs_on_any_admin_request_when_due(tmp_path):
    """Auto backup should run from admin traffic without opening the backups page."""
    client, json_dir = _build_admin_client(tmp_path)
    settings_path = json_dir / "admin_settings.json"
    now = int(time.time())
    settings_path.write_text(
        json.dumps(
            {
                "AUTO_BACKUP_ENABLED": True,
                "AUTO_BACKUP_INTERVAL_HOURS": 6,
                # Make the next request clearly overdue.
                "AUTO_BACKUP_LAST_TS": now - (7 * 3600),
            }
        ),
        encoding="utf-8",
    )

    resp = client.get("/admin/auth/status")
    assert resp.status_code == 200

    backups_dir = tmp_path / "BACKUPS"
    backups = list(backups_dir.glob("*.zip"))
    assert backups, "expected a backup zip to be created by the before_request scheduler"


def test_admin_stage_placement_update_queues_discord_embed_command(tmp_path):
    """Ownership page placement changes should enqueue the normal Discord embed command."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "players.json").write_text(
        json.dumps({
            "200": {
                "display_name": "Owner",
                "teams": [{"team": "Brazil", "ownership": {"main_owner": 200, "split_with": []}}],
            }
        }),
        encoding="utf-8",
    )
    (json_dir / "notification_settings.json").write_text(json.dumps({"200": {"channel": "dms"}}), encoding="utf-8")
    (json_dir / "team_stage.json").write_text(json.dumps({"Brazil": "Final"}), encoding="utf-8")

    response = client.post("/admin/teams/stage", json={"team": "Brazil", "stage": "2nd Place"})

    assert response.status_code == 200
    assert response.get_json()["stage"] == "2nd Place"
    command = json.loads((json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert command["kind"] == "team_stage_progress"
    assert command["data"] == {
        "team": "Brazil",
        "stage": "2nd Place",
        "previous_stage": "Final",
        "owner_ids": ["200"],
        "channel": "announcements",
    }


def test_admin_stage_alias_is_canonicalized_before_queueing(tmp_path):
    """Aliases such as Runner-up should still save and announce canonical placement labels."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "team_stage.json").write_text(json.dumps({"Brazil": "Final"}), encoding="utf-8")

    response = client.post("/admin/teams/stage", json={"team": "Brazil", "stage": "Runner-up"})

    assert response.status_code == 200
    assert response.get_json()["stage"] == "2nd Place"
    saved = json.loads((json_dir / "team_stage.json").read_text(encoding="utf-8"))
    assert saved["Brazil"] == "2nd Place"
    command = json.loads((json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert command["data"]["stage"] == "2nd Place"

def test_admin_ownership_reassign_rewrites_players_json(tmp_path):
    """Reassigning ownership should move the team row to the new main owner."""
    client, json_dir = _build_admin_client(tmp_path)
    players_path = json_dir / "players.json"
    players_path.write_text(
        json.dumps(
            {
                "200": {
                    "display_name": "Old Owner",
                    "teams": [
                        {
                            "team": "Brazil",
                            "ownership": {
                                "main_owner": 200,
                                "split_with": [300],
                                "percentages": {"200": 70, "300": 30},
                            },
                            "public_message_id": "abc123",
                        }
                    ],
                },
                "300": {
                    "display_name": "Split Owner",
                    "teams": [
                        {"team": "Brazil", "ownership": {"main_owner": 200, "split_with": []}}
                    ],
                },
                "400": {"display_name": "New Owner", "teams": []},
            }
        ),
        encoding="utf-8",
    )

    resp = client.post("/admin/ownership/reassign", json={"team": "Brazil", "new_owner_id": "400"})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["row"]["main_owner"]["id"] == "400"
    assert payload["row"]["split_with"] == [{"id": "300", "username": "300"}]

    players = json.loads(players_path.read_text(encoding="utf-8"))
    assert players["200"]["teams"] == []
    assert players["400"]["teams"] == [
        {
            "team": "Brazil",
            "ownership": {
                "main_owner": "400",
                "split_with": ["300"],
                "percentages": {"300": 30.0, "400": 70.0},
            },
            "public_message_id": "abc123",
        }
    ]
    assert players["300"]["teams"] == [
        {
            "team": "Brazil",
            "ownership": {"main_owner": "400", "split_with": []},
            "public_message_id": "abc123",
        }
    ]


def test_admin_ownership_reassign_removes_new_owner_from_split_list(tmp_path):
    """A split owner promoted to main owner must not remain a split owner too."""
    client, json_dir = _build_admin_client(tmp_path)
    players_path = json_dir / "players.json"
    players_path.write_text(
        json.dumps(
            {
                "200": {
                    "display_name": "Old Owner",
                    "teams": [
                        {"team": "Brazil", "ownership": {"main_owner": 200, "split_with": [300, 400]}}
                    ],
                },
                "300": {
                    "display_name": "Promoted Split",
                    "teams": [
                        {"team": "Brazil", "ownership": {"main_owner": 200, "split_with": []}}
                    ],
                },
                "400": {
                    "display_name": "Other Split",
                    "teams": [
                        {"team": "Brazil", "ownership": {"main_owner": 200, "split_with": []}}
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    resp = client.post("/admin/ownership/reassign", json={"team": "Brazil", "new_owner_id": "300"})

    assert resp.status_code == 200
    players = json.loads(players_path.read_text(encoding="utf-8"))
    assert players["200"]["teams"] == []
    assert players["300"]["teams"] == [
        {"team": "Brazil", "ownership": {"main_owner": "300", "split_with": ["400"]}}
    ]
    assert players["400"]["teams"] == [
        {"team": "Brazil", "ownership": {"main_owner": "300", "split_with": []}}
    ]


def test_admin_split_history_normalizes_owner_from_resolved_by(tmp_path):
    """Admin history should show the TO owner for legacy Discord-cog split logs."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "verified.json").write_text(json.dumps({
        "verified_users": [
            {"discord_id": "100", "display_name": "Siren"},
            {"discord_id": "200", "display_name": "Owner"},
        ]
    }), encoding="utf-8")
    (json_dir / "split_requests_log.json").write_text(json.dumps([
        {
            "request_id": "legacy-req",
            "status": "accepted",
            "team": "Brazil",
            "requester_id": 100,
            "resolved_by": 200,
            "timestamp": "2026-06-01T13:59:58+00:00",
        }
    ]), encoding="utf-8")

    resp = client.get("/admin/splits/history")
    assert resp.status_code == 200
    events = resp.get_json()["events"]
    assert len(events) == 1
    row = events[0]
    assert row["action"] == "accepted"
    assert row["from"] == "Siren"
    assert row["to"] == "Owner"
    assert row["to_id"] == "200"
    assert row["main_owner_id"] == "200"


def test_helper_role_can_use_only_dashboard_quick_options(tmp_path):
    """Discord users with the Helper role can operate quick options without full admin rights."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M90",
            "home": "France",
            "away": "Germany",
            "group": "A",
            "stage": "Group Stage",
            "utc": "2026-06-15T18:00:00Z",
        }]),
        encoding="utf-8",
    )
    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "456", "username": "helper", "roles": ["Helper"]}

    status = client.get("/admin/auth/status")
    assert status.status_code == 200
    assert status.get_json()["unlocked"] is False
    assert status.get_json()["can_use_quick_options"] is True

    fixtures = client.get("/admin/fixtures")
    assert fixtures.status_code == 200
    assert fixtures.get_json()["fixtures"][0]["id"] == "M90"

    quick = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M90", "event_type": "half_time"},
    )
    assert quick.status_code == 200

    settings = client.post("/admin/settings", json={"maintenance_mode": True})
    assert settings.status_code == 401



def test_penalty_quick_announcement_records_decision_without_goal(tmp_path):
    """Penalty quick options announce the referee decision without increasing the score."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M12",
            "home": "A",
            "away": "B",
            "group": "A",
            "live_stats": [{"event_type": "goal", "label": "Goal", "country": "B", "match_time": "10"}],
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "penalty", "country": "A", "match_time": "52"},
    )

    assert response.status_code == 200
    saved_match = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))[0]
    assert [(event["event_type"], event.get("country"), event.get("match_time")) for event in saved_match["live_stats"]] == [
        ("goal", "B", "10"),
        ("penalty", "A", "52"),
    ]
    command = json.loads((json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert command["data"]["event_label"] == "Penalty"
    assert command["data"]["message"] == "A 0 - 1 B"
    assert command["data"]["home_score"] == 0
    assert command["data"]["away_score"] == 1


def test_referee_decision_quick_options_record_without_changing_score(tmp_path):
    """VAR and referee quick options should preserve the score while adding timeline context."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M13",
            "home": "A",
            "away": "B",
            "group": "A",
            "live_stats": [{"event_type": "goal", "label": "Goal", "country": "A", "match_time": "10"}],
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M13", "event_type": "var_decision", "country": "B", "match_time": "61"},
    )

    assert response.status_code == 200
    saved_match = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))[0]
    assert [(event["event_type"], event.get("country"), event.get("match_time")) for event in saved_match["live_stats"]] == [
        ("goal", "A", "10"),
        ("var_decision", "B", "61"),
    ]
    command = json.loads((json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert command["data"]["event_label"] == "VAR Decision"
    assert command["data"]["message"] == "A 1 - 0 B"
    assert command["data"]["home_score"] == 1
    assert command["data"]["away_score"] == 0


def test_extra_time_quick_announcement_is_match_state_without_country_or_time(tmp_path):
    """Extra-time quick options should announce match state without requiring a team."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M14",
            "home": "A",
            "away": "B",
            "group": "A",
            "live_stats": [{"event_type": "goal", "label": "Goal", "country": "A", "match_time": "10"}],
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M14", "event_type": "extra_time"},
    )

    assert response.status_code == 200
    saved_match = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))[0]
    assert [(event["event_type"], event.get("country"), event.get("match_time")) for event in saved_match["live_stats"]] == [
        ("goal", "A", "10"),
        ("extra_time", "", ""),
    ]
    command = json.loads((json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert command["data"]["event_label"] == "Extra Time"
    assert command["data"]["country"] == ""
    assert command["data"]["message"] == "A 1 - 0 B"

def test_disallowed_goal_rolls_back_latest_goal_and_announces_score(tmp_path):
    """Disallowed goal quick options should remove a scored goal and queue the corrected score."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M12",
            "home": "A",
            "away": "B",
            "group": "A",
            "live_stats": [
                {"event_type": "goal", "label": "Goal", "country": "A", "match_time": "12"},
                {"event_type": "goal", "label": "Goal", "country": "B", "match_time": "20"},
                {"event_type": "goal", "label": "Goal", "country": "A", "match_time": "27"},
            ],
        }]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "disallowed_goal", "country": "A", "match_time": "29"},
    )

    assert response.status_code == 200
    saved_match = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))[0]
    assert [
        (event["event_type"], event.get("country"), event.get("match_time"))
        for event in saved_match["live_stats"]
    ] == [
        ("goal", "A", "12"),
        ("goal", "B", "20"),
        ("disallowed_goal", "A", "29"),
    ]
    command = json.loads(
        (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )
    assert command["data"]["event_label"] == "Goal Disallowed"
    assert command["data"]["message"] == "A 1 - 1 B"
    assert command["data"]["home_score"] == 1
    assert command["data"]["away_score"] == 1


def test_disallowed_goal_requires_existing_goal_for_country(tmp_path):
    """Operators should get a validation error instead of a negative score."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{"id": "M12", "home": "A", "away": "B", "group": "A", "live_stats": []}]),
        encoding="utf-8",
    )

    response = client.post(
        "/admin/fixtures/quick-announce",
        json={"match_id": "M12", "event_type": "disallowed_goal", "country": "A", "match_time": "29"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "goal_not_found"


def test_admin_bracket_slot_edit_preserves_existing_match_id(tmp_path):
    """Editing a knockout slot should update the current match instead of creating a duplicate."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "bracket_slots.json").write_text(
        json.dumps({
            "Round of 16": {
                "left": {
                    "1": {
                        "label": "",
                        "match_id": "BRKT-R16-L1-USA-CAN",
                        "home": "USA",
                        "away": "Canada",
                        "utc": "2026-07-01T19:00:00Z",
                    }
                }
            }
        }),
        encoding="utf-8",
    )
    (json_dir / "matches.json").write_text(
        json.dumps([
            {
                "id": "BRKT-R16-L1-USA-CAN",
                "home": "USA",
                "away": "Canada",
                "stage": "Round of 16",
                "bracket_slot": 1,
            }
        ]),
        encoding="utf-8",
    )

    response = client.post("/admin/bracket_slots", json={
        "stage": "Round of 16",
        "side": "left",
        "slot": 1,
        # This is what the frontend used to generate after changing team names.
        # The server should keep targeting the saved match_id for this slot.
        "match_id": "BRKT-R16-L1-USA-MEX",
        "home": "USA",
        "away": "Mexico",
        "utc": "2026-07-01T20:00:00Z",
    })

    assert response.status_code == 200
    matches = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))
    assert len(matches) == 1
    assert matches[0]["id"] == "BRKT-R16-L1-USA-CAN"
    assert matches[0]["away"] == "Mexico"
    assert matches[0]["utc"] == "2026-07-01T20:00:00Z"

    slots = json.loads((json_dir / "bracket_slots.json").read_text(encoding="utf-8"))
    assert slots["Round of 16"]["left"]["1"]["match_id"] == "BRKT-R16-L1-USA-CAN"
    assert slots["Round of 16"]["left"]["1"]["away"] == "Mexico"


def test_quick_fixture_delay_accepts_half_and_negative_hours(tmp_path):
    """Quick Options can shift matches.json kickoff times by signed fractional hours."""
    client, json_dir = _build_admin_client(tmp_path)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M40",
            "home": "Japan",
            "away": "Ghana",
            "utc": "2026-06-20T18:00:00Z",
            "time": "2026-06-20T18:00:00Z",
        }]),
        encoding="utf-8",
    )

    delayed = client.post("/admin/fixtures/delay", json={"match_id": "M40", "hours": 0.5})
    assert delayed.status_code == 200
    assert delayed.get_json()["utc"] == "2026-06-20T18:30:00Z"

    brought_forward = client.post("/admin/fixtures/delay", json={"match_id": "M40", "hours": -1})
    assert brought_forward.status_code == 200
    assert brought_forward.get_json()["utc"] == "2026-06-20T17:30:00Z"

    saved_match = json.loads((json_dir / "matches.json").read_text(encoding="utf-8"))[0]
    assert saved_match["utc"] == "2026-06-20T17:30:00Z"
    assert saved_match["time"] == "2026-06-20T17:30:00Z"

    commands = [
        json.loads(line)
        for line in (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    delay_commands = [command for command in commands if command.get("kind") == "fixture_kickoff_adjusted"]
    assert len(delay_commands) == 2
    assert delay_commands[-1]["data"]["home"] == "Japan"
    assert delay_commands[-1]["data"]["away"] == "Ghana"
    assert delay_commands[-1]["data"]["previous_utc"] == "2026-06-20T18:30:00Z"
    assert delay_commands[-1]["data"]["utc"] == "2026-06-20T17:30:00Z"


def test_quick_fixture_delay_rejects_invalid_hours(tmp_path):
    """Invalid delay values should not mutate the matches JSON file."""
    client, json_dir = _build_admin_client(tmp_path)
    original = [{"id": "M41", "home": "A", "away": "B", "utc": "2026-06-20T18:00:00Z"}]
    (json_dir / "matches.json").write_text(json.dumps(original), encoding="utf-8")

    response = client.post("/admin/fixtures/delay", json={"match_id": "M41", "hours": "later"})

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_hours"
    assert json.loads((json_dir / "matches.json").read_text(encoding="utf-8")) == original
