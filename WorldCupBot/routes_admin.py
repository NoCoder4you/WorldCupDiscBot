# routes_admin.py
# Flask admin blueprint for the World Cup 2026 panel.
# - Auth (login/logout/status)
# - Config exposure (webhook only)
# - Cog list/status/actions
# - Bot controls + backups via command queue
# Compatible with separate bot process (preferred) or in-process (optional)

import os
import sys
import json
import time
import glob
from flask import Blueprint, jsonify, request, session, current_app

# -----------------------------
# Helpers
# -----------------------------

def _base_dir(ctx):
    return ctx.get("BASE_DIR", os.getcwd())

def _runtime_dir(ctx):
    rd = os.path.join(_base_dir(ctx), "runtime")
    os.makedirs(rd, exist_ok=True)
    return rd

def _config_path(ctx):
    return os.path.join(_base_dir(ctx), "config.json")

def _load_config(ctx):
    try:
        with open(_config_path(ctx), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _commands_path(ctx):
    return os.path.join(_runtime_dir(ctx), "bot_commands.jsonl")

def _enqueue_command(ctx, kind, payload=None):
    """Append a one-line JSON command for the bot process to consume."""
    cmd = {
        "ts": int(time.time()),
        "kind": kind,
        "data": payload or {}
    }
    line = json.dumps(cmd, separators=(",", ":"))
    with open(_commands_path(ctx), "a", encoding="utf-8") as f:
        f.write(line + "\n")

def _cogs_dir(ctx):
    # Your cogs live in the "COGS" folder
    return os.path.join(_base_dir(ctx), "COGS")

def _cogs_state_path(ctx):
    return os.path.join(_base_dir(ctx), "JSON", "cogs_status.json")

def _read_cogs_state(ctx):
    fp = _cogs_state_path(ctx)
    if not os.path.isfile(fp):
        return set()
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("loaded"), list):
            return set(data["loaded"])
    except Exception:
        pass
    return set()

def _scan_cogs(ctx, bot=None):
    results = []
    cdir = _cogs_dir(ctx)
    if not os.path.isdir(cdir):
        return results

    # Preferred: state written by the bot
    loaded_exts = _read_cogs_state(ctx)

    # Fallback: in-process bot (if you ever run bot in same process)
    if not loaded_exts and bot is not None:
        try:
            if getattr(bot, "extensions", None):
                loaded_exts = set(bot.extensions.keys())
        except Exception:
            loaded_exts = set()

    # Last-ditch fallback: sys.modules
    sysmods = set(sys.modules.keys())

    for py in sorted(glob.glob(os.path.join(cdir, "*.py"))):
        name = os.path.splitext(os.path.basename(py))[0]
        if name.startswith("_"):
            continue
        module_name = f"COGS.{name}"
        is_loaded = (
            (module_name in loaded_exts) or
            (not loaded_exts and module_name in sysmods)
        )
        results.append({"name": name, "loaded": bool(is_loaded)})

    return results

# -----------------------------
# Auth helpers
# -----------------------------

SESSION_KEY = "wc_admin"

def _password_from_config(cfg):
    for k in ("PANEL_PASSWORD", "ADMIN_PASSWORD", "ADMIN_PASS", "ADMIN"):
        if cfg.get(k):
            return str(cfg[k])
    return None

def require_admin():
    if session.get(SESSION_KEY) is True:
        return None
    return jsonify({"ok": False, "error": "Unauthorized"}), 401

# -----------------------------
# Blueprint factory
# -----------------------------

