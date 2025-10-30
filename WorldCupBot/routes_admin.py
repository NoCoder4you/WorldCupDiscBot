import os
import sys
import json
import time
import glob
from flask import Blueprint, jsonify, request, session

SESSION_KEY = "wc_admin"

# -----------------------------
# Common helpers
# -----------------------------
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

def _commands_path(ctx):
    rd = os.path.join(_base_dir(ctx), "runtime")
    os.makedirs(rd, exist_ok=True)
    return os.path.join(rd, "bot_commands.jsonl")

def _enqueue_command(ctx, kind, payload=None):
    cmd = {"ts": int(time.time()), "kind": kind, "data": payload or {}}
    with open(_commands_path(ctx), "a", encoding="utf-8") as f:
        f.write(json.dumps(cmd, separators=(",", ":")) + "\n")

def _now_iso():
    import datetime as _dt
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

# -----------------------------
# Auth helpers
# -----------------------------
def _password_from_config(cfg):
    for k in ("PANEL_PASSWORD", "ADMIN_PASSWORD", "ADMIN_PASS", "ADMIN"):
        if cfg.get(k):
            return str(cfg[k])
    return None

def _load_config(ctx):
    return _read_json(_path(ctx, "config.json"), {})

def require_admin():
    if session.get(SESSION_KEY) is True:
        return None
    return jsonify({"ok": False, "error": "Unauthorized"}), 401

# -----------------------------
# Display-name resolution (verified.json first)
# -----------------------------
def _verified_map(ctx):
    """Return dict {discord_id(str): display_name or username} from verified.json."""
    verified = _read_json(_path(ctx, "verified.json"), [])
    out = {}
    if isinstance(verified, list):
        for v in verified:
            if not isinstance(v, dict):
                continue
            did = str(v.get("discord_id") or v.get("id") or v.get("user_id") or "")
            if not did:
                continue
            disp = (v.get("display_name") or v.get("username") or "").strip()
            out[did] = disp or did
    return out

def _resolve_names(ctx, ids):
    m = _verified_map(ctx)
    out = {}
    for i in {str(x) for x in ids if x is not None}:
        out[i] = m.get(i, i)
    return out

