
from flask import Blueprint, jsonify, send_from_directory, current_app, abort, request
import os
import time
import platform
import json

def _safe_json_load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def create_public_routes(ctx):
    """
    Registers:
      - GET /            -> static/index.html
      - GET /favicon.ico -> static favicon if present
      - /api/* endpoints via a dedicated blueprint with url_prefix='/api'
    """
    root = Blueprint("root_public", __name__)
    api = Blueprint("public_api", __name__, url_prefix="/api")

    # ---------- Root UI ----------
    @root.route("/", methods=["GET"])
    def index():
        static_folder = current_app.static_folder or os.path.join(ctx.get("BASE_DIR",""), "static")
        index_path = os.path.join(static_folder, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_folder, "index.html")
        return jsonify({"ok": False, "error": "index.html not found"}), 404

    @root.route("/favicon.ico", methods=["GET"])
    def favicon():
        static_folder = current_app.static_folder or os.path.join(ctx.get("BASE_DIR",""), "static")
        for name in ("favicon.ico", "favicon.png"):
            path = os.path.join(static_folder, name)
            if os.path.exists(path):
                return send_from_directory(static_folder, name)
        abort(404)

    # ---------- API ----------
    @api.get("/ping")
    def api_ping():
        return jsonify({"ok": True, "ts": int(time.time())})

    @api.get("/system")
    def api_system():
        usage = ctx["get_bot_resource_usage"]()
        data = {
            "ok": True,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "bot_running": bool(ctx["is_bot_running"]()),
            "mem_mb": usage.get("mem_mb"),
            "cpu_percent": usage.get("cpu_percent"),
            "logs": ctx.get("LOG_PATHS", {}),
        }
        return jsonify(data)

    @api.get("/bets")
    def api_bets():
        base = ctx.get("BASE_DIR", "")
        bets_path = os.path.join(base, "JSON", "bets.json")
        data = _safe_json_load(bets_path, [])
        status = request.args.get("status")
        if status and isinstance(data, list):
            data = [b for b in data if str(b.get("status","")).lower() == status.lower()]
        return jsonify({"ok": True, "bets": data})

    # Return BOTH blueprints so launcher can register them
    return [root, api]
