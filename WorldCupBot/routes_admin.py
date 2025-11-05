import os, json, time, glob, sys
from flask import Blueprint, jsonify, request, session, send_file

# Public OAuth flow (in routes_public.py) stores the logged-in user bundle here
USER_SESSION_KEY = "wc_user"   # e.g. {"discord_id": "...", "username": "...", ...}
ADMIN_IDS_KEY    = "ADMIN_IDS" # list of Discord IDs allowed as admins
STAGE_ALLOWED = {
    "Eliminated",
    "Group Stage",
    "Round of 32",
    "Round of 16",
    "Quarter Final",
    "Semi Final",
    "Final",
    "Winner",
}

# ---- PATH / IO HELPERS ----
def _base_dir(ctx):
    return ctx.get("BASE_DIR", os.getcwd())

def _json_dir(ctx):
    return os.path.join(_base_dir(ctx), "JSON")

def _path(ctx, name):
    return os.path.join(_json_dir(ctx), name)

def _read_json(path, default):
    try:
        if not os.path.isfile(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def _now_iso():
    import datetime as _dt
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _commands_path(ctx):
    rd = os.path.join(_base_dir(ctx), "runtime")
    os.makedirs(rd, exist_ok=True)
    return os.path.join(rd, "bot_commands.jsonl")

def _enqueue_command(ctx, kind, payload=None):
    cmd = {"ts": int(time.time()), "kind": kind, "data": payload or {}}
    with open(_commands_path(ctx), "a", encoding="utf-8") as f:
        f.write(json.dumps(cmd, separators=(",", ":")) + "\n")

# ---- LOG HELPERS ----
def _logs_dir(ctx):
    d = os.path.join(_base_dir(ctx), "logs")
    os.makedirs(d, exist_ok=True)
    return d

def _log_paths(ctx):
    lp = ctx.get("LOG_PATHS") or {}
    if isinstance(lp, dict) and lp:
        return lp
    d = _logs_dir(ctx)
    return {
        "bot":      os.path.join(d, "bot.log"),
        "health":   os.path.join(d, "health.log"),
        "launcher": os.path.join(d, "launcher.log"),
    }

def _log_path(ctx, kind):
    return _log_paths(ctx).get(str(kind))

# ---- VERIFIED MAP (discord id -> display name) ----
def _verified_map(ctx):
    blob = _read_json(_path(ctx, "verified.json"), {})
    raw = blob.get("verified_users") if isinstance(blob, dict) else blob
    out = {}
    if isinstance(raw, list):
        for v in raw:
            if not isinstance(v, dict):
                continue
            did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "").strip()
            if not did:
                continue
            disp = (v.get("display_name") or v.get("username") or "").strip()
            out[did] = disp or did
    return out

# ---- ADMIN SESSION / CONFIG ----
def _load_config(ctx):
    cfg_path = os.path.join(_base_dir(ctx), "config.json")
    try:
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

def _current_user():
    u = session.get(USER_SESSION_KEY) or None
    if isinstance(u, dict) and u.get("discord_id"):
        return u
    return None

def _is_admin(ctx):
    u = _current_user()
    if not u:
        return False
    cfg = _load_config(ctx)
    allow = cfg.get(ADMIN_IDS_KEY) or []
    try:
        allow = [str(x) for x in allow]
    except Exception:
        allow = []
    return str(u.get("discord_id")) in allow

