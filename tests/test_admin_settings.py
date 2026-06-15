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

    # Seed config with a single admin user so test session auth can pass.
    (base_dir / "config.json").write_text(json.dumps({"ADMIN_IDS": ["123"]}), encoding="utf-8")

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
        # The admin route checks this exact session key for current user.
        sess["wc_user"] = {"discord_id": "123", "username": "admin"}

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
