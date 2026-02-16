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


def test_app_bootstraps_stage_constants_without_stage_js():
    """
    app.js now defines window.WorldCupStages when the standalone stage.js asset
    is unavailable so user-facing stage UI still works.
    """
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "if (!window.WorldCupStages) {" in app_js
    assert "const STAGE_ORDER = [" in app_js
    assert "const STAGE_PROGRESS = {" in app_js
