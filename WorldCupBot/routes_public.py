from flask import Blueprint, jsonify, send_from_directory, current_app, abort, request, send_file
import os, time, platform, json, shutil, zipfile, datetime, glob
import psutil

# ---------- Helpers ----------
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

def _backup_dir(base_dir):
    return _ensure_dir(os.path.join(base_dir, "Backups"))

def _json_dir(base_dir):
    return _ensure_dir(os.path.join(base_dir, "JSON"))

def _runtime_dir(base_dir):
    return _ensure_dir(os.path.join(base_dir, "runtime"))

def _cmd_queue_path(base_dir):
    return os.path.join(_runtime_dir(base_dir), "bot_commands.jsonl")

def _enqueue_command(base_dir, cmd: dict):
    cmd = dict(cmd)
    cmd["ts"] = int(time.time())
    with open(_cmd_queue_path(base_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(cmd) + "\n")

def _bets_path(base_dir): return os.path.join(_json_dir(base_dir), "bets.json")
def _ownership_path(base_dir): return os.path.join(_json_dir(base_dir), "ownership.json")
def _verified_users_path(base_dir): return os.path.join(_json_dir(base_dir), "verified_users.json")
def _guilds_path(base_dir): return os.path.join(_json_dir(base_dir), "guilds.json")
def _split_requests_path(base_dir): return os.path.join(_json_dir(base_dir), "split_requests.json")

def _list_backups(base_dir):
    bdir = _backup_dir(base_dir)
    out = []
    for name in sorted(os.listdir(bdir)):
        fp = os.path.join(bdir, name)
        if os.path.isfile(fp):
            out.append({"name": name, "size": os.path.getsize(fp), "ts": int(os.path.getmtime(fp)), "rel": name})
    return sorted(out, key=lambda x: x["ts"], reverse=True)

def _create_backup(base_dir):
    bdir = _backup_dir(base_dir)
    jdir = _json_dir(base_dir)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outname = f"json-backup-{ts}.zip"
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
        _ensure_dir(jdir)
        z.extractall(jdir)
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
            out = [l.decode("utf-8", "ignore") for l in data[-max_lines:]]
            return out
        except Exception:
            f.seek(0)
            lines = f.read().decode("utf-8", "ignore").splitlines()
            return lines[-max_lines:]

# ---------- Blueprints ----------
def create_public_routes(ctx):
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
            if os.path.exists(path): return send_from_directory(static_folder, name)
        abort(404)

    # ---------- Dashboard endpoints ----------
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
        # Use psutil directly for rich system metrics
        try:
            sys_mem = psutil.virtual_memory()
            sys_cpu = psutil.cpu_percent(interval=0.1)
            disk = psutil.disk_usage('/')
        except Exception:
            # Fallback if psutil missing
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
        start_ts = None
        stop_ts = None

        # Try to resolve from process create_time for accuracy
        try:
            if running:
                pid = ctx.get("bot_process").pid if ctx.get("bot_process") else None
                if pid:
                    p = psutil.Process(pid)
                    start_ts = p.create_time()
        except Exception:
            start_ts = None

        # Fallback to refs
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

    # ---------- Health (crash monitor) ----------
    @api.get("/health")
    def api_health():
        """Expose crash status and basic runtime health."""
        running = bool(ctx["is_bot_running"]())
        # allow launcher to provide a callable that returns crash status
        crash_status = {}
        f = ctx.get("get_crash_status")
        if callable(f):
            try:
                crash_status = f() or {}
            except Exception:
                crash_status = {}
        # fallbacks
        last_start = (ctx.get("bot_last_start_ref") or {}).get("value")
        last_stop = (ctx.get("bot_last_stop_ref") or {}).get("value")
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

    @api.get("/guilds")
    def api_guilds():
        data = _json_load(_guilds_path(ctx.get("BASE_DIR","")), {"guild_count": 0, "guilds": []})
        return jsonify(data)

    # Bot process controls
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

    # ---------- Bets ----------
    @api.get("/bets")
    def api_bets():
        base = ctx.get("BASE_DIR", "")
        data = _json_load(_bets_path(base), [])
        return jsonify(data if isinstance(data, list) else {"bets": data})

    @api.post("/bets/settle")
    def api_bets_settle():
        base = ctx.get("BASE_DIR","")
        body = request.get_json(silent=True) or {}
        bet_id = body.get("bet_id"); winner_id = body.get("winner_id")
        if not bet_id or not winner_id:
            return jsonify({"ok": False, "error": "bet_id and winner_id required"}), 400
        _enqueue_command(base, {"kind": "bet_settle", "bet_id": bet_id, "winner_id": str(winner_id)})
        return jsonify({"ok": True})

    # ---------- Ownerships and verification ----------
    @api.get("/ownerships")
    def ownerships_get():
        base = ctx.get("BASE_DIR","")
        raw = _json_load(_ownership_path(base), {})
        ownerships = []
        if isinstance(raw, dict):
            for country, owners in raw.items():
                if owners is None: owners = []
                if isinstance(owners, str): owners = [owners]
                ownerships.append({"country": country, "owners": owners})
        verified = _json_load(_verified_users_path(base), [])
        return jsonify({"ownerships": ownerships, "verified_users": verified})

    @api.post("/ownership/update")
    def ownership_update():
        base = ctx.get("BASE_DIR","")
        body = request.get_json(silent=True) or {}
        country = (body.get("country") or "").strip()
        owners = body.get("owners")
        action = (body.get("action") or "reassign").lower()
        if not country or owners is None:
            return jsonify({"ok": False, "error": "country and owners required"}), 400
        data = _json_load(_ownership_path(base), {})
        if action == "reassign":
            data[country] = owners
        elif action == "split":
            cur = data.get(country, [])
            if isinstance(cur, str): cur = [cur]
            for o in owners:
                if o not in cur: cur.append(o)
            data[country] = cur
        else:
            data[country] = owners
        _json_save(_ownership_path(base), data)
        return jsonify({"ok": True})

    @api.get("/verified")
    def verified_list():
        base = ctx.get("BASE_DIR","")
        users = _json_load(_verified_users_path(base), [])
        return jsonify(users)

    # ---------- Split requests ----------
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
        return jsonify({"ok": True, "msg": "queued"})

    # ---------- Cogs ----------
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

    # ---------- Backups ----------
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
        return jsonify({"ok": True, "restored": name})

    return [root, api]
