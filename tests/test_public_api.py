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


def test_index_uses_root_absolute_static_asset_paths(client):
    """
    Static assets are referenced with root-absolute paths so index.html can still
    load JS/CSS when the page URL includes a nested prefix.
    """
    html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'href="/style.css"' in html
    assert 'src="/stage.js"' not in html
    assert 'src="/app.js"' in html
    assert 'src="/user.js"' in html




def test_terms_uses_root_absolute_static_asset_paths():
    """
    Terms page assets should use root-absolute URLs so CSS/JS load reliably
    regardless of URL prefixes or reverse-proxy path rewriting.
    """
    html = (ROOT / "WorldCupBot" / "static" / "terms.html").read_text(encoding="utf-8")
    assert 'href="/terms.css"' in html
    assert 'src="/terms.js"' in html


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
