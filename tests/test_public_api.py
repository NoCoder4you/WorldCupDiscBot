from flask import Flask
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ping_reports_bot_stopped(client):
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["bot_running"] is False


def test_teams_reads_from_json(client, app):
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    teams_path = json_dir / "teams.json"
    teams_path.write_text(json.dumps([{"name": "Alpha"}]), encoding="utf-8")

    resp = client.get("/api/teams")
    assert resp.status_code == 200
    assert resp.get_json() == [{"name": "Alpha"}]


def test_index_uses_document_relative_static_asset_paths(client):
    """
    Index assets should stay document-relative so reverse proxies that mount the
    app under a prefix (e.g. /panel/) do not break static URL resolution.
    """
    html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")

    # Positive checks: the intended mount-aware paths.
    assert 'href="style.css"' in html
    assert 'src="app.js"' in html
    assert 'src="user.js"' in html

    # Negative checks: guard against root-absolute regressions that 404 behind prefixes.
    assert 'href="/style.css"' not in html
    assert 'src="/app.js"' not in html
    assert 'src="/user.js"' not in html


def test_terms_uses_document_relative_static_asset_paths():
    """
    Terms assets should stay document-relative for prefix-based deployments
    (e.g. /panel/terms -> /panel/terms.css) to avoid 404s.
    """
    html = (ROOT / "WorldCupBot" / "static" / "terms.html").read_text(encoding="utf-8")

    # Positive checks: expected mount-aware asset references.
    assert 'href="terms.css"' in html
    assert 'src="terms.js"' in html

    # Negative checks: disallow root-absolute references that bypass mount prefixes.
    assert 'href="/terms.css"' not in html
    assert 'src="/terms.js"' not in html

def test_app_bootstraps_stage_constants_without_stage_js():
    """
    app.js now defines window.WorldCupStages when the standalone stage.js asset
    is unavailable so user-facing stage UI still works.
    """
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "if (!window.WorldCupStages) {" in app_js
    assert "const STAGE_ORDER = [" in app_js
    assert "const STAGE_PROGRESS = {" in app_js


def test_me_respects_masquerade_without_app_base_dir_config(tmp_path):
    """
    Ensure masquerade still works when app.config["BASE_DIR"] is unset.
    The route should fall back to the app static folder parent for config.json.
    """
    base_dir = tmp_path
    static_dir = base_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
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

    from routes_public import create_public_routes

    app = Flask(__name__, static_folder=str(static_dir))
    app.secret_key = "test-secret"
    # Intentionally do not set app.config["BASE_DIR"].

    root_bp, api_bp, auth_bp = create_public_routes(ctx)
    app.register_blueprint(root_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "123", "username": "admin"}
        sess["wc_masquerade_id"] = "999"

    resp = client.get("/api/me")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["is_admin"] is True
    assert data["masquerading_as"] == "999"


def test_app_js_has_no_known_truncated_syntax_tokens():
    """
    Guard against previously observed truncated JS tokens that produced
    `SyntaxError: Invalid or unexpected token` at runtime.
    """
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")

    # Broken patterns seen in production errors / prior diffs.
    assert "createElementNS('http:\\n" not in app_js
    assert "src=\"https:\\n" not in app_js
    assert '/\\/embed\\/avatars\\\\\n' not in app_js

    # Ensure repaired snippets are present.
    assert "createElementNS('http://www.w3.org/2000/svg', 'g')" in app_js
    assert "https://flagcdn.com/w20/${safeIso}.png" in app_js
    assert r"/\/embed\/avatars\//.test(String(v.avatar_url))" in app_js


def test_split_requests_respond_accept_updates_players_and_history(client, app):
    """Main owner should be able to accept a pending split request from the public web endpoint."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    # Seed minimal ownership data where user 200 is the main owner of Brazil.
    players_path = json_dir / "players.json"
    players_path.write_text(json.dumps({
        "200": {"display_name": "Owner", "teams": [{"team": "Brazil", "ownership": {"main_owner": 200, "split_with": []}}]},
        "100": {"display_name": "Requester", "teams": []},
    }), encoding="utf-8")

    split_requests_path = json_dir / "split_requests.json"
    split_requests_path.write_text(json.dumps({
        "req1": {
            "requester_id": 100,
            "main_owner_id": 200,
            "team": "Brazil",
            "expires_at": 4102444800,
            "requested_percentage": 25
        }
    }), encoding="utf-8")

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "200", "username": "owner"}

    resp = client.post('/api/split_requests/respond', json={"id": "req1", "action": "accept"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["event"]["action"] == "accepted"

    # Pending request should be removed.
    pending_after = json.loads(split_requests_path.read_text(encoding="utf-8"))
    assert "req1" not in pending_after

    # Owner entry should include requester in split_with.
    players_after = json.loads(players_path.read_text(encoding="utf-8"))
    owner_teams = players_after["200"]["teams"]
    brazil_owner_row = next(t for t in owner_teams if t["team"] == "Brazil")
    assert 100 in brazil_owner_row["ownership"]["split_with"]

    # Requester should have team entry pointing to same main owner.
    requester_teams = players_after["100"]["teams"]
    brazil_requester_row = next(t for t in requester_teams if t["team"] == "Brazil")
    assert brazil_requester_row["ownership"]["main_owner"] == 200


def test_split_requests_respond_forbidden_for_non_owner(client, app):
    """Only the receiving main owner can resolve a split request via web API."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    (json_dir / "split_requests.json").write_text(json.dumps({
        "req2": {
            "requester_id": 100,
            "main_owner_id": 200,
            "team": "Argentina",
            "expires_at": 4102444800,
            "requested_percentage": 20
        }
    }), encoding="utf-8")

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "300", "username": "not-owner"}

    resp = client.post('/api/split_requests/respond', json={"id": "req2", "action": "decline"})
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "forbidden"


def test_bot_watcher_handles_maintenance_announcement_commands():
    """Regression guard: runtime command watcher should process maintenance announcements."""
    bot_py = (ROOT / "WorldCupBot" / "bot.py").read_text(encoding="utf-8")
    assert 'if kind in ("maintenance_mode_enabled", "maintenance_mode_disabled"):' in bot_py
    assert 'await self._handle_maintenance_announcement(data)' in bot_py
    assert 'async def _handle_maintenance_announcement(self, data: dict):' in bot_py


def test_maintenance_announcement_channel_selection_requires_send_permission():
    """Guard against choosing a named channel where the bot cannot send messages."""
    bot_py = (ROOT / "WorldCupBot" / "bot.py").read_text(encoding="utf-8")
    assert 'if ch.name.lower() == target and ch.permissions_for(guild.me).send_messages:' in bot_py