def create_admin_routes(ctx):
    """
    Factory that returns the /admin blueprint.
    Expects ctx to contain at least:
      - BASE_DIR: project root
      - (optional) bot: a discord.py bot instance if running in-process
    """
    bp = Blueprint("admin", __name__, url_prefix="/admin")

    # ---------- Auth ----------
    @bp.post("/auth/login")
    def auth_login():
        data = request.get_json(silent=True) or {}
        pw = str(data.get("password") or "")
        cfg = _load_config(ctx)
        expected = _password_from_config(cfg)
        if expected and pw and pw == expected:
            session[SESSION_KEY] = True
            return jsonify({"ok": True, "unlocked": True})
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401

    @bp.post("/auth/logout")
    def auth_logout():
        session.pop(SESSION_KEY, None)
        return jsonify({"ok": True, "unlocked": False})

    @bp.get("/auth/status")
    def auth_status():
        return jsonify({"ok": True, "unlocked": bool(session.get(SESSION_KEY))})

    # ---------- Config (webhook only) ----------
    @bp.get("/config")
    def admin_config():
        resp = require_admin()
        if resp is not None:
            return resp
        cfg = _load_config(ctx)
        return jsonify({
            "DISCORD_WEBHOOK_URL": cfg.get("DISCORD_WEBHOOK_URL")
        })

    # ---------- Bot controls ----------
    @bp.post("/bot/start")
    def bot_start():
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_command(ctx, "bot_start", {})
        return jsonify({"ok": True})

    @bp.post("/bot/stop")
    def bot_stop():
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_command(ctx, "bot_stop", {})
        return jsonify({"ok": True})

    @bp.post("/bot/restart")
    def bot_restart():
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_command(ctx, "bot_restart", {})
        return jsonify({"ok": True})

    # ---------- Backups ----------
    @bp.post("/backups/create")
    def backups_create():
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_command(ctx, "backup_create", {})
        return jsonify({"ok": True, "message": "Backup requested"})

    @bp.post("/backups/restore")
    def backups_restore():
        resp = require_admin()
        if resp is not None:
            return resp
        data = request.get_json(silent=True) or {}
        _enqueue_command(ctx, "backup_restore", {"name": data.get("name")})
        return jsonify({"ok": True, "message": "Restore requested"})

    @bp.post("/backups/prune")
    def backups_prune():
        resp = require_admin()
        if resp is not None:
            return resp
        data = request.get_json(silent=True) or {}
        keep = int(data.get("keep") or 10)
        _enqueue_command(ctx, "backup_prune", {"keep": keep})
        return jsonify({"ok": True, "message": f"Prune keeping {keep}"})

    # ---------- Cogs ----------
    @bp.get("/cogs")
    def cogs_list():
        resp = require_admin()
        if resp is not None:
            return resp
        bot = ctx.get("bot")
        try:
            items = _scan_cogs(ctx, bot)
            return jsonify({"ok": True, "cogs": items})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.get("/cogs/<cog>/status")
    def cogs_status(cog):
        resp = require_admin()
        if resp is not None:
            return resp
        bot = ctx.get("bot")
        for entry in _scan_cogs(ctx, bot):
            if entry["name"].lower() == cog.lower():
                return jsonify(entry)
        return jsonify({"name": cog, "loaded": None}), 404

    def _enqueue_cog(cog, action):
        _enqueue_command(ctx, f"cog_{action}", {"name": cog})

    @bp.post("/cogs/<cog>/load")
    def cogs_load(cog):
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_cog(cog, "load")
        return jsonify({"ok": True})

    @bp.post("/cogs/<cog>/unload")
    def cogs_unload(cog):
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_cog(cog, "unload")
        return jsonify({"ok": True})

    @bp.post("/cogs/<cog>/reload")
    def cogs_reload(cog):
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_cog(cog, "reload")
        return jsonify({"ok": True})

    # ---------- Split Requests (reads JSON/split_requests.json) ----------
    def _split_requests_path():
        return os.path.join(_base_dir(ctx), "JSON", "split_requests.json")

    def _get_usernames(bot, user_ids):
        """Try to resolve usernames from cached Discord members."""
        names = {}
        if not bot or not hasattr(bot, "get_user"):
            return names
        for uid in user_ids:
            try:
                uid_int = int(uid)
            except Exception:
                continue
            user = bot.get_user(uid_int)
            if user:
                names[str(uid_int)] = str(user)
        return names

    def _resolve_usernames(bot, ids):
        """Return {str(id): username} by peeking bot cache and guild members."""
        names = {}
        if not bot:
            return names
        for raw in ids:
            if raw is None:
                continue
            try:
                uid = int(raw)
            except Exception:
                continue

            # 1) direct user cache
            u = bot.get_user(uid)
            if u:
                names[str(uid)] = str(u) if hasattr(u, "discriminator") else u.name
                continue

            # 2) search member caches for display names
            for g in getattr(bot, "guilds", []):
                m = g.get_member(uid)
                if m:
                    names[str(uid)] = m.display_name or m.name
                    break
        return names

    @bp.get("/splits")
    def splits_get():
        """Return all pending split requests with usernames resolved."""
        resp = require_admin()
        if resp is not None:
            return resp

        path = os.path.join(_base_dir(ctx), "JSON", "split_requests.json")
        if not os.path.isfile(path):
            return jsonify({"pending": []})

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except Exception as e:
            return jsonify({"error": f"failed to read split_requests.json: {e}"}), 500

        pending = []
        if isinstance(raw, dict):
            all_ids = set()
            for key, v in raw.items():
                if not isinstance(v, dict):
                    continue
                all_ids.add(str(v.get("requester_id")))
                all_ids.add(str(v.get("main_owner_id")))

            usernames = _get_usernames(ctx.get("bot"), all_ids)

            for key, v in raw.items():
                if not isinstance(v, dict):
                    continue
                req_id = str(v.get("requester_id"))
                owner_id = str(v.get("main_owner_id"))
                pending.append({
                    "id": key,
                    "team": v.get("team"),
                    "requester_id": req_id,
                    "main_owner_id": owner_id,
                    "from_username": usernames.get(req_id, f"User {req_id}"),
                    "to_username": usernames.get(owner_id, f"User {owner_id}"),
                    "expires_at": v.get("expires_at"),
                    "status": "pending"
                })

        return jsonify({"pending": pending})


    @bp.post("/splits/refresh")
    def splits_refresh():
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_command(ctx, "splits_refresh", {})
        return jsonify({"ok": True})

    # ---------- Split Requests (History from JSON/split_requests_log.json) ----------
    def _split_requests_log_path():
        return os.path.join(_base_dir(ctx), "JSON", "split_requests_log.json")

    @bp.get("/splits/history")
    def splits_history():
        resp = require_admin()
        if resp is not None:
            return resp

        path = os.path.join(_base_dir(ctx), "JSON", "split_requests_log.json")
        if not os.path.isfile(path):
            return jsonify({"events": []})

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f) or []
        except Exception as e:
            return jsonify({"error": f"failed to read split_requests_log.json: {e}"}), 500

        # Normalize to a list of dicts
        if isinstance(raw, dict) and isinstance(raw.get("events"), list):
            events = raw["events"]
        elif isinstance(raw, list):
            events = raw
        else:
            events = [raw]

        # Collect candidate IDs for name resolution
        id_set = set()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            for key in ("from", "requester_id", "requester", "from_id"):
                if ev.get(key) is not None:
                    id_set.add(str(ev.get(key)))
            for key in ("to", "main_owner_id", "receiver", "to_id"):
                if ev.get(key) is not None:
                    id_set.add(str(ev.get(key)))

        names = _resolve_usernames(ctx.get("bot"), id_set)

        # Attach resolved names (leave IDs as fallback)
        norm = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            req_id = (
                    ev.get("from_username") or ev.get("requester_id") or
                    ev.get("requester") or ev.get("from_id") or ev.get("from")
            )
            rec_id = (
                    ev.get("to_username") or ev.get("main_owner_id") or
                    ev.get("receiver") or ev.get("to_id") or ev.get("to")
            )

            ev_out = dict(ev)  # shallow copy
            if req_id is not None:
                ev_out["from_username"] = names.get(str(req_id), str(req_id))
            if rec_id is not None:
                ev_out["to_username"] = names.get(str(rec_id), str(rec_id))
            norm.append(ev_out)

        # Optional limit
        try:
            limit = int(request.args.get("limit", "200"))
        except Exception:
            limit = 200
        norm = norm[-abs(limit):]

        return jsonify({"events": norm})

    return bp
