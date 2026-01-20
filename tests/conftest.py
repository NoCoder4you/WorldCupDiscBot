import json
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "WorldCupBot"))

from routes_public import create_public_routes  # noqa: E402


@pytest.fixture
def app(tmp_path):
    base_dir = tmp_path
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "DISCORD_CLIENT_ID": "client-id",
        "DISCORD_CLIENT_SECRET": "client-secret",
        "DISCORD_REDIRECT_URI": "http://localhost/auth/discord/callback",
        "ADMIN_IDS": ["123"],
    }
    (base_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")

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
    app.config["BASE_DIR"] = str(base_dir)

    root_bp, api_bp, auth_bp = create_public_routes(ctx)
    app.register_blueprint(root_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)

    return app


@pytest.fixture
def client(app):
    return app.test_client()
