from flask import Blueprint, jsonify, send_from_directory, current_app, abort, request, send_file
import os, time, json, shutil, zipfile, datetime, glob
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

def _backup_dir(base_dir):   return _ensure_dir(os.path.join(base_dir, "Backups"))
def _json_dir(base_dir):     return _ensure_dir(os.path.join(base_dir, "JSON"))
def _runtime_dir(base_dir):  return _ensure_dir(os.path.join(base_dir, "runtime"))
def _cmd_queue_path(base_dir): return os.path.join(_runtime_dir(base_dir), "bot_commands.jsonl")

def _enqueue_command(base_dir, cmd: dict):
    cmd = dict(cmd); cmd["ts"] = int(time.time())
    with open(_cmd_queue_path(base_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(cmd) + "\n")

def _bets_path(base_dir):       return os.path.join(_json_dir(base_dir), "bets.json")
def _ownership_path(base_dir):  return os.path.join(_json_dir(base_dir), "ownership.json")
def _verified_path(base_dir):   return os.path.join(_json_dir(base_dir), "verified.json")
def _guilds_path(base_dir):     return os.path.join(_json_dir(base_dir), "guilds.json")
def _split_requests_path(base_dir): return os.path.join(_json_dir(base_dir), "split_requests.json")
def _players_path(base_dir):    return os.path.join(_json_dir(base_dir), "players.json")
def _teams_path(base_dir):      return os.path.join(_json_dir(base_dir), "teams.json")
def _team_iso_path(base_dir):   return os.path.join(_json_dir(base_dir), "team_iso.json")

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

# ---------- Blueprints ----------
def create_public_routes(ctx):
    root = Blueprint("root_public", __name__)
    api  = Blueprint("public_api", __name__, url_prefix="/api")

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

    # ---------- VERIFIED (normalize from {"verified_users":[...]}) ----------
    @api.get("/verified")
    def api_verified():
        base = ctx.get("BASE_DIR", "")
        blob = _json_load(_verified_path(base), {})
        raw = blob.get("verified_users") if isinstance(blob, dict) else blob
        out = []
        if isinstance(raw, list):
            for v in raw:
                if not isinstance(v, dict): continue
                user = {
                    "discord_id": str(v.get("discord_id") or v.get("id") or v.get("user_id") or ""),
                    "username": v.get("username") or v.get("name") or "",   # may be empty in your schema
                    "display_name": (v.get("display_name") or v.get("username") or ""),
                    "habbo_name": v.get("habbo_name") or ""
                }
                out.append(user)
        return jsonify(out)

    # ---------- Bets (enriched with display_name using verified_users) ----------
    @api.get("/bets")
    def api_bets():
        base = ctx.get("BASE_DIR", "")
        bets = _json_load(_bets_path(base), [])
        verified_blob = _json_load(_verified_path(base), {})
        verified = verified_blob.get("verified_users") if isinstance(verified_blob, dict) else verified_blob

        # id -> display_name (or username if needed)
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
            item = dict(b)  # do not mutate file
            o1 = resolve(item.get("option1_user_id"), item.get("option1_user_name"))
            o2 = resolve(item.get("option2_user_id"), item.get("option2_user_name"))
            item["option1_user_name"] = o1
            item["option2_user_name"] = o2
            item["option1_display_name"] = o1
            item["option2_display_name"] = o2
            out.append(item)
        return jsonify(out)

    # ---------- Ownership from players ----------
    @api.get("/ownership_merged")
    def ownership_merged():
        base = ctx.get("BASE_DIR", "")

        def _json_load(path, default):
            try:
                import json, os
                if not os.path.isfile(path):
                    return default
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                # Malformed JSON -> return safe default instead of crashing
                return default

        import os

        def _json_dir(base_dir):
            return os.path.join(base_dir, "JSON")

        def _players_path(base_dir):
            return os.path.join(_json_dir(base_dir), "players.json")

        def _teams_path(base_dir):
            return os.path.join(_json_dir(base_dir), "teams.json")

        try:
            # 1) teams list (support list or {"teams":[...]})
            teams_raw = _json_load(_teams_path(base), [])
            if isinstance(teams_raw, dict):
                teams = teams_raw.get("teams", [])
            elif isinstance(teams_raw, list):
                teams = teams_raw
            else:
                teams = []
            if not isinstance(teams, list):
                teams = []

            # 2) players -> id -> display name
            players = _json_load(_players_path(base), {})
            id_to_name = {}
            if isinstance(players, dict):
                for uid, pdata in players.items():
                    nm = None
                    if isinstance(pdata, dict):
                        nm = (
                                pdata.get("display_name")
                                or pdata.get("username")
                                or pdata.get("name")
                        )
                    id_to_name[str(uid)] = str(nm or uid)

            # 3) Build country -> ownership map safely
            country_map = {}
            if isinstance(players, dict):
                for uid, pdata in players.items():
                    if not isinstance(pdata, dict):
                        continue
                    for entry in (pdata.get("teams") or []):
                        if not isinstance(entry, dict):
                            # legacy flat entry -> {"team": entry}
                            team = str(entry)
                            if not team:
                                continue
                            rec = country_map.setdefault(team, {"main_owner": None, "split_with": []})
                            # nothing else we can infer here
                            continue

                        team = entry.get("team")
                        if not team:
                            continue
                        own = entry.get("ownership") or {}
                        main_owner = own.get("main_owner")
                        split_with = own.get("split_with") or []

                        rec = country_map.setdefault(team, {"main_owner": None, "split_with": []})
                        # Set/overwrite main owner if it's this uid or if empty
                        if main_owner is not None:
                            if rec["main_owner"] is None or str(main_owner) == str(uid):
                                rec["main_owner"] = str(main_owner)
                        # Append splits
                        for sid in split_with if isinstance(split_with, list) else [split_with]:
                            sid = str(sid).strip()
                            if sid and sid not in rec["split_with"]:
                                rec["split_with"].append(sid)

            # 4) Emit rows for all known teams; if teams list is empty, at least emit rows for whatever we saw in players
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
                    "owners_count": (1 if main_id else 0) + len(split_ids)
                })

            return jsonify({"rows": rows, "count": len(rows)})

        except Exception as e:
            # Return JSON instead of HTML error page, so the frontend prints a clear message
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

        # players.json -> { "<discord_id>": { "display_name": "...", "teams": [ { "team": "...", "ownership": { "main_owner": "...", "split_with": ["..."] } } ] } }
        def _json_load(path, default):
            try:
                import json, os
                if not os.path.isfile(path): return default
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default

        import os
        def _json_dir(base_dir):
            return os.path.join(base_dir, "JSON")

        def _players_path(base_dir):
            return os.path.join(_json_dir(base_dir), "players.json")

        players = _json_load(_players_path(base), {})
        # id -> nice name
        id_to_name = {}
        if isinstance(players, dict):
            for uid, pdata in players.items():
                if isinstance(pdata, dict):
                    nm = pdata.get("display_name") or pdata.get("username") or pdata.get("name") or str(uid)
                else:
                    nm = str(uid)
                id_to_name[str(uid)] = str(nm)

        # build country -> owners
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
                    rec = country_map.setdefault(team, {"main_owner": None, "split_with": []})
                    if main_owner is not None:
                        if rec["main_owner"] is None or str(main_owner) == str(uid):
                            rec["main_owner"] = str(main_owner)
                    for sid in split_with:
                        if sid and sid not in rec["split_with"]:
                            rec["split_with"].append(sid)

        # normalize rows that the UI expects
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
                "owners_count": (1 if main_id else 0) + len(split_ids)
            })
        return jsonify({"rows": rows, "count": len(rows)})

    @api.get("/ownerships")
    def ownerships_get():
        base = ctx.get("BASE_DIR", "")

        # Build id -> display_name map from verified.json {"verified_users":[...]}
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
            # dict?
            if isinstance(x, dict):
                did = str(x.get("discord_id") or x.get("id") or x.get("user_id") or "").strip()
                disp = (x.get("display_name") or x.get("username") or x.get("name") or "").strip()
                if did and id_to_display.get(did):
                    return id_to_display[did]
                return disp or did
            # string id?
            sx = str(x).strip()
            if sx.isdigit() and id_to_display.get(sx):
                return id_to_display[sx]
            return sx

        raw = _json_load(_ownership_path(base), {})
        items = []

        if isinstance(raw, dict):
            for team, val in raw.items():
                owners = []
                # val can be list (owners) or dict with owners/splits
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
                splits_disp = [resolve_name(s) for s in (splits or owners_disp[1:]) if
                               s]  # if no explicit splits, treat extra owners as splits

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

    # ---------- Minimal split endpoints exposed publicly (unchanged) ----------
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

    # ---------- Cogs + Backups (unchanged) ----------
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