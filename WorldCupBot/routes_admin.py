import os, json, time, glob, sys
from flask import Blueprint, jsonify, request, session, send_file

USER_SESSION_KEY = "wc_user"
ADMIN_IDS_KEY    = "ADMIN_IDS"
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

def _fan_polls_path(base_dir):
    return os.path.join(_json_dir(base_dir), "fan_polls.json")
def _fan_votes_path(base_dir):
    return os.path.join(_json_dir(base_dir), "fan_votes.json")

def _fan_zone_results_path(ctx):
    return _path(ctx, "fan_zone_results.json")

def _players_path(ctx):
    return _path(ctx, "players.json")

def _owners_for_team(ctx, team_name: str):
    team_name = (team_name or "").strip()
    if not team_name:
        return []

    players = _read_json(_players_path(ctx), {})
    out = set()

    if isinstance(players, dict):
        for uid, pdata in players.items():
            if not isinstance(pdata, dict):
                continue
            for entry in (pdata.get("teams") or []):
                if not isinstance(entry, dict):
                    continue
                if (entry.get("team") or "").strip() != team_name:
                    continue

                own = entry.get("ownership") or {}
                main = own.get("main_owner")
                splits = own.get("split_with") or []

                if main is not None:
                    out.add(str(main))
                if isinstance(splits, list):
                    for s in splits:
                        if s is not None:
                            out.add(str(s))

    return sorted(out)

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

    def _fanzone_fixture_id_from_fixture(f: dict) -> str:
        home = str(f.get("home") or "").strip()
        away = str(f.get("away") or "").strip()
        utc  = str(f.get("utc") or "").strip()
        return f"{home}-{away}-{utc}" if (home and away and utc) else ""

    def _find_fixture_any(match_id: str):
        # matches.json is a LIST in your project
        fixtures = _read_json(_path(ctx, "matches.json"), [])
        if not isinstance(fixtures, list):
            fixtures = []

        mid = str(match_id or "").strip()
        if not mid:
            return None

        for f in fixtures:
            if not isinstance(f, dict):
                continue

            fid1 = str(f.get("id") or "").strip()
            fid2 = _fanzone_fixture_id_from_fixture(f)

            if mid == fid1 or mid == fid2:
                return f

        return None


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
        if resp is not None:
            return resp

        data = request.get_json(silent=True) or {}
        sid = data.get("id")
        reason = data.get("reason") or ""
        if not sid:
            return jsonify({"ok": False, "error": "missing id"}), 400

        # 1) pull the pending request
        req_path = _split_requests_path()
        pending_raw = _read_json(req_path, {})
        if not isinstance(pending_raw, dict):
            pending_raw = {}

        entry = pending_raw.pop(sid, None)
        if not isinstance(entry, dict):
            return jsonify({"ok": False, "error": "not_found"}), 404

        # Persist removal of the pending request now
        _write_json_atomic(req_path, pending_raw)

        team = entry.get("team")
        req_id = str(entry.get("requester_id") or "")
        own_id = str(entry.get("main_owner_id") or "")
        if not team or not req_id or not own_id:
            return jsonify({"ok": False, "error": "bad_request"}), 400

        # 2) Apply the split directly in players.json
        players_path = _path(ctx, "players.json")
        players = _read_json(players_path, {})
        if not isinstance(players, dict):
            players = {}

        def ensure_player(uid: str):
            uid = str(uid)
            if uid not in players or not isinstance(players[uid], dict):
                players[uid] = {"display_name": uid, "teams": []}
            players[uid].setdefault("teams", [])
            return players[uid]

        def ensure_team_entry(pdict: dict, team_name: str):
            for t in pdict["teams"]:
                if isinstance(t, dict) and t.get("team") == team_name:
                    t.setdefault("ownership", {})
                    t["ownership"].setdefault("split_with", [])
                    return t
            new_entry = {"team": team_name, "ownership": {"main_owner": None, "split_with": []}}
            pdict["teams"].append(new_entry)
            return new_entry

        # main owner record
        owner = ensure_player(own_id)
        owner_team = ensure_team_entry(owner, team)
        # ensure main_owner remains owner
        owner_team["ownership"]["main_owner"] = int(own_id) if own_id.isdigit() else own_id
        # add requester to split_with (dedup)
        sw = owner_team["ownership"].get("split_with", [])
        req_as_num = int(req_id) if req_id.isdigit() else req_id
        if req_as_num not in sw:
            sw.append(req_as_num)
        owner_team["ownership"]["split_with"] = sw

        # requester record: make sure they have the team entry pointing to main owner
        requester = ensure_player(req_id)
        req_team = ensure_team_entry(requester, team)
        req_team["ownership"]["main_owner"] = int(own_id) if own_id.isdigit() else own_id
        # requester-side split_with usually empty in your schema
        req_team["ownership"].setdefault("split_with", [])

        # save players.json
        _write_json_atomic(players_path, players)

        # 3) Log the action with resolved names
        names = _resolve_names(ctx, {req_id, own_id})
        event = {
            "id": sid,
            "action": "accepted",
            "team": team,
            "requester_id": req_id,
            "main_owner_id": own_id,
            "from_username": names.get(req_id, req_id),
            "to_username": names.get(own_id, own_id),
            "reason": reason,
            "timestamp": _now_iso(),
        }
        _append_split_history(event)

        # optional: still enqueue for bot-side notifications or embeds
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

    # ---------- BETS ----------
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
        if resp is not None: return resp
        data = _read_json(_team_stage_path(ctx), {})
        if not isinstance(data, dict): data = {}
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

    # ---------- Masquerade Mode ----------
    @bp.post("/masquerade/start")
    def admin_masquerade_start():
        resp = require_admin()
        if resp is not None:
            return resp

        data = request.get_json(silent=True) or {}
        target = str(data.get("discord_id") or "").strip()
        if not target:
            return jsonify({"ok": False, "error": "missing discord_id"}), 400

        session["wc_masquerade_id"] = target
        return jsonify({"ok": True, "masquerading_as": target})

    @bp.post("/masquerade/stop")
    def admin_masquerade_stop():
        resp = require_admin()
        if resp is not None:
            return resp

        session.pop("wc_masquerade_id", None)
        return jsonify({"ok": True, "masquerading_as": None})


    # ---------- Fan Zone: declare winner + notify owners ----------
    def _runtime_dir():
        rd = os.path.join(_base_dir(ctx), "runtime")
        os.makedirs(rd, exist_ok=True)
        return rd

    def _fanzone_winners_path():
        return os.path.join(_runtime_dir(), "fan_winners.json")

    def _team_iso_map():
        m = _read_json(_path(ctx, "team_iso.json"), {})
        out = {}
        if isinstance(m, dict):
            for k, v in m.items():
                if not k or not v:
                    continue
                out[str(k).strip().lower()] = str(v).strip().lower()
        return out

    def _owners_for_team(team_name: str):
        players = _read_json(_path(ctx, "players.json"), {})
        owners = set()
        key = (team_name or "").strip().lower()
        if isinstance(players, dict):
            for uid, pdata in players.items():
                if not isinstance(pdata, dict):
                    continue
                for entry in (pdata.get("teams") or []):
                    if not isinstance(entry, dict):
                        continue
                    if str(entry.get("team") or "").strip().lower() != key:
                        continue
                    own = entry.get("ownership") or {}
                    main_owner = own.get("main_owner")
                    split_with = own.get("split_with") or []
                    if main_owner:
                        owners.add(str(main_owner))
                    if isinstance(split_with, list):
                        for sid in split_with:
                            if sid:
                                owners.add(str(sid))
                    elif split_with:
                        owners.add(str(split_with))
        return sorted(owners)

    def _find_fixture(match_id: str):
        matches = _read_json(_path(ctx, "matches.json"), [])
        if not isinstance(matches, list):
            return None
        mid = str(match_id or "").strip()
        for m in matches:
            if isinstance(m, dict) and str(m.get("id") or "").strip() == mid:
                return m
        return None

    @bp.post("/fanzone/declare")
    def fanzone_declare_winner():
        resp = require_admin()
        if resp is not None:
            return resp

        body = request.get_json(silent=True) or {}
        match_id = str(body.get("match_id") or body.get("fixture_id") or "").strip()
        winner = str(body.get("winner") or "").lower().strip()  # home | away | '' (clear)
        winner_team_in = str(body.get("winner_team") or "").strip()

        if not match_id:
            return jsonify({"ok": False, "error": "missing_match_id"}), 400
        if winner not in ("home", "away", ""):
            return jsonify({"ok": False, "error": "invalid_winner"}), 400

        fx = _find_fixture_any(match_id)
        if not fx:
            return jsonify({"ok": False, "error": "fixture_not_found"}), 404

        home = str(fx.get("home") or "").strip()
        away = str(fx.get("away") or "").strip()
        utc  = str(fx.get("utc") or "").strip()
        if not (home and away):
            return jsonify({"ok": False, "error": "fixture_invalid"}), 400

        winners_path = _fanzone_winners_path()
        winners_blob = _read_json(winners_path, {})
        if not isinstance(winners_blob, dict):
            winners_blob = {}

        # Clear winner support
        if winner == "":
            winners_blob.pop(match_id, None)
            _write_json_atomic(winners_path, winners_blob)
            return jsonify({"ok": True, "cleared": True})

        # If winner side missing but winner_team provided, infer side
        if winner not in ("home", "away") and winner_team_in:
            if winner_team_in == home:
                winner = "home"
            elif winner_team_in == away:
                winner = "away"

        if winner not in ("home", "away"):
            return jsonify({"ok": False, "error": "cannot_infer_winner"}), 400

        winner_team = home if winner == "home" else away
        loser_team = away if winner == "home" else home

        iso_map = _team_iso_map()
        winner_iso = iso_map.get(winner_team.lower(), "")
        loser_iso  = iso_map.get(loser_team.lower(), "")

        win_owner_ids = _owners_for_team(winner_team)
        lose_owner_ids = _owners_for_team(loser_team)

        record = {
            "match_id": match_id,
            "home": home,
            "away": away,
            "utc": utc,
            "winner": winner,
            "winner_team": winner_team,
            "loser_team": loser_team,
            "winner_iso": winner_iso,
            "loser_iso": loser_iso,
            "declared_at": _now_iso(),
        }

        winners_blob[match_id] = record
        _write_json_atomic(winners_path, winners_blob)

        cfg = _load_config(ctx)
        channel_name = str(cfg.get("FANZONE_CHANNEL_NAME") or cfg.get("FANZONE_CHANNEL") or "fanzone")

        _enqueue_command(ctx, "fanzone_winner", {
            "match_id": match_id,
            "home": home,
            "away": away,
            "winner_team": winner_team,
            "loser_team": loser_team,
            "winner_owner_ids": win_owner_ids,
            "loser_owner_ids": lose_owner_ids,
            "winner_iso": winner_iso,
            "loser_iso": loser_iso,
            "channel": channel_name
        })

        return jsonify({"ok": True, "fixture": record})

    return bp
