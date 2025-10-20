from flask import Blueprint, jsonify, request, session
import os, json, time, glob

def _cmd_queue_path(base_dir):
    return os.path.join(base_dir, "runtime", "bot_commands.jsonl")

def _enqueue_command(base_dir, cmd: dict):
    os.makedirs(os.path.dirname(_cmd_queue_path(base_dir)), exist_ok=True)
    cmd["ts"] = int(time.time())
    with open(_cmd_queue_path(base_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(cmd) + "\n")

def _scan_cogs(base_dir):
    cdir = os.path.join(base_dir, "COGS")
    found = []
    if os.path.isdir(cdir):
        for py in sorted(glob.glob(os.path.join(cdir, "*.py"))):
            name = os.path.splitext(os.path.basename(py))[0]
            if name.startswith("_"):
                continue
            found.append({ "name": name, "loaded": None })
    return found

def create_admin_routes(ctx):
    bp = Blueprint("admin", __name__, url_prefix="/admin")

    ADMIN_PASSWORD = ctx.get("ADMIN_PASSWORD", "")

    # ---------- Auth ----------
    @bp.get("/auth/status")
    def auth_status():
        return jsonify({ "ok": True, "unlocked": bool(session.get("admin_unlocked")) })

    @bp.post("/auth/login")
    def auth_login():
        data = request.get_json(silent=True) or {}
        pw = (data.get("password") or "").strip()
        if not ADMIN_PASSWORD:
            return jsonify({ "ok": False, "error": "admin password not set" }), 400
        if pw != ADMIN_PASSWORD:
            return jsonify({ "ok": False, "error": "invalid password" }), 403
        session["admin_unlocked"] = True
        return jsonify({ "ok": True, "unlocked": True })

    @bp.post("/auth/logout")
    def auth_logout():
        session["admin_unlocked"] = False
        return jsonify({ "ok": True, "unlocked": False })

    def require_admin():
        if not session.get("admin_unlocked"):
            return jsonify({ "ok": False, "error": "admin required" }), 403
        return None

    # ---------- Bot control ----------
    @bp.get("/bot/status")
    def bot_status():
        return jsonify({ "ok": True, "running": bool(ctx["is_bot_running"]()) })

    @bp.post("/bot/start")
    def bot_start():
        resp = require_admin()
        if resp is not None: return resp
        ok = ctx["start_bot"]()
        return jsonify({ "ok": bool(ok) })

    @bp.post("/bot/stop")
    def bot_stop():
        resp = require_admin()
        if resp is not None: return resp
        ok = ctx["stop_bot"]()
        return jsonify({ "ok": bool(ok) })

    @bp.post("/bot/restart")
    def bot_restart():
        resp = require_admin()
        if resp is not None: return resp
        ok = ctx["restart_bot"]()
        return jsonify({ "ok": bool(ok) })

    # ---------- Cogs ----------
    @bp.get("/cogs")
    def cogs_list():
        base = ctx.get("BASE_DIR", "")
        return jsonify({ "ok": True, "cogs": _scan_cogs(base) })

    @bp.post("/cogs/<cog>/<action>")
    def cogs_action(cog, action):
        resp = require_admin()
        if resp is not None: return resp
        base = ctx.get("BASE_DIR", "")
        action = (action or "").lower().strip()
        if action not in ("load","unload","reload"):
            return jsonify({ "ok": False, "error": "invalid action" }), 400
        _enqueue_command(base, { "kind": "cog", "action": action, "cog": cog })
        return jsonify({ "ok": True, "queued": { "cog": cog, "action": action } })

    # ---------- Backups maintenance ----------
    @bp.post("/backups/prune")
    def backups_prune():
        resp = require_admin()
        if resp is not None: return resp
        base = ctx.get("BASE_DIR", "")
        bdir = os.path.join(base, "Backups")
        keep = int((request.get_json(silent=True) or {}).get("keep", 10))
        if not os.path.isdir(bdir):
            return jsonify({ "ok": True, "pruned": 0 })
        files = sorted(
            (os.path.join(bdir, f) for f in os.listdir(bdir)),
            key=lambda p: os.path.getmtime(p),
            reverse=True
        )
        removed = 0
        for fp in files[keep:]:
            try:
                os.remove(fp)
                removed += 1
            except Exception:
                pass
        return jsonify({ "ok": True, "pruned": removed })

    # ---------- Config (for front-end webhook) ----------
    @bp.get("/config")
    def admin_config():
        """Return safe config values for the front-end (no secrets except webhook)."""
        resp = require_admin()
        if resp is not None:
            return resp

        try:
            base = ctx.get("BASE_DIR", "")
            cfg_path = os.path.join(base, "config.json")
            if not os.path.isfile(cfg_path):
                return jsonify({ "error": "config.json not found" }), 404

            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Only return the webhook
            safe = {
                "DISCORD_WEBHOOK_URL": data.get("DISCORD_WEBHOOK_URL")
            }
            return jsonify(safe)
        except Exception as e:
            return jsonify({ "error": str(e) }), 500

    return bp
