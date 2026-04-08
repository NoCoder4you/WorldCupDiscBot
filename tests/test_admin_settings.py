import json
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
    """Admin result endpoint should persist home/away scores for a fixture."""
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

    resp = client.post(
        "/admin/fixtures/result",
        json={"match_id": "M73", "home_score": 2, "away_score": 1},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["home_score"] == 2
    assert payload["away_score"] == 1

    stored = json.loads(matches_path.read_text(encoding="utf-8"))
    assert stored[0]["home_score"] == 2
    assert stored[0]["away_score"] == 1


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