# ---- BLUEPRINT ----
def create_admin_routes(ctx):
    bp = Blueprint("admin", __name__, url_prefix="/admin")

    # ---------- Auth endpoints (Discord-session based) ----------
    @bp.get("/auth/status")
    def auth_status():
        u = _current_user()
        return jsonify({
            "unlocked": bool(_is_admin(ctx)),
            "user": {
                "discord_id": (u or {}).get("discord_id"),
                "username":   (u or {}).get("username"),
                "global_name":(u or {}).get("global_name"),
                "avatar":     (u or {}).get("avatar"),
            }
        })

    # Helper: gate every admin action
    def require_admin():
        if _is_admin(ctx):
            return None
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    # ---------- Bot controls ----------
    def _callable(fn):
        try:
            return callable(fn)
        except Exception:
            return False

    def _run_or_queue(action):
        key = {
            "start": "start_bot",
            "stop": "stop_bot",
            "restart": "restart_bot",
        }.get(action)

        fn = ctx.get(key)
        if _callable(fn):
            try:
                ok = bool(fn())
            except Exception:
                ok = False
        else:
            _enqueue_command(ctx, f"bot_{action}")
            ok = True
        return ok

    @bp.get("/bot/status")
    def bot_status():
        fn = ctx.get("is_bot_running")
        running = False
        if _callable(fn):
            try:
                running = bool(fn())
            except Exception:
                running = False
        last_start = (ctx.get("bot_last_start_ref") or {}).get("value")
        last_stop  = (ctx.get("bot_last_stop_ref")  or {}).get("value")
        return jsonify({"ok": True, "running": running, "last_start": last_start, "last_stop": last_stop})

    @bp.post("/bot/start")
    def bot_start():
        resp = require_admin()
        if resp is not None: return resp
        ok = _run_or_queue("start")
        return jsonify({"ok": ok, "action": "start"})

    @bp.post("/bot/stop")
    def bot_stop():
        resp = require_admin()
        if resp is not None: return resp
        ok = _run_or_queue("stop")
        return jsonify({"ok": ok, "action": "stop"})

    @bp.post("/bot/restart")
    def bot_restart():
        resp = require_admin()
        if resp is not None: return resp
        ok = _run_or_queue("restart")
        return jsonify({"ok": ok, "action": "restart"})

    # ---------- Ownership (reassign) ----------
    def _players_path(ctx):
        return _path(ctx, "players.json")

    @bp.post("/ownership/reassign")
    def ownership_reassign():
        resp = require_admin()
        if resp is not None: return resp

        data = request.get_json(silent=True) or {}
        team = (data.get("team") or "").strip()
        new_owner_id = str(data.get("new_owner_id") or "").strip()
        if not team or not new_owner_id:
            return jsonify({"ok": False, "error": "missing team or new_owner_id"}), 400

        players = _read_json(_players_path(ctx), {})
        if not isinstance(players, dict):
            players = {}

        def ensure_player(uid):
            uid = str(uid)
            if uid not in players or not isinstance(players[uid], dict):
                players[uid] = {"display_name": uid, "teams": []}
            players[uid].setdefault("teams", [])
            return players[uid]

        # Clear existing main_owner for this team
        for uid, pdata in list(players.items()):
            if not isinstance(pdata, dict):
                continue
            for entry in pdata.get("teams", []):
                if not isinstance(entry, dict):
                    continue
                if entry.get("team") == team:
                    entry.setdefault("ownership", {})
                    if str(entry["ownership"].get("main_owner") or "") == str(uid):
                        entry["ownership"]["main_owner"] = None

        # Set new main
        target = ensure_player(new_owner_id)
        target_entry = None
        for entry in target.get("teams", []):
            if isinstance(entry, dict) and entry.get("team") == team:
                target_entry = entry
                break
        if target_entry is None:
            target_entry = {"team": team, "ownership": {"main_owner": new_owner_id, "split_with": []}}
            target["teams"].append(target_entry)
        else:
            target_entry.setdefault("ownership", {})
            target_entry["ownership"]["main_owner"] = new_owner_id
            target_entry["ownership"].setdefault("split_with", [])

        _write_json_atomic(_players_path(ctx), players)

        vmap = _verified_map(ctx)
        row = {
            "country": team,
            "main_owner": {"id": new_owner_id, "username": vmap.get(new_owner_id, new_owner_id)},
            "split_with": [
                {"id": sid, "username": vmap.get(str(sid), str(sid))}
                for sid in target_entry["ownership"].get("split_with", [])
            ],
            "owners_count": 1 + len(target_entry["ownership"].get("split_with", []))
        }
        _enqueue_command(ctx, "ownership_reassign", {"team": team, "new_owner_id": new_owner_id})
        return jsonify({"ok": True, "row": row})

    # ---------- COGS ----------
    def _scan_cogs():
        results = []
        cdir = os.path.join(_base_dir(ctx), "COGS")
        if not os.path.isdir(cdir):
            return results
        loaded_exts = set()
        try:
            st = _read_json(_path(ctx, "cogs_status.json"), {})
            if isinstance(st, dict) and isinstance(st.get("loaded"), list):
                loaded_exts = set(st["loaded"])
        except Exception:
            pass
        if not loaded_exts and ctx.get("bot"):
            try:
                if getattr(ctx["bot"], "extensions", None):
                    loaded_exts = set(ctx["bot"].extensions.keys())
            except Exception:
                loaded_exts = set()
        sysmods = set(sys.modules.keys())
        for py in sorted(glob.glob(os.path.join(cdir, "*.py"))):
            name = os.path.splitext(os.path.basename(py))[0]
            if name.startswith("_"):
                continue
            module_name = f"COGS.{name}"
            is_loaded = ((module_name in loaded_exts) or (not loaded_exts and module_name in sysmods))
            results.append({"name": name, "loaded": bool(is_loaded)})
        return results

    @bp.get("/cogs")
    def cogs_list():
        resp = require_admin()
        if resp is not None: return resp
        return jsonify({"ok": True, "cogs": _scan_cogs()})

    def _enqueue_cog(cog, action):
        _enqueue_command(ctx, f"cog_{action}", {"name": cog})

    @bp.post("/cogs/<cog>/load")
    def cogs_load(cog):
        resp = require_admin()
        if resp is not None: return resp
        _enqueue_cog(cog, "load")
        return jsonify({"ok": True})

    @bp.post("/cogs/<cog>/unload")
    def cogs_unload(cog):
        resp = require_admin()
        if resp is not None: return resp
        _enqueue_cog(cog, "unload")
        return jsonify({"ok": True})

    @bp.post("/cogs/<cog>/reload")
    def cogs_reload(cog):
        resp = require_admin()
        if resp is not None: return resp
        _enqueue_cog(cog, "reload")
        return jsonify({"ok": True})

    # ---------- SPLITS ----------
    def _split_requests_path(): return _path(ctx, "split_requests.json")
    def _split_requests_log_path(): return _path(ctx, "split_requests_log.json")

    def _append_split_history(event):
        path = _split_requests_log_path()
        raw = _read_json(path, [])
        if isinstance(raw, dict):
            events = raw.get("events", [])
            events.append(event)
            raw["events"] = events
            _write_json_atomic(path, raw)
            return len(events)
        else:
            raw.append(event)
            _write_json_atomic(path, raw)
            return len(raw)

    def _resolve_names(ctx, ids):
        m = _verified_map(ctx)
        return {str(x): m.get(str(x), str(x)) for x in {str(i) for i in ids if i is not None}}

    @bp.get("/splits")
    def splits_get():
        resp = require_admin()
        if resp is not None:
            return resp

        raw = _read_json(_split_requests_path(), {})
        pending = []
        id_bucket = set()

        if isinstance(raw, dict):
            for key, v in raw.items():
                if not isinstance(v, dict):
                    continue
                req_id = str(v.get("requester_id") or "")
                own_id = str(v.get("main_owner_id") or "")
                id_bucket.update({req_id, own_id})
                pending.append({
                    "id": key,
                    "team": v.get("team"),
                    "requester_id": req_id,
                    "main_owner_id": own_id,
                    "expires_at": v.get("expires_at"),
                    "status": "pending"
                })

        names = _resolve_names(ctx, id_bucket)
        for p in pending:
            rid = p.get("requester_id", "")
            oid = p.get("main_owner_id", "")
            p["from_username"] = names.get(rid, rid)
            p["to_username"]   = names.get(oid, oid)
            p["from"] = p["from_username"]
            p["to"]   = p["to_username"]

        return jsonify({"pending": pending})

    @bp.post("/splits/accept")
    def splits_accept():
        resp = require_admin()
        if resp is not None: return resp
        data = request.get_json(silent=True) or {}
        sid = data.get("id"); reason = data.get("reason") or ""
        if not sid: return jsonify({"ok": False, "error": "missing id"}), 400

        req_path = _split_requests_path()
        pending_raw = _read_json(req_path, {})
        if not isinstance(pending_raw, dict): pending_raw = {}

        entry = pending_raw.pop(sid, None)
        if not isinstance(entry, dict): return jsonify({"ok": False, "error": "not_found"}), 404
        _write_json_atomic(req_path, pending_raw)

        req_id = str(entry.get("requester_id") or "")
        own_id = str(entry.get("main_owner_id") or "")
        names = _resolve_names(ctx, {req_id, own_id})
        event = {
            "id": sid, "action": "accepted", "team": entry.get("team"),
            "requester_id": req_id, "main_owner_id": own_id,
            "from_username": names.get(req_id, req_id), "to_username": names.get(own_id, own_id),
            "reason": reason, "timestamp": _now_iso(),
        }
        _append_split_history(event)
        _enqueue_command(ctx, "split_accept", {"id": sid, "reason": reason})
        return jsonify({"ok": True, "event": event})

    @bp.post("/splits/decline")
    def splits_decline():
        resp = require_admin()
        if resp is not None: return resp
        data = request.get_json(silent=True) or {}
        sid = data.get("id"); reason = data.get("reason") or ""
        if not sid: return jsonify({"ok": False, "error": "missing id"}), 400

        req_path = _split_requests_path()
        pending_raw = _read_json(req_path, {})
        if not isinstance(pending_raw, dict): pending_raw = {}

        entry = pending_raw.pop(sid, None)
        if not isinstance(entry, dict): return jsonify({"ok": False, "error": "not_found"}), 404
        _write_json_atomic(req_path, pending_raw)

        req_id = str(entry.get("requester_id") or "")
        own_id = str(entry.get("main_owner_id") or "")
        names = _resolve_names(ctx, {req_id, own_id})
        event = {
            "id": sid, "action": "declined", "team": entry.get("team"),
            "requester_id": req_id, "main_owner_id": own_id,
            "from_username": names.get(req_id, req_id), "to_username": names.get(own_id, own_id),
            "reason": reason, "timestamp": _now_iso(),
        }
        _append_split_history(event)
        _enqueue_command(ctx, "split_decline", {"id": sid, "reason": reason})
        return jsonify({"ok": True, "event": event})

    @bp.get("/splits/history")
    def splits_history():
        resp = require_admin()
        if resp is not None:
            return resp

        raw = _read_json(_split_requests_log_path(), [])
        events = raw.get("events") if isinstance(raw, dict) else raw
        if not isinstance(events, list):
            events = []

        id_bucket = set()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            for k in ("requester_id", "main_owner_id", "from_id", "to_id", "from", "to"):
                v = ev.get(k)
                if v:
                    id_bucket.add(str(v))

        names = _resolve_names(ctx, id_bucket)

        norm = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            e = dict(ev)
            req_id = str(ev.get("requester_id") or ev.get("from_id") or ev.get("from") or "")
            own_id = str(ev.get("main_owner_id") or ev.get("to_id") or ev.get("to") or "")
            e["from_id"] = req_id
            e["to_id"]   = own_id
            e["from_username"] = names.get(req_id, req_id)
            e["to_username"]   = names.get(own_id, own_id)
            e["from"] = e["from_username"]
            e["to"]   = e["to_username"]
            norm.append(e)

        try:
            limit = int(request.args.get("limit", "200"))
        except Exception:
            limit = 200
        norm = norm[-abs(limit):]

        return jsonify({"events": norm})

    # ---------- BETS: declare winner ----------
    def _bets_path(): return _path(ctx, "bets.json")

    def _enrich_bet_names(b):
        item = dict(b)
        vmap = _verified_map(ctx)
        def resolve(uid, fallback):
            key = str(uid) if uid is not None else ""
            return (vmap.get(key) or fallback or key or "")
        if "option1_user_id" in item or "option1_user_name" in item:
            item["option1_user_name"] = resolve(item.get("option1_user_id"), item.get("option1_user_name"))
        if "option2_user_id" in item or "option2_user_name" in item:
            item["option2_user_name"] = resolve(item.get("option2_user_id"), item.get("option2_user_name"))
        return item

    @bp.post("/bets/<bet_id>/winner")
    def bets_declare_winner(bet_id):
        resp = require_admin()
        if resp is not None: return resp
        data = request.get_json(silent=True) or {}
        winner = str(data.get("winner") or "").lower()
        if winner not in ("option1", "option2", ""):
            return jsonify({"ok": False, "error": "winner must be option1 or option2"}), 400

        bets = _read_json(_bets_path(), [])
        seq = bets if isinstance(bets, list) else bets.get("bets", [])
        found = None
        for b in seq or []:
            if str(b.get("bet_id")) == str(bet_id):
                found = b; break
        if not found:
            return jsonify({"ok": False, "error": "bet_not_found"}), 404

        found["winner"] = winner or None
        _write_json_atomic(_bets_path(), bets)
        _enqueue_command(ctx, "bet_winner_declared", {"bet_id": bet_id, "winner": found["winner"]})
        return jsonify({"ok": True, "bet": _enrich_bet_names(found)})

    # ---------- LOGS ----------
    @bp.get("/log/<kind>")
    def admin_log_get(kind):
        resp = require_admin()
        if resp is not None:
            return resp
        path = _log_path(ctx, kind)
        lines = []
        try:
            if path and os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()[-2000:]
        except Exception:
            lines = []
        return jsonify({"lines": lines})

    @bp.post("/log/<kind>/clear")
    def admin_log_clear(kind):
        resp = require_admin()
        if resp is not None:
            return resp
        path = _log_path(ctx, kind)
        if not path:
            return jsonify({"ok": False, "error": "unknown_log"}), 404
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.get("/log/<kind>/download")
    def admin_log_download(kind):
        resp = require_admin()
        if resp is not None:
            return resp
        path = _log_path(ctx, kind)
        if not (path and os.path.isfile(path)):
            return jsonify({"ok": False, "error": "not_found"}), 404
        return send_file(path, as_attachment=True, download_name=f"{kind}.log", mimetype="text/plain")

    # === view/update stages ===
    def _team_stage_path(ctx):
        return os.path.join(_json_dir(ctx), "team_stage.json")

    @bp.get("/teams/stage")
    def admin_team_stage_get():
        resp = require_admin()
        if resp is not None:
            return resp
        base_dir = ctx.get("BASE_DIR", "")
        path = _team_stage_path(base_dir)
        data = _read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        return jsonify({"ok": True, "stages": data})

    @bp.post("/teams/stage")
    def admin_team_stage_set():
        resp = require_admin()
        if resp is not None: return resp
        body = request.get_json(silent=True) or {}
        team = (body.get("team") or "").strip()
        stage = (body.get("stage") or "").strip()

        if not team or not stage:
            return jsonify({"ok": False, "error": "missing team or stage"}), 400
        if stage not in STAGE_ALLOWED:
            return jsonify({"ok": False, "error": "invalid stage"}), 400

        path = _team_stage_path(ctx)
        data = _read_json(path, {})
        if not isinstance(data, dict): data = {}
        data[team] = stage
        _write_json_atomic(path, data)
        return jsonify({"ok": True, "team": team, "stage": stage})

    return bp