# -----------------------------
# Blueprint factory
# -----------------------------
def create_admin_routes(ctx):
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
        resp = require_admin()
        if resp is not None:
            return jsonify({"unlocked": False})
        return jsonify({"unlocked": True})

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

    # ---------- Cogs ----------
    def _scan_cogs():
        results = []
        cdir = os.path.join(_base_dir(ctx), "COGS")
        if not os.path.isdir(cdir):
            return results

        # Try to read bot-side state
        loaded_exts = set()
        try:
            st = _read_json(_path(ctx, "cogs_status.json"), {})
            if isinstance(st, dict) and isinstance(st.get("loaded"), list):
                loaded_exts = set(st["loaded"])
        except Exception:
            pass

        # Fallback to current process if provided
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
            is_loaded = (
                (module_name in loaded_exts) or
                (not loaded_exts and module_name in sysmods)
            )
            results.append({"name": name, "loaded": bool(is_loaded)})
        return results

    @bp.get("/cogs")
    def cogs_list():
        resp = require_admin()
        if resp is not None:
            return resp
        return jsonify({"ok": True, "cogs": _scan_cogs()})

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

    # ---------- Splits (enriched with display_name) ----------
    def _split_requests_path():
        return _path(ctx, "split_requests.json")

    def _split_requests_log_path():
        return _path(ctx, "split_requests_log.json")

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
            rid = str(p.get("requester_id"))
            oid = str(p.get("main_owner_id"))
            p["from_username"] = names.get(rid, rid)
            p["to_username"] = names.get(oid, oid)

        return jsonify({"pending": pending})

    @bp.post("/splits/refresh")
    def splits_refresh():
        resp = require_admin()
        if resp is not None:
            return resp
        _enqueue_command(ctx, "splits_refresh", {})
        return jsonify({"ok": True})

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

        req_path = _split_requests_path()
        pending_raw = _read_json(req_path, {})
        if not isinstance(pending_raw, dict):
            pending_raw = {}

        entry = pending_raw.pop(sid, None)
        if not isinstance(entry, dict):
            return jsonify({"ok": False, "error": "not found"}), 404

        _write_json_atomic(req_path, pending_raw)

        req_id = str(entry.get("requester_id") or "")
        own_id = str(entry.get("main_owner_id") or "")
        names = _resolve_names(ctx, {req_id, own_id})
        event = {
            "id": sid,
            "action": "accepted",
            "team": entry.get("team"),
            "requester_id": req_id,
            "main_owner_id": own_id,
            "from_username": names.get(req_id, req_id),
            "to_username": names.get(own_id, own_id),
            "reason": reason,
            "timestamp": _now_iso(),
        }
        hist_count = _append_split_history(event)

        _enqueue_command(ctx, "split_accept", {"id": sid, "reason": reason})

        return jsonify({
            "ok": True,
            "pending_count": len(pending_raw),
            "history_count": hist_count,
            "event": event
        })

    @bp.post("/splits/decline")
    def splits_decline():
        resp = require_admin()
        if resp is not None:
            return resp

        data = request.get_json(silent=True) or {}
        sid = data.get("id")
        reason = data.get("reason") or ""
        if not sid:
            return jsonify({"ok": False, "error": "missing id"}), 400

        req_path = _split_requests_path()
        pending_raw = _read_json(req_path, {})
        if not isinstance(pending_raw, dict):
            pending_raw = {}

        entry = pending_raw.pop(sid, None)
        if not isinstance(entry, dict):
            return jsonify({"ok": False, "error": "not found"}), 404

        _write_json_atomic(req_path, pending_raw)

        req_id = str(entry.get("requester_id") or "")
        own_id = str(entry.get("main_owner_id") or "")
        names = _resolve_names(ctx, {req_id, own_id})
        event = {
            "id": sid,
            "action": "declined",
            "team": entry.get("team"),
            "requester_id": req_id,
            "main_owner_id": own_id,
            "from_username": names.get(req_id, req_id),
            "to_username": names.get(own_id, own_id),
            "reason": reason,
            "timestamp": _now_iso(),
        }
        hist_count = _append_split_history(event)

        _enqueue_command(ctx, "split_decline", {"id": sid, "reason": reason})

        return jsonify({
            "ok": True,
            "pending_count": len(pending_raw),
            "history_count": hist_count,
            "event": event
        })

    @bp.get("/splits/history")
    def splits_history():
        resp = require_admin()
        if resp is not None:
            return resp

        raw = _read_json(_split_requests_log_path(), [])
        if isinstance(raw, dict) and isinstance(raw.get("events"), list):
            events = raw["events"]
        elif isinstance(raw, list):
            events = raw
        else:
            events = [raw]

        id_bucket = set()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            for k in ("requester_id", "main_owner_id", "from_id", "to_id", "from", "to"):
                if ev.get(k):
                    id_bucket.add(str(ev.get(k)))

        names = _resolve_names(ctx, id_bucket)

        norm = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev_out = dict(ev)
            req_id = str(
                ev.get("requester_id") or ev.get("from_id") or ev.get("from") or ""
            )
            own_id = str(
                ev.get("main_owner_id") or ev.get("to_id") or ev.get("to") or ""
            )
            ev_out["from_username"] = names.get(req_id, req_id)
            ev_out["to_username"] = names.get(own_id, own_id)
            norm.append(ev_out)

        try:
            limit = int(request.args.get("limit", "200"))
        except Exception:
            limit = 200
        norm = norm[-abs(limit):]
        return jsonify({"events": norm})

    # ---------- Bets: declare winner (only updates 'winner') ----------
    def _bets_path():
        return _path(ctx, "bets.json")

    def _enrich_bet_names(b):
        """Return a shallow copy of bet with user_name fields upgraded to display_name."""
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
        """Admin: declare winner for a bet by ID. Only updates 'winner' in JSON; response enriched."""
        resp = require_admin()
        if resp is not None:
            return resp

        data = request.get_json(silent=True) or {}
        winner = str(data.get("winner") or "").lower()
        if winner not in ("option1", "option2", ""):
            return jsonify({"ok": False, "error": "winner must be option1 or option2"}), 400

        bets = _read_json(_bets_path(), [])
        seq = bets if isinstance(bets, list) else bets.get("bets", [])
        found = None
        for b in seq or []:
            if str(b.get("bet_id")) == str(bet_id):
                found = b
                break
        if not found:
            return jsonify({"ok": False, "error": "bet_not_found"}), 404

        # Only change the one field
        found["winner"] = winner or None

        _write_json_atomic(_bets_path(), bets)

        # notify bot to update embed (optional queue)
        _enqueue_command(ctx, "bet_winner_declared", {"bet_id": bet_id, "winner": found["winner"]})

        # return enriched response for admin UI
        return jsonify({"ok": True, "bet": _enrich_bet_names(found)})

    # ---------- Utility: resolve a list of IDs to display names ----------
    @bp.post("/resolve")
    def admin_resolve_ids():
        """Body: { "ids": ["2981...", "..."] } -> { "map": { id: display_name } }"""
        resp = require_admin()
        if resp is not None:
            return resp
        data = request.get_json(silent=True) or {}
        ids = data.get("ids") or []
        m = _resolve_names(ctx, ids)
        return jsonify({"ok": True, "map": m})

    return bp
