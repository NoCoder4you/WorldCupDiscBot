import json
from pathlib import Path


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
