import json
from pathlib import Path

from flask import Flask

from routes_admin import create_admin_routes


def _client_with_user(tmp_path: Path, user: dict, config: dict | None = None):
    """Build an admin route client with an OAuth-like user stored in session."""
    base_dir = tmp_path
    (base_dir / "JSON").mkdir(parents=True, exist_ok=True)
    (base_dir / "config.json").write_text(json.dumps(config or {}), encoding="utf-8")
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
        sess["wc_user"] = user
    return client


def test_referee_role_unlocks_admin_view(tmp_path):
    """A Discord user with Referee role can use admin endpoints without config IDs."""
    client = _client_with_user(tmp_path, {"discord_id": "999", "roles": ["Referee"]})

    resp = client.get("/admin/auth/status")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["is_admin"] is True
    assert payload["unlocked"] is True


def test_config_admin_id_no_longer_unlocks_admin_view(tmp_path):
    """Static ADMIN_IDS do not grant admin access without the Discord Referee role."""
    client = _client_with_user(
        tmp_path,
        {"discord_id": "123", "roles": []},
        config={"ADMIN_IDS": ["123"]},
    )

    resp = client.get("/admin/auth/status")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["is_admin"] is False
    assert payload["unlocked"] is False


def test_admin_delete_bet_removes_record_and_queues_discord_delete(tmp_path):
    """Deleting a bet should remove it from JSON and enqueue message metadata for Discord cleanup."""
    client = _client_with_user(tmp_path, {"discord_id": "999", "roles": ["Referee"]})
    json_dir = tmp_path / "JSON"
    (json_dir / "bets.json").write_text(json.dumps([
        {
            "bet_id": "00001",
            "bet_title": "Delete me",
            "channel_id": "111",
            "message_id": "222",
            "option1_user_id": "1",
            "option2_user_id": "2",
        },
        {"bet_id": "00002", "bet_title": "Keep me"},
    ]), encoding="utf-8")

    resp = client.delete("/admin/bets/00001")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    bets = json.loads((json_dir / "bets.json").read_text(encoding="utf-8"))
    assert [b["bet_id"] for b in bets] == ["00002"]

    lines = [ln for ln in (json_dir / "bot_commands.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    cmd = json.loads(lines[-1])
    assert cmd["kind"] == "bet_deleted"
    assert cmd["data"] == {"bet_id": "00001", "channel_id": "111", "message_id": "222"}
