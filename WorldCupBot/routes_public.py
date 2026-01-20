from flask import Blueprint, jsonify, send_from_directory, current_app, abort, request, send_file, session, redirect, url_for, make_response
import os, time, json, shutil, zipfile, datetime, glob, re, ipaddress
import logging
import psutil
import secrets
import urllib.parse
import requests

from stage_constants import STAGE_CHANNEL_MAP, normalize_stage

log = logging.getLogger("launcher")

# ======================
# Core helpers
# ======================

def _load_config(base_dir):
    cfg_path = os.path.join(base_dir, "config.json")
    try:
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

def _json_load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _json_save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def _ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p

def _backup_dir(base_dir): return _ensure_dir(os.path.join(base_dir, "BACKUPS"))
def _json_dir(base_dir): return _ensure_dir(os.path.join(base_dir, "JSON"))
def _runtime_dir(base_dir): return _ensure_dir(os.path.join(base_dir, "runtime"))
def _cmd_queue_path(base_dir):
    return os.path.join(_runtime_dir(base_dir), "bot_commands.jsonl")

def _enqueue_command(base_dir, cmd: dict):
    cmd = dict(cmd); cmd["ts"] = int(time.time())
    with open(_cmd_queue_path(base_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(cmd) + "\\n")

def _bets_path(base_dir):
    return os.path.join(_json_dir(base_dir), "bets.json")
def _ownership_path(base_dir):
    return os.path.join(_json_dir(base_dir), "ownership.json")
def _verified_path(base_dir):
    return os.path.join(_json_dir(base_dir), "verified.json")
def _guilds_path(base_dir):
    return os.path.join(_json_dir(base_dir), "guilds.json")
def _admin_settings_path(base_dir):
    return os.path.join(_json_dir(base_dir), "admin_settings.json")
def _split_requests_path(base_dir):
    return os.path.join(_json_dir(base_dir), "split_requests.json")
def _split_requests_log_path(base_dir):
    return os.path.join(_json_dir(base_dir), "split_requests_log.json")
def _login_ips_path(base_dir):
    return os.path.join(_json_dir(base_dir), "login_ips.json")
def _players_path(base_dir):
    return os.path.join(_json_dir(base_dir), "players.json")
def _teams_path(base_dir):
    return os.path.join(_json_dir(base_dir), "teams.json")
def _team_iso_path(base_dir):
    return os.path.join(_json_dir(base_dir), "team_iso.json")
def _matches_path(base_dir):
    return os.path.join(_json_dir(base_dir), "matches.json")
def _tos_path(base_dir):
    return os.path.join(_json_dir(base_dir), "terms_accept.json")
def _team_stage_path(base_dir):
    return os.path.join(_json_dir(base_dir), "team_stage.json")
def _team_stage_notifications_path(base_dir):
    return os.path.join(_json_dir(base_dir), "team_stage_notifications.json")
def _bracket_slots_path(base_dir):
    return os.path.join(_json_dir(base_dir), "bracket_slots.json")
def _fan_zone_results_path(base_dir):
    return os.path.join(_json_dir(base_dir), "fan_zone_results.json")
def _bet_results_path(base_dir):
    return os.path.join(_json_dir(base_dir), "bet_results.json")
def _swap_requests_path(base_dir):
    return os.path.join(_json_dir(base_dir), "swap_requests.json")
def _notifications_read_path(base_dir):
    return os.path.join(base_dir, "JSON", "notifications_read.json")
def _notification_settings_path(base_dir):
    return os.path.join(_json_dir(base_dir), "notification_settings.json")

NOTIFICATION_CATEGORIES = (
    "splits",
    "matches",
    "bets",
    "stages",
)

def _load_notifications_read(base_dir):
    try:
        with open(_notifications_read_path(base_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_notifications_read(base_dir, data):
    os.makedirs(os.path.dirname(_notifications_read_path(base_dir)), exist_ok=True)
    with open(_notifications_read_path(base_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _load_notification_settings(base_dir):
    return _json_read(_notification_settings_path(base_dir), {})

def _save_notification_settings(base_dir, data):
    _json_save(_notification_settings_path(base_dir), data)

def _default_notification_categories() -> dict:
    return {key: True for key in NOTIFICATION_CATEGORIES}

def _notification_record(base_dir, uid: str) -> dict:
    settings = _load_notification_settings(base_dir)
    if not isinstance(settings, dict):
        settings = {}
    raw = settings.get(str(uid))
    if isinstance(raw, str):
        raw = {"channel": raw}
    if not isinstance(raw, dict):
        raw = {}
    channel = str(raw.get("channel") or "").strip().lower()
    raw_categories = raw.get("categories")
    categories = _default_notification_categories()
    if isinstance(raw_categories, dict):
        for key in NOTIFICATION_CATEGORIES:
            if key in raw_categories:
                categories[key] = bool(raw_categories.get(key))
    return {"channel": channel, "categories": categories}

def _notification_channel_preference(base_dir, uid: str) -> str:
    return _notification_record(base_dir, uid).get("channel") or ""

def _notification_category_enabled(base_dir, uid: str, category: str) -> bool:
    rec = _notification_record(base_dir, uid)
    return bool(rec.get("categories", {}).get(category, True))

def _json_read(path, default):
    try:
        if not os.path.isfile(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _load_admin_settings(base_dir):
    return _json_read(_admin_settings_path(base_dir), {})

def _load_primary_guild_id(base_dir) -> str:
    settings = _load_admin_settings(base_dir)
    selected = str(settings.get("SELECTED_GUILD_ID") or "").strip()
    if selected:
        return selected
    cfg = _load_config(base_dir)
    for key in ("DISCORD_GUILD_ID", "GUILD_ID", "PRIMARY_GUILD_ID", "ADMIN_GUILD_ID"):
        raw = str(cfg.get(key) or "").strip()
        if raw:
            return raw
    data = _json_read(_guilds_path(base_dir), {})
    if isinstance(data, dict):
        guilds = data.get("guilds") or []
        if isinstance(guilds, list):
            for g in guilds:
                if isinstance(g, dict):
                    gid = str(g.get("id") or "").strip()
                    if gid:
                        return gid
    return ""

def _list_backups(base_dir):
    bdir = _backup_dir(base_dir)
    out = []
    for name in sorted(os.listdir(bdir)):
        fp = os.path.join(bdir, name)
        if os.path.isfile(fp):
            title, ext = os.path.splitext(name)
            if ext.lower() == ".zip":
                title = name
            out.append({
                "name": name,
                "title": title,
                "size": os.path.getsize(fp),
                "ts": int(os.path.getmtime(fp)),
                "rel": name,
            })
    return sorted(out, key=lambda x: x["ts"], reverse=True)

def _create_backup(base_dir):
    bdir = _backup_dir(base_dir)
    jdir = _json_dir(base_dir)
    ts = datetime.datetime.now().strftime("%d-%m_%H-%M")
    outname = f"{ts}.zip"
    outpath = os.path.join(bdir, outname)
    with zipfile.ZipFile(outpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if os.path.isdir(jdir):
            for root, _, files in os.walk(jdir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arc = os.path.relpath(fp, jdir)
                    z.write(fp, arcname=arc)
    return outname

def _restore_backup(base_dir, name):
    bdir = _backup_dir(base_dir)
    jdir = _json_dir(base_dir)
    src = os.path.join(bdir, name)
    if not (os.path.isfile(src) and src.endswith(".zip")):
        raise FileNotFoundError("Backup not found")
    if os.path.isdir(jdir):
        shutil.copytree(jdir, jdir + ".bak.restore", dirs_exist_ok=True)
    with zipfile.ZipFile(src, "r") as z:
        _ensure_dir(jdir); z.extractall(jdir)
    return True

def _tail_file(path, max_lines=500):
    if not os.path.isfile(path): return []
    with open(path, "rb") as f:
        try:
            f.seek(0, os.SEEK_END)
            data = []
            while len(data) < max_lines and f.tell() > 0:
                step = min(4096, f.tell())
                f.seek(-step, os.SEEK_CUR)
                chunk = f.read(step)
                f.seek(-step, os.SEEK_CUR)
                lines = chunk.splitlines()
                if data:
                    lines[-1] += data[0]
                    data = lines[:-1] + data[1:]
                else:
                    data = lines
                if f.tell() == 0:
                    break
            return [l.decode("utf-8", "ignore") for l in data[-max_lines:]]
        except Exception:
            f.seek(0)
            return f.read().decode("utf-8", "ignore").splitlines()[-max_lines:]

# ======================
# Discord OAuth helpers
# ======================

def _discord_oauth_urls():
    return {
        "authorize": "https://discord.com/api/oauth2/authorize",
        "token":     "https://discord.com/api/oauth2/token",
        "me":        "https://discord.com/api/users/@me",
        "cdn":       "https://cdn.discordapp.com"
    }

def _discord_client_info(ctx):
    base = ctx.get("BASE_DIR", "")
    cfg = _load_config(base)
    return (
        str(cfg.get("DISCORD_CLIENT_ID") or ""),
        str(cfg.get("DISCORD_CLIENT_SECRET") or ""),
        str(cfg.get("DISCORD_REDIRECT_URI") or ""),
    )

def _is_admin(base_dir, uid):
    cfg = _load_config(base_dir)
    admin_ids = cfg.get("ADMIN_IDS") or cfg.get("ADMIN_IDs") or cfg.get("admins") or []
    admin_ids = [str(x).strip() for x in admin_ids if str(x).strip()]
    return str(uid).strip() in admin_ids

def _session_key():
    return "wc_user"

_AVATAR_CACHE = {}  # { id: {"url": str, "ts": int} }

def _discord_avatar_url(user_id: str, avatar_hash: str, size: int = 64) -> str | None:
    if not user_id or not avatar_hash:
        return None
    ext = "gif" if str(avatar_hash).startswith("a_") else "png"
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size={size}"

def _discord_default_avatar_url(user_id: str) -> str:
    try:
        idx = int(int(user_id) % 6)
    except Exception:
        idx = 0
    return f"https://cdn.discordapp.com/embed/avatars/{idx}.png"

def _extract_client_ip(req) -> str:
    headers = req.headers
    for key in ("CF-Connecting-IP", "X-Real-IP"):
        value = str(headers.get(key) or "").strip()
        if value:
            return value
    xff = str(headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return str(req.remote_addr or "").strip()

def _ip_match_key(raw_ip: str) -> str:
    if not raw_ip:
        return ""
    try:
        addr = ipaddress.ip_address(raw_ip)
    except ValueError:
        return ""
    if not addr.is_global:
        return ""
    if addr.version == 4:
        return f"v4:{addr.compressed}"
    if addr.version == 6:
        return f"v6:{addr.compressed}"
    return ""

# ---------- Masquerade helper ----------
def _effective_uid():
    """Return actual logged-in user OR masqueraded user id."""
    user = session.get("wc_user")
    if not user:
        return None

    real_id = str(user.get("discord_id") or "")
    masquerade_id = session.get("wc_masquerade_id")

    # Only allow masquerade if the real user is an admin
    base = current_app.config.get("BASE_DIR", "")
    cfg = _load_config(base)
    admin_ids = {str(x) for x in (cfg.get("ADMIN_IDS") or [])}

    if masquerade_id and real_id in admin_ids:
        return str(masquerade_id)

    return real_id

# ---------- Blueprints ----------
def create_public_routes(ctx):
    root = Blueprint("root_public", __name__)
    api  = Blueprint("public_api", __name__, url_prefix="/api")
    auth = Blueprint("auth", __name__, url_prefix="/auth/discord")

    # ---------- Root ----------
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
            if os.path.exists(path): return send_from_directory(static_folder, name)
        abort(404)

    # ---------- First-class Terms page ----------
    @root.route("/terms", methods=["GET"])
    def terms_page():
        # Serve the dedicated static HTML file only (no inline HTML/JS/CSS here)
        static_folder = current_app.static_folder or os.path.join(ctx.get("BASE_DIR", ""), "static")
        terms_path = os.path.join(static_folder, "terms.html")
        if os.path.exists(terms_path):
            return send_from_directory(static_folder, "terms.html")
        return jsonify({"ok": False, "error": "terms.html not found"}), 404

    # ---------- Dashboard ----------
    @api.get("/ping")
    def api_ping():
        running = bool(ctx["is_bot_running"]())
        pid = None
        if running:
            try:
                pid = ctx.get("bot_process").pid if ctx.get("bot_process") else None
            except Exception:
                pid = None
        return jsonify({"status": "ok", "bot_running": running, "pid": pid})

    @api.get("/system")
    def api_system():
        try:
            sys_mem = psutil.virtual_memory()
            sys_cpu = psutil.cpu_percent(interval=0.1)
            disk = psutil.disk_usage('/')
        except Exception:
            sys_mem = type("x",(object,),{"total":0,"used":0,"percent":0})()
            sys_cpu = 0.0
            class D: total=0; used=0; percent=0
            disk = D()
        usage = ctx["get_bot_resource_usage"]() if "get_bot_resource_usage" in ctx else {"mem_mb": None, "cpu_percent": None}
        return jsonify({
            "bot": usage,
            "system": {
                "mem_total_mb": (getattr(sys_mem, "total", 0) or 0) / 1024 / 1024,
                "mem_used_mb": (getattr(sys_mem, "used", 0) or 0) / 1024 / 1024,
                "mem_percent": float(getattr(sys_mem, "percent", 0) or 0),
                "cpu_percent": float(sys_cpu or 0),
                "disk_total_mb": (getattr(disk, "total", 0) or 0) / 1024 / 1024,
                "disk_used_mb": (getattr(disk, "used", 0) or 0) / 1024 / 1024,
                "disk_percent": float(getattr(disk, "percent", 0) or 0),
            }
        })

    @api.get("/uptime")
    def api_uptime():
        running = bool(ctx["is_bot_running"]())
        now = time.time()
        start_ts = None; stop_ts = None
        try:
            if running:
                pid = ctx.get("bot_process").pid if ctx.get("bot_process") else None
                if pid:
                    start_ts = psutil.Process(pid).create_time()
        except Exception:
            start_ts = None
        if start_ts is None:
            start_ref = ctx.get("bot_last_start_ref", {})
            start_ts = start_ref.get("value") if isinstance(start_ref, dict) else None
        stop_ref = ctx.get("bot_last_stop_ref", {})
        stop_ts = stop_ref.get("value") if isinstance(stop_ref, dict) else None

        def _fmt(sec):
            sec = max(0, int(sec or 0))
            h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
            return f"{h:02d}:{m:02d}:{s:02d}"

        if running and start_ts:
            uptime = now - float(start_ts)
            return jsonify({"bot_running": True, "uptime_seconds": int(uptime), "uptime_hms": _fmt(uptime)})
        else:
            downtime = (now - float(stop_ts)) if stop_ts else 0
            return jsonify({"bot_running": False, "downtime_seconds": int(downtime), "downtime_hms": _fmt(downtime)})

    @api.get("/health")
    def api_health():
        running = bool(ctx["is_bot_running"]())
        crash_status = {}
        f = ctx.get("get_crash_status")
        if callable(f):
            try: crash_status = f() or {}
            except Exception: crash_status = {}
        last_start = (ctx.get("bot_last_start_ref") or {}).get("value")
        last_stop  = (ctx.get("bot_last_stop_ref") or {}).get("value")
        now = time.time()
        cooldown_until = crash_status.get("cooldown_until", 0)
        return jsonify({
            "bot_running": running,
            "crash_count": int(crash_status.get("crash_count", 0)),
            "cooldown_active": bool(crash_status.get("cooldown_active", False)),
            "seconds_until_restart": max(0, int(cooldown_until - now)) if cooldown_until else 0,
            "window_seconds": int(crash_status.get("window_seconds", 60)),
            "max_crashes": int(crash_status.get("max_crashes", 3)),
            "last_start": last_start,
            "last_stop": last_stop,
            "ts": int(now)
        })

    # ---------- Public Settings ----------
    @api.get("/settings")
    def api_public_settings():
        base_dir = ctx.get("BASE_DIR", "")
        settings = _load_admin_settings(base_dir)
        primary_guild_id = _load_primary_guild_id(base_dir)
        selected_guild_id = str(settings.get("SELECTED_GUILD_ID") or "").strip()
        stage_channel = str(settings.get("STAGE_ANNOUNCE_CHANNEL") or "").strip()
        effective_guild_id = selected_guild_id or primary_guild_id
        return jsonify({
            "ok": True,
            "stage_announce_channel": stage_channel,
            "selected_guild_id": selected_guild_id,
            "primary_guild_id": primary_guild_id,
            "effective_guild_id": effective_guild_id,
        })

    # ---------- Teams ----------
    @api.get("/teams")
    def api_teams():
        base = ctx.get("BASE_DIR", "")
        data = _json_load(_teams_path(base), [])
        if isinstance(data, dict) and "teams" in data:
            return jsonify(data["teams"])
        return jsonify(data if isinstance(data, list) else [])

    @api.get("/guilds")
    def api_guilds():
        data = _json_load(_guilds_path(ctx.get("BASE_DIR","")), {"guild_count": 0, "guilds": []})
        return jsonify(data)

    @api.get("/team_stage")
    def api_team_stage():
        base = ctx.get("BASE_DIR", "")
        data = _json_read(_team_stage_path(base), {})
        resp = make_response(jsonify(data if isinstance(data, dict) else {}))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @api.get("/bracket_slots")
    def api_bracket_slots():
        base = ctx.get("BASE_DIR", "")
        data = _json_read(_bracket_slots_path(base), {})
        return jsonify({"ok": True, "slots": data if isinstance(data, dict) else {}})

    # ---------- Bot controls ----------
    @api.post("/bot/start")
    def bot_start():
        ok = ctx["start_bot"]()
        ctx.setdefault("bot_last_stop_ref", {}).update({"value": None})
        ctx.setdefault("bot_last_start_ref", {}).update({"value": time.time()})
        return jsonify({"ok": bool(ok)})

    @api.post("/bot/stop")
    def bot_stop():
        ok = ctx["stop_bot"]()
        ctx.setdefault("bot_last_stop_ref", {}).update({"value": time.time()})
        return jsonify({"ok": bool(ok)})

    @api.post("/bot/restart")
    def bot_restart():
        ok = ctx["restart_bot"]()
        ctx.setdefault("bot_last_start_ref", {}).update({"value": time.time()})
        return jsonify({"ok": bool(ok)})

    # ---------- Logs ----------
    @api.get("/log/<kind>")
    def log_get(kind):
        paths = ctx.get("LOG_PATHS", {})
        fp = paths.get(kind)
        if not fp or not os.path.exists(fp):
            return jsonify({"ok": True, "lines": []})
        return jsonify({"ok": True, "lines": _tail_file(fp, max_lines=500)})

    @api.get("/log/<kind>/download")
    def log_download(kind):
        paths = ctx.get("LOG_PATHS", {})
        fp = paths.get(kind)
        if not fp or not os.path.exists(fp):
            return jsonify({"ok": False, "error": "not found"}), 404
        return send_file(fp, as_attachment=True, download_name=f"{kind}.log")

    @api.post("/log/<kind>/clear")
    def log_clear(kind):
        paths = ctx.get("LOG_PATHS", {})
        fp = paths.get(kind)
        if not fp: return jsonify({"ok": False, "error": "unknown log"}), 404
        try:
            open(fp, "w").close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ---------- VERIFIED ----------
    @api.get("/verified")
    def api_verified():
        base = ctx.get("BASE_DIR", "")
        blob = _json_load(_verified_path(base), {})
        raw = blob.get("verified_users") if isinstance(blob, dict) else blob
        login_map = _json_load(_login_ips_path(base), {})
        if not isinstance(login_map, dict):
            login_map = {}
        tos_map = _json_load(_tos_path(base), {})
        if not isinstance(tos_map, dict):
            tos_map = {}
        out = []
        ip_counts = {}
        user_keys = {}
        if isinstance(raw, list):
            for v in raw:
                if not isinstance(v, dict):
                    continue
                ip = str(v.get("ip") or v.get("ip_address") or "").strip()
                if ip:
                    ip_counts[ip] = ip_counts.get(ip, 0) + 1

            for v in raw:
                if not isinstance(v, dict):
                    continue
                did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "").strip()
                if not did:
                    continue
                tos_rec = tos_map.get(did) if isinstance(tos_map.get(did), dict) else {}
                ip = str(
                    v.get("ip")
                    or v.get("ip_address")
                    or tos_rec.get("ip_client")
                    or tos_rec.get("ip")
                    or ""
                ).strip()
                key = _ip_match_key(ip) if ip else ""
                keys = {key} if key else set()
                user_keys[did] = keys
                for key in keys:
                    ip_counts[key] = ip_counts.get(key, 0) + 1

            for v in raw:
                if not isinstance(v, dict):
                    continue
                did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "").strip()
                if not did:
                    continue
                login_rec = login_map.get(did) if isinstance(login_map.get(did), dict) else {}
                tos_rec = tos_map.get(did) if isinstance(tos_map.get(did), dict) else {}
                ip = str(
                    login_rec.get("ip_client")
                    or login_rec.get("ip")
                    or v.get("ip")
                    or v.get("ip_address")
                    or tos_rec.get("ip_client")
                    or tos_rec.get("ip")
                    or ""
                ).strip()
                key = _ip_match_key(ip) if ip else ""
                keys = {key} if key else set()
                user_keys[did] = keys
                for key in keys:
                    ip_counts[key] = ip_counts.get(key, 0) + 1

            for v in raw:
                if not isinstance(v, dict):
                    continue
                did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "").strip()
                if not did:
                    continue

                keys = user_keys.get(did, set())
                avatar_field = (
                    v.get("avatar_url")
                    or v.get("avatarUrl")
                    or v.get("avatar")
                    or v.get("avatar_hash")
                    or v.get("avatarHash")
                )
                avatar_url = None
                avatar_hash = None

                if isinstance(avatar_field, str) and avatar_field.startswith("http"):
                    avatar_url = avatar_field
                elif isinstance(avatar_field, str) and avatar_field:
                    # looks like a hash
                    avatar_hash = avatar_field
                    avatar_url = _discord_avatar_url(did, avatar_hash, size=64)

                # Fallback to default avatar if nothing known
                if not avatar_url:
                    avatar_url = _discord_default_avatar_url(did)

                user = {
                    "discord_id": did,
                    "username": v.get("username") or v.get("name") or "",
                    "display_name": (v.get("display_name") or v.get("username") or ""),
                    "habbo_name": v.get("habbo_name") or "",
                    "avatar_hash": avatar_hash,
                    "avatar_url": avatar_url,
                    "ip_match": any(ip_counts.get(key, 0) > 1 for key in keys),
                }
                out.append(user)
        return jsonify(out)

    @api.get("/avatars")
    def api_avatars():
        base = ctx.get("BASE_DIR", "")
        cfg = _load_config(base)
        bot_token = cfg.get("DISCORD_BOT_TOKEN") or cfg.get("BOT_TOKEN") or ""
        ids = (request.args.get("ids") or "").split(",")
        ids = [i.strip() for i in ids if i.strip().isdigit()]
        if not ids:
            return jsonify({"avatars": {}})

        out = {}
        now = int(time.time())

        # small in-memory cache 10 minutes
        def cache_get(uid):
            rec = _AVATAR_CACHE.get(uid)
            if rec and now - rec.get("ts", 0) < 600:
                return rec.get("url")
            return None

        def cache_put(uid, url):
            _AVATAR_CACHE[uid] = {"url": url, "ts": now}

        # without a token we can only return defaults
        if not bot_token:
            for uid in ids:
                url = cache_get(uid) or _discord_default_avatar_url(uid)
                cache_put(uid, url)
                out[uid] = url
            return jsonify({"avatars": out})

        # fetch each user (keep it simple; Pi-friendly; Discord rate-limit is generous for small lists)
        for uid in ids:
            cached = cache_get(uid)
            if cached:
                out[uid] = cached
                continue
            try:
                r = requests.get(
                    f"https://discord.com/api/v10/users/{uid}",
                    headers={"Authorization": f"Bot {bot_token}"},
                    timeout=4,
                )
                if r.status_code == 200:
                    info = r.json() or {}
                    ah = info.get("avatar")
                    url = _discord_avatar_url(uid, ah, 64) if ah else _discord_default_avatar_url(uid)
                else:
                    url = _discord_default_avatar_url(uid)
            except Exception:
                url = _discord_default_avatar_url(uid)
            cache_put(uid, url)
            out[uid] = url

        return jsonify({"avatars": out})

    @api.get("/player_names")
    def api_player_names():
        base = ctx.get("BASE_DIR", "")
        verified_blob = _json_load(_verified_path(base), {})
        players_blob = _json_load(_players_path(base), {})

        # Build { discord_id: display_name }
        out = {}

        # 1) verified.json (preferred)
        vlist = verified_blob.get("verified_users") if isinstance(verified_blob, dict) else verified_blob
        if isinstance(vlist, list):
            for v in vlist:
                if not isinstance(v, dict):
                    continue
                did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "").strip()
                disp = (v.get("display_name") or v.get("username") or v.get("name") or "").strip()
                if did:
                    out[did] = disp or did

        # 2) players.json fallback for any IDs not in verified.json
        if isinstance(players_blob, dict):
            for uid, pdata in players_blob.items():
                did = str(uid).strip()
                if not did or did in out:
                    continue
                if isinstance(pdata, dict):
                    disp = (pdata.get("display_name") or pdata.get("username") or pdata.get("name") or "").strip()
                else:
                    disp = did
                out[did] = disp or did

        # no-cache so UI always sees freshest names
        resp = make_response(jsonify(out))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # ---------- Bets (enriched with display_name) ----------
    @api.get("/bets")
    def api_bets():
        base = ctx.get("BASE_DIR", "")
        bets = _json_load(_bets_path(base), [])
        verified_blob = _json_load(_verified_path(base), {})
        verified = verified_blob.get("verified_users") if isinstance(verified_blob, dict) else verified_blob

        id_to_disp = {}
        if isinstance(verified, list):
            for v in verified:
                if isinstance(v, dict):
                    did = str(v.get("discord_id") or v.get("id") or "").strip()
                    dname = (v.get("display_name") or v.get("username") or "").strip()
                    if did:
                        id_to_disp[did] = dname

        def resolve(uid, uname):
            key = str(uid).strip() if uid is not None else ""
            if key and key in id_to_disp:
                return id_to_disp[key] or (uname or key)
            return uname or (key if key else "")

        out = []
        seq = bets if isinstance(bets, list) else bets.get("bets", [])
        for b in seq or []:
            if not isinstance(b, dict):
                continue
            item = dict(b)
            o1 = resolve(item.get("option1_user_id"), item.get("option1_user_name"))
            o2 = resolve(item.get("option2_user_id"), item.get("option2_user_name"))
            item["option1_user_name"] = o1
            item["option2_user_name"] = o2
            item["option1_display_name"] = o1
            item["option2_display_name"] = o2
            out.append(item)
        return jsonify(out)

    @api.get("/my_bets")
    def api_my_bets():
        base = ctx.get("BASE_DIR", "")
        uid = _effective_uid() or ""

        def _s(x):
            return str(x or "").strip()

        def _your_side_for_uid(b, uid_):
            if not uid_: return ""
            if _s(b.get("option1_user_id")) == uid_: return "option1"
            if _s(b.get("option2_user_id")) == uid_: return "option2"
            return ""

        def _winner_side(b):
            w = _s(b.get("winner"))
            if not w: return ""
            o1 = _s(b.get("option1"))
            o2 = _s(b.get("option2"))
            wl = w.lower()
            if wl in ("option1", "1", "a"): return "option1"
            if wl in ("option2", "2", "b"): return "option2"
            if wl == o1.lower(): return "option1"
            if wl == o2.lower(): return "option2"
            return ""

        def _winner_label(b):
            ws = _winner_side(b)
            if not ws: return ""
            o1 = _s(b.get("option1")) or "Option 1"
            o2 = _s(b.get("option2")) or "Option 2"
            return f"Option 1 ({o1})" if ws == "option1" else f"Option 2 ({o2})"

        def _title_for(b):
            return _s(b.get("bet_title")) or f"Bet {_s(b.get('bet_id'))}"

        if not uid:
            return jsonify({"ok": True, "bets": [], "uid": uid})

        blob = _json_load(_bets_path(base), [])
        bets = blob if isinstance(blob, list) else blob.get("bets", [])

        out = []
        for b in bets:
            if not isinstance(b, dict):
                continue
            ys = _your_side_for_uid(b, uid)
            if not ys:
                continue
            choice = _s(b.get("option1")) if ys == "option1" else _s(b.get("option2"))
            ws = _winner_side(b)
            out.append({
                "id": _s(b.get("bet_id")),
                "title": _title_for(b),
                "your_side": ys,  # "option1" | "option2"
                "your_choice": choice,  # text like "Spain Will Win"
                "winner_side": ws,  # "" | "option1" | "option2"
                "winner_label": _winner_label(b),
                "status": "Open" if not ws else "Settled",
            })

        resp = make_response(jsonify({"ok": True, "bets": out, "uid": uid}))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # ---------- Ownership from players ----------
    @api.get("/ownership_merged")
    def ownership_merged():
        base = ctx.get("BASE_DIR", "")
        try:
            teams_raw = _json_load(_teams_path(base), [])
            if isinstance(teams_raw, dict):
                teams = teams_raw.get("teams", [])
            elif isinstance(teams_raw, list):
                teams = teams_raw
            else:
                teams = []
            if not isinstance(teams, list):
                teams = []

            players = _json_load(_players_path(base), {})
            verified_blob = _json_load(_verified_path(base), {})
            id_to_name = {}

            vlist = verified_blob.get("verified_users") if isinstance(verified_blob, dict) else verified_blob
            if isinstance(vlist, list):
                for v in vlist:
                    if not isinstance(v, dict):
                        continue
                    did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "").strip()
                    dnm = (v.get("display_name") or v.get("username") or v.get("name") or "").strip()
                    if did:
                        id_to_name[did] = dnm or did

            if isinstance(players, dict):
                for uid, pdata in players.items():
                    did = str(uid).strip()
                    if not did or did in id_to_name:
                        continue
                    nm = None
                    if isinstance(pdata, dict):
                        nm = (pdata.get("display_name") or pdata.get("username") or pdata.get("name"))
                    id_to_name[did] = str(nm or did)

            country_map = {}
            if isinstance(players, dict):
                for uid, pdata in players.items():
                    if not isinstance(pdata, dict):
                        continue
                    for entry in (pdata.get("teams") or []):
                        if isinstance(entry, dict):
                            team = entry.get("team")
                            if not team: 
                                continue
                            own = entry.get("ownership") or {}
                            main_owner = own.get("main_owner")
                            split_with = own.get("split_with") or []
                        else:
                            team = str(entry)
                            own = {}
                            main_owner = None
                            split_with = []

                        rec = country_map.setdefault(team, {"main_owner": None, "split_with": [], "percentages": {}})
                        if main_owner is not None:
                            if rec["main_owner"] is None or str(main_owner) == str(uid):
                                rec["main_owner"] = str(main_owner)
                        for sid in split_with if isinstance(split_with, list) else [split_with]:
                            sid = str(sid).strip()
                            if sid and sid not in rec["split_with"]:
                                rec["split_with"].append(sid)
                        percentages = own.get("percentages")
                        if isinstance(percentages, dict) and percentages:
                            rec["percentages"] = {
                                str(owner_id): float(value)
                                for owner_id, value in percentages.items()
                                if value is not None
                            }

            team_names = set([str(t) for t in teams if t]) or set(country_map.keys())
            rows = []
            for team in sorted(team_names, key=lambda s: s.lower()):
                rec = country_map.get(team, {"main_owner": None, "split_with": []})
                main_id = rec.get("main_owner")
                split_ids = [sid for sid in rec.get("split_with", []) if sid and sid != str(main_id)]

                rows.append({
                    "country": team,
                    "main_owner": None if main_id is None else {
                        "id": str(main_id),
                        "username": id_to_name.get(str(main_id))
                    },
                    "split_with": [{"id": sid, "username": id_to_name.get(sid)} for sid in split_ids],
                    "owners_count": (1 if main_id else 0) + len(split_ids),
                    "percentages": rec.get("percentages") or {}
                })

            return jsonify({"rows": rows, "count": len(rows)})

        except Exception as e:
            import traceback
            current_app.logger.exception("ownership_merged failed")
            return jsonify({
                "ok": False,
                "error": "ownership_merged crashed",
                "detail": str(e),
                "trace": traceback.format_exc().splitlines()[-5:],
            }), 500

    @api.get("/ownership_from_players")
    def ownership_from_players():
        base = ctx.get("BASE_DIR", "")

        players = _json_load(_players_path(base), {})
        id_to_name = {}
        if isinstance(players, dict):
            for uid, pdata in players.items():
                if isinstance(pdata, dict):
                    nm = pdata.get("display_name") or pdata.get("username") or pdata.get("name") or str(uid)
                else:
                    nm = str(uid)
                id_to_name[str(uid)] = str(nm)

        country_map = {}
        if isinstance(players, dict):
            for uid, pdata in players.items():
                if not isinstance(pdata, dict):
                    continue
                for entry in (pdata.get("teams") or []):
                    if not isinstance(entry, dict):
                        continue
                    team = entry.get("team")
                    own = entry.get("ownership") or {}
                    main_owner = own.get("main_owner")
                    split_with = [str(x) for x in (own.get("split_with") or [])]
                    if not team:
                        continue
                    rec = country_map.setdefault(team, {"main_owner": None, "split_with": [], "percentages": {}})
                    if main_owner is not None:
                        if rec["main_owner"] is None or str(main_owner) == str(uid):
                            rec["main_owner"] = str(main_owner)
                    for sid in split_with:
                        if sid and sid not in rec["split_with"]:
                            rec["split_with"].append(sid)
                    percentages = own.get("percentages")
                    if isinstance(percentages, dict) and percentages:
                        rec["percentages"] = {
                            str(owner_id): float(value)
                            for owner_id, value in percentages.items()
                            if value is not None
                        }

        rows = []
        for team in sorted(country_map.keys(), key=lambda x: x.lower()):
            rec = country_map[team]
            main_id = rec.get("main_owner")
            split_ids = [sid for sid in rec.get("split_with", []) if sid and sid != str(main_id)]
            rows.append({
                "country": team,
                "main_owner": None if main_id is None else {"id": str(main_id),
                                                            "username": id_to_name.get(str(main_id))},
                "split_with": [{"id": sid, "username": id_to_name.get(sid)} for sid in split_ids],
                "owners_count": (1 if main_id else 0) + len(split_ids),
                "percentages": rec.get("percentages") or {}
            })
        return jsonify({"rows": rows, "count": len(rows)})

    @api.get("/ownerships")
    def ownerships_get():
        base = ctx.get("BASE_DIR", "")

        verified_blob = _json_load(_verified_path(base), {})
        vlist = verified_blob.get("verified_users") if isinstance(verified_blob, dict) else verified_blob
        id_to_display = {}
        if isinstance(vlist, list):
            for u in vlist:
                if isinstance(u, dict):
                    did = str(u.get("discord_id") or u.get("id") or u.get("user_id") or "").strip()
                    dnm = (u.get("display_name") or u.get("username") or u.get("name") or "").strip()
                    if did:
                        id_to_display[did] = dnm or did

        def resolve_name(x):
            if x is None:
                return ""
            if isinstance(x, dict):
                did = str(x.get("discord_id") or x.get("id") or x.get("user_id") or "").strip()
                disp = (x.get("display_name") or x.get("username") or x.get("name") or "").strip()
                if did and id_to_display.get(did):
                    return id_to_display[did]
                return disp or did
            sx = str(x).strip()
            if sx.isdigit() and id_to_display.get(sx):
                return id_to_display[sx]
            return sx

        raw = _json_load(_ownership_path(base), {})
        items = []

        if isinstance(raw, dict):
            for team, val in raw.items():
                owners = []
                if isinstance(val, list):
                    owners = val
                    splits = []
                elif isinstance(val, dict):
                    owners = val.get("owners") or val.get("owner") or []
                    splits = val.get("splits") or val.get("split_with") or []
                    if isinstance(owners, (str, dict)): owners = [owners]
                    if isinstance(splits, (str, dict)): splits = [splits]
                else:
                    owners = [val]
                    splits = []

                owners_disp = [resolve_name(o) for o in owners if o is not None]
                splits_disp = [resolve_name(s) for s in (splits or owners_disp[1:]) if s]

                owner_main = owners_disp[0] if owners_disp else ""
                split_with = ", ".join([n for n in splits_disp if n and n != owner_main])
                items.append({
                    "team": str(team),
                    "owner": owner_main,
                    "split_with": split_with
                })

        elif isinstance(raw, list):
            for row in raw:
                if not isinstance(row, dict):
                    continue
                team = row.get("team") or row.get("country") or ""
                owners = row.get("owners") or row.get("owner") or []
                splits = row.get("splits") or row.get("split_with") or []
                if isinstance(owners, (str, dict)): owners = [owners]
                if isinstance(splits, (str, dict)): splits = [splits]

                owners_disp = [resolve_name(o) for o in owners if o is not None]
                splits_disp = [resolve_name(s) for s in splits if s is not None]

                owner_main = owners_disp[0] if owners_disp else ""
                split_with = ", ".join([n for n in splits_disp if n and n != owner_main])
                items.append({
                    "team": str(team),
                    "owner": owner_main,
                    "split_with": split_with
                })

        return jsonify({"items": items, "ownerships": items})

    # ---------- Team ISO ----------
    @api.get("/team_iso")
    def api_team_iso():
        base = ctx.get("BASE_DIR", "")
        data = _json_load(_team_iso_path(base), {})
        if isinstance(data, list):
            out = {}
            for row in data:
                if not isinstance(row, dict): continue
                name = (row.get("team") or row.get("name") or "").strip()
                code = (row.get("iso") or row.get("code") or "").strip().lower()
                if name and code: out[name] = code
            return jsonify(out)
        return jsonify(data if isinstance(data, dict) else {})

    @api.get("/team_meta")
    def get_team_meta():
        import os, json
        path = os.path.join(ctx.get("BASE_DIR", ""), "JSON", "team_meta.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ---------- Minimal split endpoints exposed publicly ----------
    @api.get("/split_requests")
    def split_requests_get():
        base = ctx.get("BASE_DIR","")
        data = _json_load(_split_requests_path(base), {"pending": [], "resolved": []})
        data.setdefault("pending", []); data.setdefault("resolved", [])
        return jsonify(data)

    @api.post("/split_requests/force")
    def split_requests_force():
        base = ctx.get("BASE_DIR","")
        body = request.get_json(silent=True) or {}
        req_id = body.get("request_id"); action = (body.get("action") or "").lower()
        if action not in ("forceaccept", "forcedecline", "delete"):
            return jsonify({"ok": False, "error": "invalid action"}), 400
        _enqueue_command(base, {"kind": "split_force", "request_id": req_id, "action": action})
        log.info("Split force requested via API (request_id=%s action=%s)", req_id, action)
        return jsonify({"ok": True, "msg": "queued"})

    # ---------- Cogs + BACKUPS ----------
    @api.get("/cogs")
    def cogs_list():
        base = ctx.get("BASE_DIR","")
        cdir = os.path.join(base, "COGS")
        out = []
        if os.path.isdir(cdir):
            for py in sorted(glob.glob(os.path.join(cdir, "*.py"))):
                name = os.path.splitext(os.path.basename(py))[0]
                if not name.startswith("_"):
                    out.append({"name": name, "loaded": None, "last_error": ""})
        return jsonify({"cogs": out})

    @api.post("/cogs/action")
    def cogs_action():
        base = ctx.get("BASE_DIR","")
        body = request.get_json(silent=True) or {}
        cog = (body.get("cog") or "").strip()
        action = (body.get("action") or "").lower().strip()
        if not cog or action not in ("load","unload","reload"):
            return jsonify({"ok": False, "error": "bad payload"}), 400
        _enqueue_command(base, {"kind": "cog", "action": action, "cog": cog})
        return jsonify({"ok": True})

    @api.get("/backups")
    def backups_list():
        base = ctx.get("BASE_DIR","")
        files = _list_backups(base)
        folders = [{
            "display": "JSON snapshots",
            "count": len(files),
            "files": [{"name": f["name"], "bytes": f["size"], "mtime": f["ts"], "rel": f["rel"]} for f in files]
        }]
        return jsonify({"folders": folders, "backups": files})

    @api.get("/backups/download")
    def backups_download():
        base = ctx.get("BASE_DIR","")
        rel = request.args.get("rel","")
        if not rel: return jsonify({"ok": False, "error": "missing rel"}), 400
        fp = os.path.join(_backup_dir(base), rel)
        if not os.path.isfile(fp): return jsonify({"ok": False, "error": "not found"}), 404
        return send_file(fp, as_attachment=True, download_name=os.path.basename(fp))

    @api.post("/backups/create")
    def backups_create():
        base = ctx.get("BASE_DIR","")
        name = _create_backup(base)
        user = session.get(_session_key()) or {}
        log.info(
            "Backup created via API (name=%s discord_id=%s username=%s)",
            name,
            _effective_uid() or user.get("discord_id") or "anonymous",
            user.get("username") or "unknown",
        )
        return jsonify({"ok": True, "created": name})

    @api.post("/backups/restore")
    def backups_restore():
        base = ctx.get("BASE_DIR","")
        body = request.get_json(silent=True) or {}
        name = body.get("name","")
        try:
            _restore_backup(base, name)
        except FileNotFoundError:
            return jsonify({"ok": False, "error": "backup not found"}), 404
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        user = session.get(_session_key()) or {}
        log.info(
            "Backup restored via API (name=%s discord_id=%s username=%s)",
            name,
            _effective_uid() or user.get("discord_id") or "anonymous",
            user.get("username") or "unknown",
        )
        return jsonify({"ok": True, "restored": name})

    # =====================
    # Discord OAuth routes
    # =====================

    @auth.get("/login")
    def discord_login():
        client_id, _, redirect_uri = _discord_client_info(ctx)
        if not (client_id and redirect_uri):
            return jsonify({"ok": False, "error": "Discord OAuth not configured in config.json"}), 500

        state = secrets.token_urlsafe(20)
        session["oauth_state"] = state
        log.info("User login initiated via Discord OAuth (state=%s)", state)

        params = {
            "response_type": "code",
            "client_id": client_id,
            "scope": "identify",
            "state": state,
            "redirect_uri": redirect_uri,
            "prompt": "consent"
        }
        url = _discord_oauth_urls()["authorize"] + "?" + urllib.parse.urlencode(params)
        return redirect(url, code=302)

    @auth.get("/callback")
    def discord_callback():
        err = request.args.get("error", "")
        err_desc = request.args.get("error_description", "")
        if err:
            session.pop("oauth_state", None)
            log.info("Discord OAuth canceled/failed (error=%s desc=%s)", err, err_desc)
            return redirect(url_for("root_public.index", discord_error=err))

        code = request.args.get("code","")
        state = request.args.get("state","")
        if not code or state != session.get("oauth_state"):
            return jsonify({"ok": False, "error": "Invalid state or code"}), 400

        client_id, client_secret, redirect_uri = _discord_client_info(ctx)
        if not (client_id and client_secret and redirect_uri):
            return jsonify({"ok": False, "error": "Discord OAuth not configured"}), 500

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            tok = requests.post(_discord_oauth_urls()["token"], data=data, headers=headers, timeout=10)
            tok.raise_for_status()
            tok_json = tok.json()
        except Exception as e:
            return jsonify({"ok": False, "error": f"token_exchange_failed: {e}"}), 500

        access_token = tok_json.get("access_token")
        if not access_token:
            return jsonify({"ok": False, "error": "no_access_token"}), 500

        try:
            me = requests.get(
                _discord_oauth_urls()["me"],
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            me.raise_for_status()
            info = me.json() or {}
        except Exception as e:
            return jsonify({"ok": False, "error": f"userinfo_failed: {e}"}), 500

        avatar = None
        if info.get("id") and info.get("avatar"):
            avatar = f'{_discord_oauth_urls()["cdn"]}/avatars/{info["id"]}/{info["avatar"]}.png?size=128'

        session[_session_key()] = {
            "discord_id": str(info.get("id") or ""),
            "username": f'{info.get("username","")}#{info.get("discriminator","")}' if info.get("discriminator") else info.get("username",""),
            "global_name": info.get("global_name") or info.get("username"),
            "avatar": avatar,
            "ts": int(time.time())
        }
        ip = _extract_client_ip(request)
        if session[_session_key()].get("discord_id"):
            ip_path = _login_ips_path(ctx.get("BASE_DIR", ""))
            ip_data = _json_load(ip_path, {})
            if not isinstance(ip_data, dict):
                ip_data = {}
            ip_data[session[_session_key()]["discord_id"]] = {
                "ip_client": ip,
                "ts": int(time.time()),
            }
            _json_save(ip_path, ip_data)
        log.info(
            "User login via Discord OAuth (discord_id=%s username=%s)",
            session[_session_key()].get("discord_id"),
            session[_session_key()].get("username"),
        )
        return redirect(url_for("root_public.index"))

    @auth.post("/logout")
    def discord_logout():
        user = session.get(_session_key()) or {}
        log.info(
            "User logout via Discord OAuth (discord_id=%s username=%s)",
            user.get("discord_id"),
            user.get("username"),
        )
        session.pop(_session_key(), None)
        return jsonify({"ok": True})

    # ==========================
    # User-facing APIs (session)
    # ==========================

    @api.get("/me")
    def me_get():
        base = ctx.get("BASE_DIR", "")
        cfg = _load_config(base)
        admin_ids = {str(x) for x in (cfg.get("ADMIN_IDS") or [])}

        user = session.get(_session_key())
        if not user:
            return jsonify({"ok": True, "user": None, "is_admin": False, "masquerading_as": None})

        real_uid = str(user.get("discord_id") or "")
        effective_uid = _effective_uid()

        return jsonify({
            "ok": True,
            "user": user,
            "is_admin": real_uid in admin_ids,
            "masquerading_as": None if effective_uid == real_uid else effective_uid
        })

    @api.get("/me/notification-settings")
    def me_notification_settings_get():
        base = ctx.get("BASE_DIR", "")
        user = session.get(_session_key())
        if not user or not user.get("discord_id"):
            return jsonify({
                "ok": True,
                "connected": False,
                "preference": "",
                "categories": _default_notification_categories(),
            })

        uid = _effective_uid() or str(user.get("discord_id") or "")
        rec = _notification_record(base, uid)
        return jsonify({
            "ok": True,
            "connected": True,
            "preference": rec.get("channel") or "",
            "categories": rec.get("categories") or _default_notification_categories(),
        })

    @api.post("/me/notification-settings")
    def me_notification_settings_set():
        base = ctx.get("BASE_DIR", "")
        user = session.get(_session_key())
        if not user or not user.get("discord_id"):
            return jsonify({
                "ok": False,
                "error": "not_authenticated"
            }), 401

        uid = _effective_uid() or str(user.get("discord_id") or "")
        body = request.get_json(silent=True) or {}
        pref = str(body.get("preference") or "").strip().lower()
        categories = body.get("categories")
        if pref not in ("", "bell", "dms", "none"):
            return jsonify({"ok": False, "error": "invalid_preference"}), 400

        settings = _load_notification_settings(base)
        if not isinstance(settings, dict):
            settings = {}
        record = {}
        if pref:
            record["channel"] = pref
        if isinstance(categories, dict):
            record["categories"] = {
                key: bool(categories.get(key)) for key in NOTIFICATION_CATEGORIES
            }
        if record:
            settings[str(uid)] = record
        else:
            settings.pop(str(uid), None)
        _save_notification_settings(base, settings)
        return jsonify({
            "ok": True,
            "preference": pref,
            "categories": record.get("categories") or _default_notification_categories(),
        })

    def _terms_accept_path(base_dir):
        return os.path.join(base_dir, "JSON", "terms_accept.json")

    @api.get("/me/notifications")
    def me_notifications():
        base = ctx.get("BASE_DIR", "")
        user = session.get(_session_key())

        if not user or not user.get("discord_id"):
            resp = make_response(jsonify({
                "ok": True,
                "connected": False,
                "items": [],
                "unread": 0
            }))
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

        # Respect masquerade (admins viewing as another user)
        uid = _effective_uid() or str(user.get("discord_id") or "")
        uid = str(uid).strip()

        now = int(time.time())
        items = []

        def coerce_ts(value, fallback):
            if value is None:
                return fallback
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except Exception:
                    pass
                try:
                    return int(datetime.datetime.fromisoformat(value).timestamp())
                except Exception:
                    return fallback
            return fallback

        # Read-state store: { "<uid>": { "read": ["id1","id2",...], "updated_at": 123 } }
        read_store = _load_notifications_read(base)
        read_ids = set()
        if isinstance(read_store, dict):
            rec = read_store.get(uid) or {}
            if isinstance(rec, dict) and isinstance(rec.get("read"), list):
                read_ids = {str(x) for x in rec["read"] if str(x)}

        # ----------------------------
        # Terms updated
        # ----------------------------
        cfg = _load_config(base)
        latest = str(cfg.get("TERMS_VERSION") or "").strip()
        if latest:
            accepted = _json_load(_terms_accept_path(base), {})
            rec = accepted.get(uid) if isinstance(accepted, dict) else None
            accepted_ver = str(rec.get("version") or "") if isinstance(rec, dict) else ""
            if accepted_ver != latest:
                items.append({
                    "id": f"terms:{latest}",
                    "type": "terms",
                    "severity": "warn",
                    "title": "Terms updated",
                    "body": "You need to re-accept the latest Terms & Conditions.",
                    "action": {"kind": "page", "page": "terms"},
                    "ts": now
                })

        preference = _notification_channel_preference(base, uid)
        if preference in ("dms", "none"):
            for it in items:
                it["read"] = str(it.get("id") or "") in read_ids
            items.sort(key=lambda x: int(x.get("ts") or 0), reverse=True)
            unread = sum(1 for it in items if not it.get("read"))
            resp = make_response(jsonify({
                "ok": True,
                "connected": True,
                "items": items,
                "unread": unread
            }))
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

        # ----------------------------
        # Split requests requiring action (main owner only)
        # Supports BOTH schemas:
        #  1) { "pending": [ ... ], "resolved": [ ... ] }
        #  2) { "<req_id>": { "requester_id": "...", "main_owner_id": 123, "team": "...", "expires_at": ... }, ... }
        # ----------------------------
        splits_blob = _json_load(_split_requests_path(base), {})
        pending_rows = []

        if isinstance(splits_blob, dict):
            if isinstance(splits_blob.get("pending"), list):
                pending_rows = splits_blob.get("pending") or []
            else:
                # dict-of-requests schema
                for req_id, r in splits_blob.items():
                    if not isinstance(r, dict):
                        continue
                    rr = dict(r)
                    rr.setdefault("id", req_id)
                    pending_rows.append(rr)

        if isinstance(pending_rows, list) and _notification_category_enabled(base, uid, "splits"):
            for r in pending_rows:
                if not isinstance(r, dict):
                    continue

                # main owner can be stored as:
                # - r["ownership"]["main_owner"] (older schema)
                # - r["main_owner_id"] (your current schema)
                owner = (r.get("ownership") or {})
                main_owner = str(owner.get("main_owner") or r.get("main_owner_id") or "").strip()
                if main_owner != uid:
                    continue

                # ignore expired
                try:
                    exp = float(r.get("expires_at") or 0)
                except Exception:
                    exp = 0
                if exp and exp <= time.time():
                    continue

                team = str(r.get("team") or "Team")
                rid = str(r.get("id") or r.get("request_id") or r.get("requester_id") or f"{uid}:{team}").strip()

                client_id, _, _ = _discord_client_info(ctx)
                action = {"kind": "page", "page": "splits"}
                if client_id:
                    action = {
                        "kind": "dm",
                        "app_url": f"discord://-/channels/@me/{client_id}",
                    }

                items.append({
                    "id": f"split:{rid}",
                    "type": "split",
                    "severity": "info",
                    "title": "Split request",
                    "body": f"Split request pending for {team}.",
                    "action": action,
                    "ts": int(r.get("created_at") or now)
                })

        # ----------------------------
        # Split results (accept/decline) for requester
        # ----------------------------
        split_log = _json_load(_split_requests_log_path(base), [])
        split_events = split_log.get("events") if isinstance(split_log, dict) else split_log
        if isinstance(split_events, list) and _notification_category_enabled(base, uid, "splits"):
            for ev in split_events:
                if not isinstance(ev, dict):
                    continue
                req_id = str(ev.get("requester_id") or ev.get("from_id") or ev.get("from") or "").strip()
                if req_id != uid:
                    continue

                action = str(ev.get("action") or ev.get("status") or "").lower().strip()
                if action in ("approved",):
                    action = "accepted"
                if action not in ("accepted", "declined", "denied", "rejected"):
                    continue

                team = str(ev.get("team") or "Team")
                rid = str(ev.get("id") or ev.get("request_id") or f"{req_id}:{team}").strip()
                ts = coerce_ts(ev.get("timestamp") or ev.get("ts"), now)
                result = "accepted" if action == "accepted" else "declined"
                severity = "ok" if result == "accepted" else "warn"

                items.append({
                    "id": f"split-result:{rid}:{result}",
                    "type": "split-result",
                    "severity": severity,
                    "title": "Split request update",
                    "body": f"Your split request for {team} was {result}.",
                    "action": {"kind": "page", "page": "splits"},
                    "ts": ts
                })

        # ----------------------------
        # Fan Zone results
        # JSON/ fan_zone_results.json:
        # { "events":[ { "id":".", "discord_id":".", "result":"win|lose", "title":".", "body":".", "ts":123 } ] }
        # ----------------------------
        fz = _json_load(_fan_zone_results_path(base), {})
        events = fz.get("events") if isinstance(fz, dict) else []
        if isinstance(events, list) and _notification_category_enabled(base, uid, "matches"):
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                if str(ev.get("discord_id") or "") != uid:
                    continue

                rid = str(ev.get("id") or ev.get("ts") or now)
                res = str(ev.get("result") or "info").lower()
                sev = "ok" if res == "win" else ("warn" if res == "lose" else "info")

                items.append({
                    "id": f"fz:{rid}",
                    "type": "fanzone",
                    "severity": sev,
                    "title": ev.get("title") or "Match Votes result",
                    "body": ev.get("body") or (
                        "You won a Match Votes pick." if res == "win"
                        else "You lost a Match Votes pick."
                    ),
                    "action": {"kind": "page", "page": "fanzone"},
                    "ts": int(ev.get("ts") or now)
                })

        # ----------------------------
        # Team stage progress
        # JSON/ team_stage_notifications.json:
        # { "events":[ { "id":".", "discord_id":".", "team":".", "stage":".", "title":".", "body":".", "ts":123 } ] }
        # ----------------------------
        tsn = _json_load(_team_stage_notifications_path(base), {})
        stage_events = tsn.get("events") if isinstance(tsn, dict) else []
        if isinstance(stage_events, list) and _notification_category_enabled(base, uid, "stages"):
            for ev in stage_events:
                if not isinstance(ev, dict):
                    continue
                if str(ev.get("discord_id") or "") != uid:
                    continue

                rid = str(ev.get("id") or ev.get("ts") or now)
                team = ev.get("team") or "Team"
                stage = ev.get("stage") or "a new stage"
                items.append({
                    "id": f"stage:{rid}",
                    "type": "stage",
                    "severity": "info",
                    "title": ev.get("title") or "Stage update",
                    "body": ev.get("body") or f"{team} advanced to {stage}.",
                    "action": {"kind": "page", "page": "user"},
                    "ts": int(ev.get("ts") or now)
                })

        # ----------------------------
        # Bet results
        # JSON/ bet_results.json:
        # { "events":[ { "id":".", "discord_id":".", "result":"win|lose", "title":".", "body":".", "ts":123 } ] }
        # ----------------------------
        br = _json_load(_bet_results_path(base), {})
        bet_events = br.get("events") if isinstance(br, dict) else []
        if isinstance(bet_events, list) and _notification_category_enabled(base, uid, "bets"):
            for ev in bet_events:
                if not isinstance(ev, dict):
                    continue
                if str(ev.get("discord_id") or "") != uid:
                    continue

                rid = str(ev.get("id") or ev.get("ts") or now)
                res = str(ev.get("result") or "info").lower()
                sev = "ok" if res == "win" else ("warn" if res == "lose" else "info")
                bet_title = ev.get("bet_title") or "Bet"
                wager = ev.get("wager") or "-"
                outcome = "Status: 🏆 Won 🏆" if res == "win" else ("Status: Lost" if res == "lose" else "Result")
                item_id = rid if rid.startswith("bet:") else f"bet:{rid}"

                items.append({
                    "id": item_id,
                    "type": "bet",
                    "severity": sev,
                    "title": ev.get("title") or "Bet result",
                    "body": ev.get("body") or f"Bet: {bet_title}\nWager: {wager}\n{outcome}",
                    "action": {"kind": "page", "page": "bets"},
                    "ts": int(ev.get("ts") or now)
                })

        # Overlay read state + counts
        for it in items:
            it["read"] = str(it.get("id") or "") in read_ids

        items.sort(key=lambda x: int(x.get("ts") or 0), reverse=True)
        unread = sum(1 for it in items if not it.get("read"))

        resp = make_response(jsonify({
            "ok": True,
            "connected": True,
            "items": items,
            "unread": unread
        }))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp


    @api.post("/me/notifications/read")
    def me_notifications_read():
        base = ctx.get("BASE_DIR", "")
        user = session.get(_session_key())
        if not user or not user.get("discord_id"):
            return jsonify({"ok": False}), 401

        uid = _effective_uid() or str(user.get("discord_id") or "")
        uid = str(uid).strip()

        body = request.get_json(silent=True) or {}
        nid = str(body.get("id") or "").strip()
        if not nid:
            return jsonify({"ok": False, "error": "missing_id"}), 400

        store = _load_notifications_read(base)
        rec = store.setdefault(uid, {"read": []})

        if nid not in rec["read"]:
            rec["read"].append(nid)

        rec["updated_at"] = int(time.time())
        store[uid] = rec
        _save_notifications_read(base, store)

        return jsonify({"ok": True})

    @api.get("/me/is_admin")
    def api_me_is_admin():
        base = ctx.get("BASE_DIR", "")
        cfg = _load_config(base)
        admin_ids = {str(x) for x in (cfg.get("ADMIN_IDS") or [])}

        uid = (request.args.get("uid") or "").strip()
        if not uid:
            uid = ""

        is_admin = uid in admin_ids if uid else False

        resp = make_response(jsonify({"ok": True, "uid": uid, "is_admin": is_admin}))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # ------- T&Cs status + accept endpoints -------
    def _in_players(base, uid: str) -> bool:
        players = _json_load(_players_path(base), {})
        if not isinstance(players, dict):
            return False
        return str(uid) in players

    def _ensure_player(base, uid: str, display_name: str):
        players_path = _players_path(base)
        players = _json_load(players_path, {})
        if not isinstance(players, dict):
            players = {}
        rec = players.get(uid)
        if not isinstance(rec, dict):
            players[uid] = {"display_name": display_name or uid, "teams": []}
        else:
            rec.setdefault("display_name", display_name or uid)
            rec.setdefault("teams", [])
        _json_save(players_path, players)

    @api.get("/me/tos")
    def me_tos_status():
        base = ctx.get("BASE_DIR","")
        cfg = _load_config(base)
        version = str(cfg.get("TERMS_VERSION") or "2026.1")
        # If no external URL is set, we default to our first-class /terms page
        tos_url = cfg.get("TERMS_URL") or "/terms"
        user = session.get(_session_key())
        if not user or not user.get("discord_id"):
            return jsonify({"connected": False, "in_players": False, "accepted": False, "version": version, "url": tos_url})

        uid = str(user["discord_id"])
        accepted_map = _json_load(_tos_path(base), {})
        accepted = False
        if isinstance(accepted_map, dict):
            rec = accepted_map.get(uid) or {}
            accepted = (str(rec.get("version") or "") == version)

        return jsonify({
            "connected": True,
            "in_players": _in_players(base, uid),
            "accepted": bool(accepted),
            "version": version,
            "url": tos_url
        })

    @api.post("/me/tos/accept")
    def me_tos_accept():
        base = ctx.get("BASE_DIR","")
        cfg = _load_config(base)
        version = str(cfg.get("TERMS_VERSION") or "2026.1")
        user = session.get(_session_key())
        if not user or not user.get("discord_id"):
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        uid = str(user["discord_id"])
        disp = user.get("global_name") or user.get("username") or uid

        # --- capture client IP from request ---
        ip = _extract_client_ip(request)

        # --- store acceptance in tos.json (unchanged, plus ip) ---
        path = _tos_path(base)
        data = _json_load(path, {})
        if not isinstance(data, dict):
            data = {}
        data[uid] = {
            "version": version,
            "ts": int(time.time()),
            "display_name": disp,
            "ip": ip,
            "ip_client": ip,
        }
        _json_save(path, data)

        # --- also write IP into verified.json if this user is in there ---
        vpath = _verified_path(base)
        vblob = _json_load(vpath, {})
        vraw = vblob.get("verified_users") if isinstance(vblob, dict) else vblob
        changed = False

        if isinstance(vraw, list):
            for v in vraw:
                if not isinstance(v, dict):
                    continue
                did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "").strip()
                if did != uid:
                    continue
                if ip:
                    v["ip"] = ip
                # you can also store tos info here if you want
                v.setdefault("meta", {})
                if isinstance(v["meta"], dict):
                    v["meta"]["tos_version"] = version
                    v["meta"]["tos_accepted_ts"] = int(time.time())
                changed = True
                break

        if changed:
            if isinstance(vblob, dict):
                vblob["verified_users"] = vraw
                _json_save(vpath, vblob)
            else:
                _json_save(vpath, vraw)

        # ensure a players.json entry exists so the user area can work
        if not _in_players(base, uid):
            _ensure_player(base, uid, disp)

        return jsonify({"ok": True, "version": version, "ip": ip})

    @api.get("/me/ownership")
    def me_ownership():
        base = ctx.get("BASE_DIR", "")
        user = session.get(_session_key())
        if not user or not user.get("discord_id"):
            return jsonify({"ok": True, "owned": [], "split": []})

        players = _json_load(_players_path(base), {})
        teams_iso = _json_load(_team_iso_path(base), {})
        uid = _effective_uid()
        if not uid:
            return jsonify({"ok": True, "owned": [], "split": []})

        owned_set, split_set = set(), set()

        if isinstance(players, dict):
            for _, pdata in players.items():
                if not isinstance(pdata, dict):
                    continue
                for entry in (pdata.get("teams") or []):
                    if not isinstance(entry, dict):
                        continue
                    team = entry.get("team")
                    if not team:
                        continue
                    own = entry.get("ownership") or {}
                    main_owner = str(own.get("main_owner")) if own.get("main_owner") is not None else None
                    splits = [str(x) for x in (own.get("split_with") or [])]

                    if main_owner == uid:
                        owned_set.add(team)
                    elif uid in splits:
                        split_set.add(team)

        def flag(team):
            code = None
            if isinstance(teams_iso, dict):
                code = teams_iso.get(team)
            return f"https://flagcdn.com/w80/{(code or '').lower()}.png" if code else None

        owned = [{"team": t, "flag": flag(t)} for t in sorted(owned_set)]
        split = [{"team": t, "flag": flag(t)} for t in sorted(split_set)]
        return jsonify({"ok": True, "owned": owned, "split": split})

    @api.get("/me/matches")
    def me_matches():
        base = ctx.get("BASE_DIR","")
        user = session.get(_session_key())
        if not user or not user.get("discord_id"):
            return jsonify({"ok": True, "matches": []})

        uid = _effective_uid()
        if not uid:
            return jsonify({"ok": True, "matches": []})

        players = _json_load(_players_path(base), {})
        owned_set = set()
        pdata = players.get(uid) if isinstance(players, dict) else None
        if isinstance(pdata, dict):
            for entry in (pdata.get("teams") or []):
                if not isinstance(entry, dict): continue
                team = entry.get("team"); own = entry.get("ownership") or {}
                if not team: continue
                if str(own.get("main_owner")) == uid or uid in [str(x) for x in (own.get("split_with") or [])]:
                    owned_set.add(team)

        all_matches = _json_load(_matches_path(base), [])
        out = []
        for m in all_matches if isinstance(all_matches, list) else []:
            try:
                when = m.get("utc") or m.get("time") or ""
                dt = datetime.datetime.fromisoformat(when.replace("Z","+00:00"))
                ts = dt.timestamp()
            except Exception:
                ts = 0
            if not ts: 
                continue
            if owned_set.intersection(set([m.get("home"), m.get("away")])):
                out.append(m)

        out.sort(key=lambda x: x.get("utc") or x.get("time") or "")
        return jsonify({"ok": True, "matches": out})

    # ======================
    # Fan Zone (fixtures + anonymous voting)
    # ======================

    def _fz_votes_path(base_dir):
        return os.path.join(_runtime_dir(base_dir), "fan_votes.json")

    def _fz_winners_path(base_dir):
        return os.path.join(_runtime_dir(base_dir), "fan_winners.json")

    def _get_fan_id():
        fid = request.cookies.get("wc_fan_id")
        if fid and isinstance(fid, str) and len(fid) >= 12:
            return fid
        return None

    def _ensure_fan_id(resp):
        fid = _get_fan_id()
        if fid:
            return fid
        fid = secrets.token_urlsafe(16)
        try:
            resp.set_cookie("wc_fan_id", fid, max_age=60*60*24*365, samesite="Lax")
        except Exception:
            pass
        return fid

    def _load_team_iso_map(base_dir):
        m = _json_load(_team_iso_path(base_dir), {})
        out = {}
        if isinstance(m, dict):
            for k, v in m.items():
                if not k or not v:
                    continue
                out[str(k).strip().lower()] = str(v).strip().lower()
        return out

    def _group_from_team_meta(base_dir, home: str, away: str) -> str:
        meta = _json_load(os.path.join(_json_dir(base_dir), "team_meta.json"), {})
        groups = meta.get("groups") if isinstance(meta, dict) else None
        if not isinstance(groups, dict):
            return ""

        lookup = {}
        for group, teams in groups.items():
            if not group or not isinstance(teams, list):
                continue
            for team in teams:
                if isinstance(team, str) and team.strip():
                    lookup[team.strip().lower()] = str(group).strip().upper()

        home_key = (home or "").strip().lower()
        away_key = (away or "").strip().lower()
        home_group = lookup.get(home_key, "")
        away_group = lookup.get(away_key, "")
        if home_group and away_group and home_group == away_group:
            return home_group
        return home_group or away_group or ""

    def _extract_group_from_stage(stage: str) -> str:
        if not stage:
            return ""
        match = re.search(r"group\\s*([a-l])", stage, re.IGNORECASE)
        return match.group(1).upper() if match else ""

    def _resolve_fanzone_channel(base_dir, fixture: dict, home: str, away: str) -> str:
        stage_raw = str(
            fixture.get("stage")
            or fixture.get("round")
            or fixture.get("phase")
            or fixture.get("tournament_stage")
            or ""
        ).strip()
        stage_norm = normalize_stage(stage_raw) or stage_raw
        if stage_norm and stage_norm not in ("Group Stage", "Groups"):
            channel = STAGE_CHANNEL_MAP.get(stage_norm)
            if channel:
                return channel

        group = str(fixture.get("group") or "").strip().upper()
        if not group:
            group = _extract_group_from_stage(stage_raw)
        if not group:
            group = _group_from_team_meta(base_dir, home, away)
        if group:
            return f"group-{group.lower()}"
        return ""

    @api.get("/fixtures")
    def api_fixtures():
        base = ctx.get("BASE_DIR", "")
        matches = _json_load(_matches_path(base), [])
        iso_map = _load_team_iso_map(base)

        fixtures = []
        if isinstance(matches, list):
            for m in matches:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or "").strip()
                home = str(m.get("home") or "").strip()
                away = str(m.get("away") or "").strip()
                utc = str(m.get("utc") or m.get("time") or "").strip()
                stage_raw = str(
                    m.get("stage")
                    or m.get("round")
                    or m.get("phase")
                    or m.get("tournament_stage")
                    or ""
                ).strip()
                stage = normalize_stage(stage_raw) or stage_raw
                group = str(m.get("group") or "").strip()
                if not (mid and home and away):
                    continue
                home_score = m.get("home_score")
                away_score = m.get("away_score")
                if home_score is None:
                    home_score = m.get("score_home")
                if away_score is None:
                    away_score = m.get("score_away")
                if home_score is None or away_score is None:
                    score_raw = m.get("score")
                    if isinstance(score_raw, str) and "-" in score_raw:
                        parts = score_raw.split("-", 1)
                        if len(parts) == 2:
                            home_score = home_score if home_score is not None else parts[0].strip()
                            away_score = away_score if away_score is not None else parts[1].strip()
                def _score_val(raw):
                    try:
                        return int(str(raw).strip())
                    except Exception:
                        return None
                home_score = _score_val(home_score)
                away_score = _score_val(away_score)
                fixtures.append({
                    "id": mid,
                    "home": home,
                    "away": away,
                    "utc": utc,
                    "stadium": str(m.get("stadium") or ""),
                    "stage": stage,
                    "group": group,
                    "bracket_slot": m.get("bracket_slot") or m.get("slot") or m.get("bracket"),
                    "status": str(m.get("status") or m.get("state") or ""),
                    "home_iso": iso_map.get(home.lower(), ""),
                    "away_iso": iso_map.get(away.lower(), ""),
                })
                if home_score is not None and away_score is not None:
                    fixtures[-1]["home_score"] = home_score
                    fixtures[-1]["away_score"] = away_score

        return jsonify({"ok": True, "fixtures": fixtures})


    @api.post("/fanzone/vote")
    def api_fanzone_vote():
        base = ctx.get("BASE_DIR", "")
        body = request.get_json(silent=True) or {}
        fixture_id = str(body.get("fixture_id") or "").strip()
        choice = str(body.get("choice") or "").strip().lower()

        if not fixture_id or choice not in ("home", "away", "draw"):
            return jsonify({"ok": False, "error": "invalid_request"}), 400

        winners_blob = _json_load(_fz_winners_path(base), {})
        if isinstance(winners_blob, dict) and fixture_id in winners_blob:
            return jsonify({"ok": False, "error": "voting_closed"}), 409

        votes_path = _fz_votes_path(base)
        votes_blob = _json_load(votes_path, {"fixtures": {}})
        if not isinstance(votes_blob, dict):
            votes_blob = {"fixtures": {}}

        fixtures = votes_blob.setdefault("fixtures", {})
        fx = fixtures.setdefault(fixture_id, {"home": 0, "away": 0, "draw": 0, "voters": {}})
        if not isinstance(fx, dict):
            fx = {"home": 0, "away": 0, "draw": 0, "voters": {}}
            fixtures[fixture_id] = fx

        voters = fx.setdefault("voters", {})
        if not isinstance(voters, dict):
            voters = {}
            fx["voters"] = voters

        resp = make_response(jsonify({"ok": True}))
        fan_id = _ensure_fan_id(resp)

        # If the voter is logged in, also record a per-discord vote so we can notify them later.
        uid = None
        try:
            u = session.get(_session_key()) or {}
            uid = _effective_uid() or str(u.get("discord_id") or "").strip()
        except Exception:
            uid = None
        if uid:
            dv = fx.setdefault("discord_voters", {})
            if not isinstance(dv, dict):
                dv = {}
                fx["discord_voters"] = dv
            dv.setdefault(uid, choice)

        # One vote per fixture per anonymous fan id (cookie-based)
        if fan_id in voters:
            # If they already voted anonymously, we still persist any discord linkage we just added
            _json_save(votes_path, votes_blob)
            return resp

        voters[fan_id] = choice
        if choice == "home":
            fx["home"] = int(fx.get("home") or 0) + 1
        elif choice == "away":
            fx["away"] = int(fx.get("away") or 0) + 1
        else:
            fx["draw"] = int(fx.get("draw") or 0) + 1

        _json_save(votes_path, votes_blob)
        log.info(
            "Match vote recorded (fixture_id=%s choice=%s fan_id=%s discord_id=%s)",
            fixture_id,
            choice,
            fan_id,
            uid or "anonymous",
        )
        return resp

    @api.post("/fanzone/declare")
    def fanzone_declare():
        base = ctx.get("BASE_DIR", "")
        body = request.get_json(silent=True) or {}

        fixture_id = str(body.get("fixture_id") or body.get("match_id") or "").strip()
        winner_side = str(body.get("winner") or body.get("winner_side") or "").strip().lower()  # home | away | draw
        winner_team = str(body.get("winner_team") or "").strip()

        # Must be logged in as Discord user
        user = session.get(_session_key()) or {}
        uid = _effective_uid() or str(user.get("discord_id") or "").strip()
        if not uid:
            return jsonify({"ok": False, "error": "not_logged_in"}), 401

        if not _is_admin(base, uid):
            return jsonify({"ok": False, "error": "admin_required"}), 403

        if not fixture_id or winner_side not in ("home", "away", "draw"):
            return jsonify({"ok": False, "error": "invalid_request"}), 400
        log.info(
            "Fan zone declare requested via public API (discord_id=%s fixture_id=%s winner_side=%s winner_team=%s)",
            uid,
            fixture_id,
            winner_side,
            winner_team,
        )

        # ----------------------------
        # Resolve fixture teams from matches.json (robust schema support)
        # ----------------------------
        def _resolve_fixture_teams(fid: str):
            matches = _json_load(_matches_path(base), [])
            home = ""
            away = ""
            fixture = {}

            def pick(d, *keys):
                for k in keys:
                    v = d.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                return ""

            if isinstance(matches, list):
                for m in matches:
                    if not isinstance(m, dict):
                        continue
                    mid = str(m.get("fixture_id") or m.get("id") or m.get("match_id") or "").strip()
                    if mid != fid:
                        continue

                    # Common schemas:
                    # home/away strings
                    home = pick(m, "home", "home_team", "team_home", "homeName", "home_name")
                    away = pick(m, "away", "away_team", "team_away", "awayName", "away_name")

                    # nested team objects
                    if not home and isinstance(m.get("home_team"), dict):
                        home = pick(m["home_team"], "name", "team", "title")
                    if not away and isinstance(m.get("away_team"), dict):
                        away = pick(m["away_team"], "name", "team", "title")

                    # nested "teams": {"home": {"name":..}, "away": {"name":..}}
                    teams = m.get("teams")
                    if isinstance(teams, dict):
                        h = teams.get("home")
                        a = teams.get("away")
                        if not home and isinstance(h, dict):
                            home = pick(h, "name", "team", "title")
                        if not away and isinstance(a, dict):
                            away = pick(a, "name", "team", "title")

                    fixture = m
                    break

            return home, away, fixture

        home, away, fixture = _resolve_fixture_teams(fixture_id)
        resolved_winner_team = winner_team or (home if winner_side == "home" else away if winner_side == "away" else "Draw")
        resolved_loser_team = (away if winner_side == "home" else home if winner_side == "away" else "")

        # ----------------------------
        # Lock voting by writing winners record
        # ----------------------------
        winners_path = _fz_winners_path(base)
        winners_blob = _json_load(winners_path, {})
        if not isinstance(winners_blob, dict):
            winners_blob = {}

        if fixture_id in winners_blob:
            rec = winners_blob.get(fixture_id) or {}
            return jsonify({
                "ok": True,
                "already_declared": True,
                "winner_side": (rec.get("winner_side") or rec.get("winner"))
            })

        ts = int(time.time())
        winners_blob[fixture_id] = {
            "winner_side": winner_side,
            "winner_team": resolved_winner_team or None,
            "declared_by": str(uid),
            "ts": ts
        }
        _json_save(winners_path, winners_blob)

        # ----------------------------
        # Load votes and voters (discord_voters)
        # ----------------------------
        votes_blob = _json_load(_fz_votes_path(base), {"fixtures": {}})
        fx = ((votes_blob.get("fixtures") or {}).get(fixture_id) or {}) if isinstance(votes_blob, dict) else {}
        dv = fx.get("discord_voters") if isinstance(fx, dict) else None
        if not isinstance(dv, dict):
            dv = {}

        # ----------------------------
        # Load/prepare events file
        # ----------------------------
        ev_path = _fan_zone_results_path(base)
        ev_blob = _json_load(ev_path, {"events": []})
        if not isinstance(ev_blob, dict):
            ev_blob = {"events": []}
        evs = ev_blob.get("events")
        if not isinstance(evs, list):
            evs = []
            ev_blob["events"] = evs

        existing_ids = {str(e.get("id")) for e in evs if isinstance(e, dict)}

        # ----------------------------
        # Notify logged-in voters
        # ----------------------------
        for voter_uid, choice in dv.items():
            voter_uid = str(voter_uid).strip()
            choice = str(choice or "").strip().lower()
            if not voter_uid or choice not in ("home", "away", "draw"):
                continue

            result = "win" if choice == winner_side else "lose"
            eid = f"fz:{fixture_id}:{voter_uid}:{ts}"
            if eid in existing_ids:
                continue

            title = f"Match Votes: {resolved_winner_team} declared" if resolved_winner_team else "Match Votes result"
            body_txt = "You won your Match Votes pick." if result == "win" else "You lost your Match Votes pick."

            evs.append({
                "id": eid,
                "discord_id": voter_uid,
                "fixture_id": fixture_id,
                "result": result,
                "title": title,
                "body": body_txt,
                "ts": ts
            })
            existing_ids.add(eid)

        # ----------------------------
        # Notify team owners (EVERY TIME)
        # Reads ownership from players.json -> teams[] -> ownership.main_owner + ownership.split_with
        # ----------------------------
        def _team_owner_ids(team_name: str):
            s = str(team_name or "").strip().lower()
            if not s:
                return set()

            owners = set()
            players_blob = _json_load(_players_path(base), {})
            if not isinstance(players_blob, dict):
                return owners

            for _, pdata in players_blob.items():
                if not isinstance(pdata, dict):
                    continue

                tlist = pdata.get("teams")
                if not isinstance(tlist, list):
                    continue

                for t in tlist:
                    if not isinstance(t, dict):
                        continue
                    if str(t.get("team") or "").strip().lower() != s:
                        continue

                    own = t.get("ownership") or {}
                    if isinstance(own, dict):
                        mo = own.get("main_owner")
                        if mo is not None and str(mo).strip():
                            owners.add(str(mo).strip())

                        sw = own.get("split_with")
                        if isinstance(sw, list):
                            for oid in sw:
                                if oid is not None and str(oid).strip():
                                    owners.add(str(oid).strip())

            return owners

        win_owners = _team_owner_ids(resolved_winner_team) if winner_side in ("home", "away") else set()
        lose_owners = _team_owner_ids(resolved_loser_team) if winner_side in ("home", "away") else set()
        all_owners = win_owners | lose_owners

        # Even if teams couldn't be resolved from matches.json, still notify owners of winner_team if provided
        # (loser owners won't be known in that case)
        if not all_owners and resolved_winner_team and winner_side in ("home", "away"):
            win_owners = _team_owner_ids(resolved_winner_team)
            all_owners = set(win_owners)

        for owner_uid in all_owners:
            owner_uid = str(owner_uid).strip()
            if not owner_uid:
                continue

            result = "win" if owner_uid in win_owners else "lose"
            eid = f"fzown:{fixture_id}:{owner_uid}:{result}:{ts}"
            if eid in existing_ids:
                continue

            title = f"Match declared: {resolved_winner_team}" if resolved_winner_team else "Match declared"

            if resolved_winner_team and resolved_loser_team:
                if result == "win":
                    body_txt = f"✅ Your team won - {resolved_winner_team} beat {resolved_loser_team}."
                else:
                    body_txt = f"❌ Your team lost - {resolved_loser_team} lost to {resolved_winner_team}."
            else:
                # Fallback if match teams unknown
                if result == "win":
                    body_txt = f"✅ Your team won - {resolved_winner_team} was declared the winner."
                else:
                    body_txt = f"❌ Your team lost - a match you own was declared."

            evs.append({
                "id": eid,
                "discord_id": owner_uid,
                "fixture_id": fixture_id,
                "result": result,
                "title": title,
                "body": body_txt,
                "ts": ts
            })
            existing_ids.add(eid)

        _json_save(ev_path, ev_blob)

        iso_map = _load_team_iso_map(base)
        winner_iso = iso_map.get(resolved_winner_team.lower(), "") if resolved_winner_team else ""
        loser_iso = iso_map.get(resolved_loser_team.lower(), "") if resolved_loser_team else ""

        channel_name = _resolve_fanzone_channel(base, fixture or {}, home, away)
        if not channel_name:
            cfg = _load_config(base)
            channel_name = str(cfg.get("FANZONE_CHANNEL_NAME") or cfg.get("FANZONE_CHANNEL") or "fanzone")

        _enqueue_command(base, {
            "kind": "fanzone_winner",
            "data": {
                "fixture_id": fixture_id,
                "home": home,
                "away": away,
                "utc": str((fixture or {}).get("utc") or (fixture or {}).get("time") or ""),
                "group": str((fixture or {}).get("group") or ""),
                "stage": str((fixture or {}).get("stage") or (fixture or {}).get("round") or (fixture or {}).get("phase") or ""),
                "winner_side": winner_side,
                "winner_team": resolved_winner_team,
                "loser_team": resolved_loser_team,
                "winner_iso": winner_iso,
                "loser_iso": loser_iso,
                "winner_owner_ids": sorted(win_owners),
                "loser_owner_ids": sorted(lose_owners),
                "channel": channel_name,
            }
        })
        log.info(
            "Match declared via public API (fixture_id=%s winner_side=%s winner_team=%s loser_team=%s notified_voters=%s notified_owners=%s)",
            fixture_id,
            winner_side,
            resolved_winner_team,
            resolved_loser_team,
            len(dv),
            len(all_owners),
        )

        return jsonify({
            "ok": True,
            "winner_side": winner_side,
            "winner_team": winner_team or resolved_winner_team or None,
            "notified_voters": len(dv),
            "notified_owners": len(all_owners)
        })

    @api.get("/fanzone/<fixture_id>")
    def api_fanzone_stats(fixture_id):
        base = ctx.get("BASE_DIR", "")
        fid = str(fixture_id or "").strip()
        if not fid:
            return jsonify({"ok": False, "error": "bad_fixture"}), 400

        votes_blob = _json_load(_fz_votes_path(base), {"fixtures": {}})
        winners_blob = _json_load(_fz_winners_path(base), {})

        fx = (votes_blob.get("fixtures") or {}).get(fid, {}) if isinstance(votes_blob, dict) else {}
        home_n = int(fx.get("home") or 0)
        away_n = int(fx.get("away") or 0)
        draw_n = int(fx.get("draw") or 0)
        total = max(0, home_n + away_n + draw_n)

        last_choice = None
        fan_id = _get_fan_id()
        voters = fx.get("voters") if isinstance(fx, dict) else None
        if fan_id and isinstance(voters, dict):
            last_choice = voters.get(fan_id)

        home_pct = (home_n / total * 100.0) if total else 0.0
        away_pct = (away_n / total * 100.0) if total else 0.0
        draw_pct = (draw_n / total * 100.0) if total else 0.0

        winner = None
        winner_team = None
        declared_at = None

        if isinstance(winners_blob, dict) and fid in winners_blob:
            rec = winners_blob.get(fid) or {}
            if isinstance(rec, dict):
                winner = (rec.get("winner_side") or rec.get("winner") or None)
                winner_team = (rec.get("winner_team") or None)
                declared_at = rec.get("ts") or rec.get("declared_at") or None

        return jsonify({
            "ok": True,
            "home_votes": home_n,
            "away_votes": away_n,
            "draw_votes": draw_n,
            "total": total,
            "home_pct": home_pct,
            "away_pct": away_pct,
            "draw_pct": draw_pct,
            "last_choice": last_choice,
            "winner": winner,
            "winner_team": winner_team,
            "declared_at": declared_at
        })

    @api.get("/fanzone/winners")
    def api_fanzone_winners():
        base = ctx.get("BASE_DIR", "")
        winners_blob = _json_load(_fz_winners_path(base), {})
        if not isinstance(winners_blob, dict):
            winners_blob = {}
        winners = {}
        for fid, rec in winners_blob.items():
            if not isinstance(rec, dict):
                continue
            winners[str(fid)] = {
                "winner_side": rec.get("winner_side") or rec.get("winner") or "",
                "winner_team": rec.get("winner_team") or "",
            }
        return jsonify({"ok": True, "winners": winners})

    @api.get("/fanzone/stats/<fixture_id>")
    def api_fanzone_stats_alias(fixture_id):
        return api_fanzone_stats(fixture_id)

    def _fanzone_vote_leaderboard(result_kind: str):
        base = ctx.get("BASE_DIR", "")
        winners_blob = _json_load(_fz_winners_path(base), {})
        votes_blob = _json_load(_fz_votes_path(base), {"fixtures": {}})

        counts = {}
        seen = set()
        if isinstance(winners_blob, dict):
            for key, rec in winners_blob.items():
                if not isinstance(rec, dict):
                    continue
                fixture_id = str(rec.get("fixture_id") or key or "").strip()
                if not fixture_id or fixture_id in seen:
                    continue
                seen.add(fixture_id)

                winner_side = str(rec.get("winner_side") or rec.get("winner") or "").strip().lower()
                if winner_side not in ("home", "away", "draw"):
                    continue

                fx = ((votes_blob.get("fixtures") or {}).get(fixture_id) or {}) if isinstance(votes_blob, dict) else {}
                dv = fx.get("discord_voters") if isinstance(fx, dict) else None
                if not isinstance(dv, dict):
                    continue

                for voter_uid, choice in dv.items():
                    voter_uid = str(voter_uid).strip()
                    choice = str(choice or "").strip().lower()
                    if not voter_uid or choice not in ("home", "away", "draw"):
                        continue
                    is_win = choice == winner_side
                    if (result_kind == "wins" and is_win) or (result_kind == "losses" and not is_win):
                        counts[voter_uid] = counts.get(voter_uid, 0) + 1

        rows = [{"id": uid, result_kind: total} for uid, total in counts.items()]
        rows.sort(key=lambda x: (-x.get(result_kind, 0), str(x.get("id") or "")))
        return jsonify({"ok": True, "rows": rows})

    @api.get("/leaderboards/fanzone_wins")
    def api_fanzone_wins_leaderboard():
        return _fanzone_vote_leaderboard("wins")

    @api.get("/leaderboards/fanzone_losses")
    def api_fanzone_losses_leaderboard():
        return _fanzone_vote_leaderboard("losses")

    return root, api, auth
