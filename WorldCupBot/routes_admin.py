import os, json, time, glob, sys, re, shutil, zipfile, datetime
import requests
from flask import Blueprint, jsonify, request, session, send_file
import logging

from stage_constants import (
    STAGE_ALLOWED,
    STAGE_CHANNEL_MAP,
    normalize_stage,
    stage_rank,
)

USER_SESSION_KEY = "wc_user"
ADMIN_IDS_KEY    = "ADMIN_IDS"
MAX_BACKUPS = 25
AUTO_BACKUP_DEFAULT_HOURS = 6.0

# ---- PATH / IO HELPERS ----
def _base_dir(ctx):
    return ctx.get("BASE_DIR", os.getcwd())

def _json_dir(ctx):
    return os.path.join(_base_dir(ctx), "JSON")

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path

def _backup_dir(base_dir):
    return _ensure_dir(os.path.join(base_dir, "BACKUPS"))

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

def _unique_backup_path(bdir: str, timestamp: str) -> tuple[str, str]:
    base_name = f"{timestamp}.zip"
    base_path = os.path.join(bdir, base_name)
    if not os.path.exists(base_path):
        return base_name, base_path
    suffix = 1
    while True:
        candidate_name = f"{timestamp}_{suffix:02d}.zip"
        candidate_path = os.path.join(bdir, candidate_name)
        if not os.path.exists(candidate_path):
            return candidate_name, candidate_path
        suffix += 1

def _cleanup_old_backups(base_dir: str):
    bdir = _backup_dir(base_dir)
    backups = sorted(
        [
            os.path.join(bdir, name)
            for name in os.listdir(bdir)
            if name.endswith(".zip") and os.path.isfile(os.path.join(bdir, name))
        ],
        key=os.path.getmtime,
    )
    if len(backups) <= MAX_BACKUPS:
        return
    for path in backups[:-MAX_BACKUPS]:
        try:
            os.remove(path)
        except OSError:
            log.warning("Failed to remove old backup: %s", path)

def _create_backup(base_dir):
    bdir = _backup_dir(base_dir)
    jdir = os.path.join(base_dir, "JSON")
    ts = datetime.datetime.now().strftime("%d-%m_%H-%M-%S")
    outname, outpath = _unique_backup_path(bdir, ts)
    with zipfile.ZipFile(outpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if os.path.isdir(jdir):
            for root, _, files in os.walk(jdir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arc = os.path.relpath(fp, jdir)
                    z.write(fp, arcname=arc)
    _cleanup_old_backups(base_dir)
    return outname

def _backup_request_context() -> dict:
    """Return safe request metadata to trace backup calls without exposing tokens."""
    return {
        "remote_addr": request.remote_addr,
        "forwarded_for": request.headers.get("X-Forwarded-For", ""),
        "user_agent": request.headers.get("User-Agent", ""),
    }

def _restore_backup(base_dir, name):
    bdir = _backup_dir(base_dir)
    jdir = os.path.join(base_dir, "JSON")
    src = os.path.join(bdir, name)
    if not (os.path.isfile(src) and src.endswith(".zip")):
        raise FileNotFoundError("Backup not found")
    if os.path.isdir(jdir):
        shutil.copytree(jdir, jdir + ".bak.restore", dirs_exist_ok=True)
    with zipfile.ZipFile(src, "r") as z:
        _ensure_dir(jdir)
        z.extractall(jdir)
    return True

def _notification_settings_path(ctx):
    return _path(ctx, "notification_settings.json")

NOTIFICATION_CATEGORIES = (
    "splits",
    "matches",
    "bets",
    "stages",
)

def _players_path(ctx):
    return _path(ctx, "players.json")

def _fanzone_votes_path(ctx):
    return os.path.join(_json_dir(ctx), "fan_votes.json")
def _bracket_slots_path(ctx):
    return _path(ctx, "bracket_slots.json")

def _owners_for_team(ctx, team_name: str):
    team_name = (team_name or "").strip().lower()
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
                entry_team = (entry.get("team") or "").strip().lower()
                if entry_team != team_name:
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

def _load_notification_settings(ctx):
    data = _read_json(_notification_settings_path(ctx), {})
    return data if isinstance(data, dict) else {}

def _default_notification_categories() -> dict:
    return {key: True for key in NOTIFICATION_CATEGORIES}

def _notification_record(ctx, uid: str) -> dict:
    settings = _load_notification_settings(ctx)
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

def _notification_preference(ctx, uid: str) -> str:
    return _notification_record(ctx, uid).get("channel") or ""

def _prefers_bell(ctx, uid: str) -> bool:
    return _notification_preference(ctx, uid) in ("", "bell")

def _prefers_dms(ctx, uid: str) -> bool:
    return _notification_preference(ctx, uid) in ("", "dms")

def _category_enabled(ctx, uid: str, category: str) -> bool:
    return bool(_notification_record(ctx, uid).get("categories", {}).get(category, True))

def _filter_notification_ids(ctx, ids: list[str], channel: str, category: str) -> list[str]:
    if not ids:
        return []
    settings = _load_notification_settings(ctx)
    out = []
    for uid in ids:
        suid = str(uid or "").strip()
        if not suid:
            continue
        pref_record = settings.get(suid)
        if isinstance(pref_record, str):
            pref_record = {"channel": pref_record}
        if not isinstance(pref_record, dict):
            pref_record = {}
        pref = str(pref_record.get("channel") or "").strip().lower()
        categories = _default_notification_categories()
        if isinstance(pref_record.get("categories"), dict):
            for key in NOTIFICATION_CATEGORIES:
                if key in pref_record["categories"]:
                    categories[key] = bool(pref_record["categories"].get(key))
        if not categories.get(category, True):
            continue
        if channel == "bell" and pref in ("", "bell"):
            out.append(suid)
        elif channel == "dms" and pref in ("", "dms"):
            out.append(suid)
    return out

def _filter_notification_voters(ctx, voters: dict, category: str) -> dict:
    if not isinstance(voters, dict) or not voters:
        return {}
    settings = _load_notification_settings(ctx)
    out = {}
    for uid, choice in voters.items():
        suid = str(uid or "").strip()
        if not suid:
            continue
        pref_record = settings.get(suid)
        if isinstance(pref_record, str):
            pref_record = {"channel": pref_record}
        if not isinstance(pref_record, dict):
            pref_record = {}
        pref = str(pref_record.get("channel") or "").strip().lower()
        categories = _default_notification_categories()
        if isinstance(pref_record.get("categories"), dict):
            for key in NOTIFICATION_CATEGORIES:
                if key in pref_record["categories"]:
                    categories[key] = bool(pref_record["categories"].get(key))
        if not categories.get(category, True):
            continue
        if pref in ("", "bell"):
            out[suid] = choice
    return out

def _now_iso():
    import datetime as _dt
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _matches_path(ctx):
    return _path(ctx, "matches.json")

def _commands_path(ctx):
    rd = _ensure_dir(_json_dir(ctx))
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

def _settings_path(ctx):
    return os.path.join(_json_dir(ctx), "admin_settings.json")

def _load_settings(ctx):
    try:
        path = _settings_path(ctx)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

def _coerce_auto_backup_interval(value, default=AUTO_BACKUP_DEFAULT_HOURS) -> float:
    """Parse and clamp the auto-backup interval to a safe positive float."""
    try:
        interval = float(value)
    except (TypeError, ValueError):
        return default
    if interval <= 0:
        return default
    return max(0.1, round(interval, 2))

def _update_auto_backup_timestamp(ctx, ts: int) -> None:
    """Persist the last backup timestamp for UI reporting."""
    settings = _load_settings(ctx)
    settings["AUTO_BACKUP_LAST_TS"] = int(ts)
    _save_settings(ctx, settings)

def _auto_backup_if_due(ctx) -> str | None:
    """Create an automatic backup when the configured interval elapses."""
    if not _is_admin(ctx):
        return None
    settings = _load_settings(ctx)
    if not bool(settings.get("AUTO_BACKUP_ENABLED")):
        return None
    interval_hours = _coerce_auto_backup_interval(settings.get("AUTO_BACKUP_INTERVAL_HOURS"))
    last_ts = int(settings.get("AUTO_BACKUP_LAST_TS") or 0)
    now = int(time.time())
    if last_ts and (now - last_ts) < int(interval_hours * 3600):
        return None
    name = _create_backup(ctx.get("BASE_DIR", ""))
    settings["AUTO_BACKUP_LAST_TS"] = now
    _save_settings(ctx, settings)
    log.info("Auto backup created (name=%s interval_hours=%.2f)", name, interval_hours)
    return name

def _guilds_path(ctx):
    return _path(ctx, "guilds.json")

def _load_primary_guild_id(ctx) -> str:
    settings = _load_settings(ctx)
    selected = str(settings.get("SELECTED_GUILD_ID") or "").strip()
    if selected:
        return selected
    cfg = _load_config(ctx)
    for key in ("DISCORD_GUILD_ID", "GUILD_ID", "PRIMARY_GUILD_ID", "ADMIN_GUILD_ID"):
        raw = str(cfg.get(key) or "").strip()
        if raw:
            return raw
    data = _read_json(_guilds_path(ctx), {})
    if isinstance(data, dict):
        guilds = data.get("guilds") or []
        if isinstance(guilds, list):
            for g in guilds:
                if isinstance(g, dict):
                    gid = str(g.get("id") or "").strip()
                    if gid:
                        return gid
    return ""

def _is_divider_channel(name: str) -> bool:
    raw = str(name or "").strip()
    if not raw:
        return False
    return all(ch == "_" for ch in raw)

def _save_settings(ctx, data: dict) -> bool:
    path = _settings_path(ctx)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False

def _current_user():
    u = session.get(USER_SESSION_KEY) or None
    if isinstance(u, dict) and u.get("discord_id"):
        return u
    return None

def _effective_uid(ctx):
    user = session.get(USER_SESSION_KEY)
    if not user:
        return None

    real_id = str(user.get("discord_id") or "")
    masquerade_id = session.get("wc_masquerade_id")

    cfg = _load_config(ctx)
    admin_ids = {str(x) for x in (cfg.get("ADMIN_IDS") or [])}
    if masquerade_id and real_id in admin_ids:
        return str(masquerade_id)
    return real_id

def _user_label():
    u = _current_user()
    if not u:
        return "unknown"
    uname = u.get("username") or u.get("global_name") or "unknown"
    return f"{uname} ({u.get('discord_id')})"

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
    bp = Blueprint("admin", __name__)

    # ---------- Auth endpoints (Discord-session based) ----------
    @bp.get("/admin/auth/status")
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

    @bp.get("/api/backups")
    def backups_list():
        base = ctx.get("BASE_DIR", "")
        # Auto backups are triggered opportunistically when admins view the backups page.
        _auto_backup_if_due(ctx)
        files = _list_backups(base)
        folders = [{
            "display": "JSON snapshots",
            "count": len(files),
            "files": [{"name": f["name"], "bytes": f["size"], "mtime": f["ts"], "rel": f["rel"]} for f in files],
        }]
        return jsonify({
            "folders": folders,
            "backups": files,
        })

    @bp.get("/api/backups/download")
    def backups_download():
        base = ctx.get("BASE_DIR", "")
        rel = request.args.get("rel", "")
        if not rel:
            return jsonify({"ok": False, "error": "missing rel"}), 400
        fp = os.path.join(_backup_dir(base), rel)
        if not os.path.isfile(fp):
            return jsonify({"ok": False, "error": "not found"}), 404
        return send_file(fp, as_attachment=True, download_name=os.path.basename(fp))

    @bp.post("/api/backups/create")
    def backups_create():
        base = ctx.get("BASE_DIR", "")
        name = _create_backup(base)
        _update_auto_backup_timestamp(ctx, int(time.time()))
        user = session.get(USER_SESSION_KEY) or {}
        # Trace backup creation to identify startup callers triggering this endpoint.
        trace_ctx = _backup_request_context()
        log.info(
            "Backup created via API (name=%s discord_id=%s username=%s remote_addr=%s forwarded_for=%s user_agent=%s)",
            name,
            _effective_uid(ctx) or user.get("discord_id") or "anonymous",
            user.get("username") or "unknown",
            trace_ctx.get("remote_addr"),
            trace_ctx.get("forwarded_for"),
            trace_ctx.get("user_agent"),
        )
        return jsonify({"ok": True, "created": name})

    @bp.post("/api/backups/restore")
    def backups_restore():
        base = ctx.get("BASE_DIR", "")
        body = request.get_json(silent=True) or {}
        name = body.get("name", "")
        try:
            _restore_backup(base, name)
        except FileNotFoundError:
            return jsonify({"ok": False, "error": "backup not found"}), 404
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        user = session.get(USER_SESSION_KEY) or {}
        log.info(
            "Backup restored via API (name=%s discord_id=%s username=%s)",
            name,
            _effective_uid(ctx) or user.get("discord_id") or "anonymous",
            user.get("username") or "unknown",
        )
        return jsonify({"ok": True, "restored": name})

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

    @bp.get("/admin/bot/status")
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

    @bp.post("/admin/bot/start")
    def bot_start():
        resp = require_admin()
        if resp is not None: return resp
        ok = _run_or_queue("start")
        log.info("Bot start requested by %s (ok=%s)", _user_label(), ok)
        return jsonify({"ok": ok, "action": "start"})

    @bp.post("/admin/bot/stop")
    def bot_stop():
        resp = require_admin()
        if resp is not None: return resp
        ok = _run_or_queue("stop")
        log.info("Bot stop requested by %s (ok=%s)", _user_label(), ok)
        return jsonify({"ok": ok, "action": "stop"})

    @bp.post("/admin/bot/restart")
    def bot_restart():
        resp = require_admin()
        if resp is not None: return resp
        ok = _run_or_queue("restart")
        log.info("Bot restart requested by %s (ok=%s)", _user_label(), ok)
        return jsonify({"ok": ok, "action": "restart"})

    # ---------- Ownership (reassign) ----------
    @bp.post("/admin/ownership/reassign")
    def ownership_reassign():
        resp = require_admin()
        if resp is not None: return resp

        data = request.get_json(silent=True) or {}
        team = (data.get("team") or "").strip()
        new_owner_id = str(data.get("new_owner_id") or "").strip()
        if not team or not new_owner_id:
            return jsonify({"ok": False, "error": "missing team or new_owner_id"}), 400
        log.info("Ownership reassignment requested by %s (team=%s new_owner_id=%s)", _user_label(), team, new_owner_id)

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

    @bp.get("/admin/cogs")
    def cogs_list():
        resp = require_admin()
        if resp is not None: return resp
        return jsonify({"ok": True, "cogs": _scan_cogs()})

    def _enqueue_cog(cog, action):
        _enqueue_command(ctx, f"cog_{action}", {"name": cog})
        log.info("Cog %s requested by %s (cog=%s)", action, _user_label(), cog)

    @bp.post("/admin/cogs/<cog>/load")
    def cogs_load(cog):
        resp = require_admin()
        if resp is not None: return resp
        _enqueue_cog(cog, "load")
        return jsonify({"ok": True})

    @bp.post("/admin/cogs/<cog>/unload")
    def cogs_unload(cog):
        resp = require_admin()
        if resp is not None: return resp
        _enqueue_cog(cog, "unload")
        return jsonify({"ok": True})

    @bp.post("/admin/cogs/<cog>/reload")
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

    @bp.get("/admin/splits")
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

    @bp.post("/admin/splits/accept")
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
        log.info("Split accepted by %s (team=%s requester_id=%s main_owner_id=%s reason=%s)", _user_label(), team, req_id, own_id, reason)

        return jsonify({"ok": True, "event": event})

    @bp.post("/admin/splits/decline")
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
        log.info("Split declined by %s (team=%s requester_id=%s main_owner_id=%s reason=%s)", _user_label(), entry.get("team"), req_id, own_id, reason)
        return jsonify({"ok": True, "event": event})

    @bp.get("/admin/splits/history")
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

    def _append_bet_results(bet: dict):
        winner = str((bet or {}).get("winner") or "").strip().lower()
        if winner not in ("option1", "option2"):
            return
        bet_id = str((bet or {}).get("bet_id") or "").strip()
        if not bet_id:
            return
        opt1_id = str((bet or {}).get("option1_user_id") or "").strip()
        opt2_id = str((bet or {}).get("option2_user_id") or "").strip()
        if not (opt1_id or opt2_id):
            return

        path = _path(ctx, "bet_results.json")
        data = _read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        events = data.get("events")
        if not isinstance(events, list):
            events = []

        existing = {str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id")}
        now = int(time.time())

        bet_title = str((bet or {}).get("bet_title") or f"Bet {bet_id}")
        wager = str((bet or {}).get("wager") or "-")

        def add_event(uid: str, result: str):
            if not uid:
                return
            if not _prefers_bell(ctx, uid) or not _category_enabled(ctx, uid, "bets"):
                return
            eid = f"bet:{bet_id}:{uid}"
            if eid in existing:
                return
            outcome = "Status: 🏆 Won 🏆" if result == "win" else "Lost"
            events.append({
                "id": eid,
                "discord_id": uid,
                "result": result,
                "title": "Bet settled",
                "body": f"Bet: {bet_title}\nWager: {wager}\nStatus: {outcome}",
                "bet_id": bet_id,
                "bet_title": bet_title,
                "wager": wager,
                "ts": now
            })
            existing.add(eid)

        def purge_existing(uid: str):
            if not uid:
                return
            prefix = f"bet:{bet_id}:{uid}"
            kept = []
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                if str(ev.get("id") or "") == prefix:
                    continue
                kept.append(ev)
            events[:] = kept
            existing.discard(prefix)

        if winner == "option1":
            purge_existing(opt1_id)
            purge_existing(opt2_id)
            add_event(opt1_id, "win")
            add_event(opt2_id, "lose")
        elif winner == "option2":
            purge_existing(opt1_id)
            purge_existing(opt2_id)
            add_event(opt1_id, "lose")
            add_event(opt2_id, "win")

        events.sort(key=lambda x: int((x or {}).get("ts") or 0), reverse=True)
        data["events"] = events[:500]
        _write_json_atomic(path, data)

    @bp.post("/admin/bets/<bet_id>/winner")
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

        log.info(
            "Bet settlement requested by %s (bet_id=%s winner=%s)",
            _user_label(),
            bet_id,
            winner or "clear",
        )
        found["winner"] = winner or None
        _write_json_atomic(_bets_path(), bets)
        _enqueue_command(ctx, "bet_winner_declared", {"bet_id": bet_id, "winner": found["winner"]})
        _append_bet_results(found)
        log.info("Bet winner declared by %s (bet_id=%s winner=%s)", _user_label(), bet_id, found["winner"])
        return jsonify({"ok": True, "bet": _enrich_bet_names(found)})

    # ---------- LOGS ----------
    @bp.get("/admin/log/<kind>")
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

    @bp.post("/admin/log/<kind>/clear")
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

    @bp.get("/admin/log/<kind>/download")
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

    def _team_stage_notifications_path(ctx):
        return os.path.join(_json_dir(ctx), "team_stage_notifications.json")

    def _stage_notification_body(team: str, stage: str) -> str:
        stage_norm = normalize_stage(stage)
        if stage_norm == "Eliminated":
            return f"{team} was eliminated."
        return f"{team} advanced to {stage_norm}."

    def _append_stage_notifications(discord_ids: list[str], team: str, stage: str, ts: int):
        if not discord_ids:
            return
        team = str(team or "").strip()
        stage = str(stage or "").strip()
        if not team or not stage:
            return
        body = _stage_notification_body(team, stage)

        path = _team_stage_notifications_path(ctx)
        data = _read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        events = data.get("events")
        if not isinstance(events, list):
            events = []

        existing = {str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id")}

        for uid in discord_ids:
            suid = str(uid or "").strip()
            if not suid:
                continue
            eid = f"stage:{team}:{stage}:{suid}"
            if eid in existing:
                continue
            events.append({
                "id": eid,
                "discord_id": suid,
                "team": team,
                "stage": stage,
                "title": "Stage update",
                "body": body,
                "ts": ts
            })
            existing.add(eid)

        events.sort(key=lambda x: int((x or {}).get("ts") or 0), reverse=True)
        data["events"] = events[:500]
        _write_json_atomic(path, data)

    @bp.get("/admin/teams/stage")
    def admin_team_stage_get():
        resp = require_admin()
        if resp is not None: return resp
        data = _read_json(_team_stage_path(ctx), {})
        if not isinstance(data, dict): data = {}
        return jsonify({"ok": True, "stages": data})

    @bp.post("/admin/teams/stage")
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
        prev_stage = data.get(team) or ""
        prev_stage_norm = normalize_stage(prev_stage) or "Group Stage"
        next_stage_norm = normalize_stage(stage)
        data[team] = stage
        _write_json_atomic(path, data)
        log.info(
            "Team stage updated by %s (team=%s stage=%s previous_stage=%s)",
            _user_label(),
            team,
            stage,
            prev_stage,
        )

        prev_rank = stage_rank(prev_stage_norm)
        next_rank = stage_rank(next_stage_norm)
        progressed = next_rank > prev_rank >= 0
        eliminated = next_stage_norm == "Eliminated" and prev_stage_norm != "Eliminated"

        if progressed or eliminated:
            owner_ids = _owners_for_team(ctx, team)
            now = int(time.time())
            bell_owner_ids = _filter_notification_ids(ctx, owner_ids, "bell", "stages")
            dm_owner_ids = _filter_notification_ids(ctx, owner_ids, "dms", "stages")
            _append_stage_notifications(bell_owner_ids, team, next_stage_norm, now)

            settings = _load_settings(ctx)
            channel_name = str(settings.get("STAGE_ANNOUNCE_CHANNEL") or "announcements")

            _enqueue_command(ctx, "team_stage_progress", {
                "team": team,
                "stage": next_stage_norm,
                "previous_stage": prev_stage_norm,
                "owner_ids": dm_owner_ids,
                "channel": channel_name,
            })
        return jsonify({"ok": True, "team": team, "stage": stage})

    # ---------- Masquerade Mode ----------
    @bp.post("/admin/masquerade/start")
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

    @bp.post("/admin/masquerade/stop")
    def admin_masquerade_stop():
        resp = require_admin()
        if resp is not None:
            return resp

        session.pop("wc_masquerade_id", None)
        return jsonify({"ok": True, "masquerading_as": None})

    # ---------- Settings ----------
    @bp.get("/admin/settings")
    def admin_settings_get():
        resp = require_admin()
        if resp is not None:
            return resp
        cfg = _load_settings(ctx)
        return jsonify({
            "ok": True,
            "stage_announce_channel": str(cfg.get("STAGE_ANNOUNCE_CHANNEL") or "").strip(),
            "selected_guild_id": str(cfg.get("SELECTED_GUILD_ID") or "").strip(),
            "primary_guild_id": _load_primary_guild_id(ctx),
            "maintenance_mode": bool(cfg.get("MAINTENANCE_MODE")),
            "auto_backup_enabled": bool(cfg.get("AUTO_BACKUP_ENABLED")),
            "auto_backup_interval_hours": _coerce_auto_backup_interval(
                cfg.get("AUTO_BACKUP_INTERVAL_HOURS"),
                AUTO_BACKUP_DEFAULT_HOURS,
            ),
            "auto_backup_last_ts": int(cfg.get("AUTO_BACKUP_LAST_TS") or 0),
        })

    @bp.post("/admin/settings")
    def admin_settings_set():
        resp = require_admin()
        if resp is not None:
            return resp
        body = request.get_json(silent=True) or {}
        maintenance_raw = body.get("maintenance_mode", None)
        auto_backup_enabled = body.get("auto_backup_enabled", None)
        auto_backup_interval = body.get("auto_backup_interval_hours", None)

        cfg = _load_settings(ctx)
        prev_maintenance = bool(cfg.get("MAINTENANCE_MODE"))
        if "stage_announce_channel" in body:
            channel = str(body.get("stage_announce_channel") or "").strip()
            cfg["STAGE_ANNOUNCE_CHANNEL"] = channel
        if "selected_guild_id" in body:
            selected_guild_id = str(body.get("selected_guild_id") or "").strip()
            if selected_guild_id:
                cfg["SELECTED_GUILD_ID"] = selected_guild_id
            else:
                cfg.pop("SELECTED_GUILD_ID", None)
        if maintenance_raw is not None:
            cfg["MAINTENANCE_MODE"] = bool(maintenance_raw)
        if auto_backup_enabled is not None:
            cfg["AUTO_BACKUP_ENABLED"] = bool(auto_backup_enabled)
            # Start the interval clock when auto backups are first enabled.
            if cfg["AUTO_BACKUP_ENABLED"] and not cfg.get("AUTO_BACKUP_LAST_TS"):
                cfg["AUTO_BACKUP_LAST_TS"] = int(time.time())
        if auto_backup_interval is not None:
            cfg["AUTO_BACKUP_INTERVAL_HOURS"] = _coerce_auto_backup_interval(auto_backup_interval)
        if not _save_settings(ctx, cfg):
            return jsonify({"ok": False, "error": "failed_to_save"}), 500
        if maintenance_raw is not None:
            next_maintenance = bool(cfg.get("MAINTENANCE_MODE"))
            if next_maintenance != prev_maintenance:
                log.info(
                    "Maintenance mode updated by %s (enabled=%s)",
                    _user_label(),
                    next_maintenance,
                )
                if next_maintenance:
                    # Broadcast the maintenance state change so Discord members
                    # immediately understand why the web app is unavailable.
                    _enqueue_command(ctx, "maintenance_mode_enabled", {
                        "channel": "announcements",
                        "message": (
                            "🚧 **Maintenance Mode Enabled**\n"
                            "The World Cup site is temporarily unavailable while "
                            "we perform maintenance. We will post another update "
                            "here as soon as normal access is restored."
                        ),
                    })
        return jsonify({
            "ok": True,
            "stage_announce_channel": str(cfg.get("STAGE_ANNOUNCE_CHANNEL") or "").strip(),
            "selected_guild_id": str(cfg.get("SELECTED_GUILD_ID") or "").strip(),
            "maintenance_mode": bool(cfg.get("MAINTENANCE_MODE")),
            "auto_backup_enabled": bool(cfg.get("AUTO_BACKUP_ENABLED")),
            "auto_backup_interval_hours": _coerce_auto_backup_interval(
                cfg.get("AUTO_BACKUP_INTERVAL_HOURS"),
                AUTO_BACKUP_DEFAULT_HOURS,
            ),
            "auto_backup_last_ts": int(cfg.get("AUTO_BACKUP_LAST_TS") or 0),
        })

    def _load_matches_payload():
        raw = _read_json(_matches_path(ctx), [])
        if isinstance(raw, dict):
            if isinstance(raw.get("fixtures"), list):
                return raw, raw.get("fixtures"), "fixtures"
            if isinstance(raw.get("matches"), list):
                return raw, raw.get("matches"), "matches"
            return raw, [], ""
        if isinstance(raw, list):
            return None, raw, ""
        return None, [], ""

    def _valid_utc(utc: str) -> bool:
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", utc or ""))

    @bp.get("/admin/fixtures")
    def admin_fixtures_get():
        resp = require_admin()
        if resp is not None:
            return resp

        _, fixtures, _ = _load_matches_payload()
        out = []
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            fid = str(fixture.get("id") or "").strip()
            home = str(fixture.get("home") or "").strip()
            away = str(fixture.get("away") or "").strip()
            utc = str(fixture.get("utc") or fixture.get("time") or "").strip()
            if not fid:
                continue
            out.append({
                "id": fid,
                "home": home,
                "away": away,
                "utc": utc,
            })
        return jsonify({"ok": True, "fixtures": out})

    @bp.post("/admin/fixtures")
    def admin_fixtures_set():
        resp = require_admin()
        if resp is not None:
            return resp

        body = request.get_json(silent=True) or {}
        match_id = str(body.get("id") or body.get("match_id") or "").strip()
        utc = str(body.get("utc") or "").strip()
        if not match_id or not utc:
            return jsonify({"ok": False, "error": "missing_match_id_or_time"}), 400
        if not _valid_utc(utc):
            return jsonify({"ok": False, "error": "invalid_utc"}), 400

        container, fixtures, key = _load_matches_payload()
        updated = False
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            fid = str(fixture.get("id") or fixture.get("fixture_id") or "").strip()
            if fid != match_id:
                continue
            fixture["utc"] = utc
            if "time" in fixture:
                fixture["time"] = utc
            updated = True
            break

        if not updated:
            return jsonify({"ok": False, "error": "match_not_found"}), 404

        if container is None:
            _write_json_atomic(_matches_path(ctx), fixtures)
        else:
            if key:
                container[key] = fixtures
            _write_json_atomic(_matches_path(ctx), container)
        return jsonify({"ok": True, "id": match_id, "utc": utc})

    @bp.post("/admin/fixtures/slot")
    def admin_fixture_slot_set():
        resp = require_admin()
        if resp is not None:
            return resp

        body = request.get_json(silent=True) or {}
        match_id = str(body.get("id") or body.get("match_id") or "").strip()
        slot_raw = body.get("bracket_slot") if "bracket_slot" in body else body.get("slot")

        if not match_id:
            return jsonify({"ok": False, "error": "missing_match_id"}), 400

        slot_val = None
        if slot_raw is not None and str(slot_raw).strip() != "":
            try:
                slot_val = int(str(slot_raw).strip())
            except Exception:
                return jsonify({"ok": False, "error": "invalid_slot"}), 400

        container, fixtures, key = _load_matches_payload()
        updated = False
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            fid = str(fixture.get("id") or fixture.get("fixture_id") or "").strip()
            if fid != match_id:
                continue
            if slot_val is None:
                fixture.pop("bracket_slot", None)
            else:
                fixture["bracket_slot"] = slot_val
            updated = True
            break

        if not updated:
            return jsonify({"ok": False, "error": "match_not_found"}), 404

        if container is None:
            _write_json_atomic(_matches_path(ctx), fixtures)
        else:
            if key:
                container[key] = fixtures
            _write_json_atomic(_matches_path(ctx), container)
        return jsonify({"ok": True, "id": match_id, "bracket_slot": slot_val})

    @bp.post("/admin/bracket_slots")
    def admin_bracket_slots_set():
        resp = require_admin()
        if resp is not None:
            return resp

        body = request.get_json(silent=True) or {}
        stage_raw = str(body.get("stage") or "").strip()
        stage = normalize_stage(stage_raw)
        if stage not in STAGE_ALLOWED:
            return jsonify({"ok": False, "error": "invalid_stage"}), 400

        slot_limits = {
            "Round of 32": 8,
            "Round of 16": 4,
            "Quarter-finals": 2,
            "Semi-finals": 1,
            "Final": 1,
            "Third Place Play-off": 1,
        }

        slot_raw = body.get("slot") if "slot" in body else body.get("bracket_slot")
        try:
            slot_val = int(str(slot_raw).strip())
        except Exception:
            return jsonify({"ok": False, "error": "invalid_slot"}), 400
        max_slot = slot_limits.get(stage)
        if max_slot and (slot_val < 1 or slot_val > max_slot):
            return jsonify({"ok": False, "error": "slot_out_of_range"}), 400

        side_raw = str(body.get("side") or "").strip().lower()
        if stage in ("Final", "Third Place Play-off"):
            side = "center"
        else:
            side = side_raw if side_raw in ("left", "right") else ""
        if stage not in ("Final", "Third Place Play-off") and not side:
            return jsonify({"ok": False, "error": "invalid_side"}), 400

        label = str(body.get("label") or "").strip()
        home = str(body.get("home") or body.get("country_a") or "").strip()
        away = str(body.get("away") or body.get("country_b") or "").strip()
        match_id = str(body.get("match_id") or body.get("matchId") or "").strip()
        utc = str(body.get("utc") or body.get("time") or "").strip()

        slots = _read_json(_bracket_slots_path(ctx), {})
        if not isinstance(slots, dict):
            slots = {}
        stage_slots = slots.get(stage)
        if not isinstance(stage_slots, dict):
            stage_slots = {}
        side_key = side or "center"
        side_slots = stage_slots.get(side_key)
        if not isinstance(side_slots, dict):
            side_slots = {}

        if not home and not away and not match_id and not label:
            side_slots.pop(str(slot_val), None)
        else:
            side_slots[str(slot_val)] = {
                "label": label,
                "match_id": match_id,
                "home": home,
                "away": away,
                "utc": utc,
            }

        if side_slots:
            stage_slots[side_key] = side_slots
        else:
            stage_slots.pop(side_key, None)

        if stage_slots:
            slots[stage] = stage_slots
        else:
            slots.pop(stage, None)

        _write_json_atomic(_bracket_slots_path(ctx), slots)

        if match_id:
            container, fixtures, key = _load_matches_payload()
            updated = False
            for fixture in fixtures:
                if not isinstance(fixture, dict):
                    continue
                fid = str(fixture.get("id") or fixture.get("fixture_id") or "").strip()
                if fid != match_id:
                    continue
                fixture["bracket_slot"] = slot_val
                if home:
                    fixture["home"] = home
                if away:
                    fixture["away"] = away
                if utc:
                    fixture["utc"] = utc
                    fixture["time"] = utc
                updated = True
                break
            if not updated:
                if not home and not away and label:
                    if " vs " in label.lower():
                        parts = re.split(r"\s+vs\s+", label, flags=re.IGNORECASE)
                        home = parts[0].strip() if parts else "TBD"
                        away = parts[1].strip() if len(parts) > 1 else "TBD"
                    else:
                        home = label
                        away = "TBD"
                if not home:
                    home = "TBD"
                if not away:
                    away = "TBD"
                fixtures.append({
                    "id": match_id,
                    "home": home or "TBD",
                    "away": away or "TBD",
                    "utc": "",
                    "stadium": "",
                    "group": "",
                    "stage": stage,
                    "bracket_slot": slot_val,
                    "utc": utc,
                })
                updated = True
            if updated:
                if container is None:
                    _write_json_atomic(_matches_path(ctx), fixtures)
                else:
                    if key:
                        container[key] = fixtures
                    _write_json_atomic(_matches_path(ctx), container)

        return jsonify({"ok": True, "stage": stage, "slot": slot_val})

    @bp.get("/admin/discord/channels")
    def admin_discord_channels():
        resp = require_admin()
        if resp is not None:
            return resp
        cfg = _load_config(ctx)
        token = str(cfg.get("DISCORD_BOT_TOKEN") or cfg.get("BOT_TOKEN") or "").strip()
        requested_guild_id = str(request.args.get("guild_id") or "").strip()
        guild_id = requested_guild_id or _load_primary_guild_id(ctx)
        if not token:
            return jsonify({"ok": False, "error": "missing_bot_token"}), 500
        if not guild_id:
            return jsonify({"ok": False, "error": "missing_guild_id"}), 500

        url = f"https://discord.com/api/v10/guilds/{guild_id}/channels"
        try:
            resp = requests.get(url, headers={"Authorization": f"Bot {token}"}, timeout=10)
        except requests.RequestException as exc:
            return jsonify({"ok": False, "error": "discord_request_failed", "detail": str(exc)}), 502
        if resp.status_code >= 300:
            detail = resp.text.strip() if resp.text else ""
            return jsonify({
                "ok": False,
                "error": f"discord_error ({resp.status_code})",
                "status": resp.status_code,
                "detail": detail[:200],
            }), 502
        payload = resp.json() if resp.content else []
        if not isinstance(payload, list):
            payload = []

        categories = {}
        category_positions = {}
        for ch in payload:
            if not isinstance(ch, dict):
                continue
            if ch.get("type") == 4:
                cid = str(ch.get("id") or "")
                categories[cid] = str(ch.get("name") or "")
                category_positions[cid] = int(ch.get("position") or 0)

        rows = []
        for ch in payload:
            if not isinstance(ch, dict):
                continue
            ctype = ch.get("type")
            if ctype == 4:
                continue
            if ctype in (2, 13):
                continue
            name = str(ch.get("name") or "").strip()
            if not name or _is_divider_channel(name):
                continue
            parent_id = str(ch.get("parent_id") or "").strip()
            category_name = categories.get(parent_id, "")
            rows.append({
                "category": category_name,
                "channel": name,
                "id": str(ch.get("id") or "").strip(),
                "category_position": category_positions.get(parent_id, 1_000_000),
                "channel_position": int(ch.get("position") or 0),
            })

        rows.sort(key=lambda item: (
            item.get("category_position", 1_000_000),
            item.get("channel_position", 0),
            (item.get("category") or "").lower(),
            (item.get("channel") or "").lower(),
        ))
        cleaned = [{"category": r["category"], "channel": r["channel"], "id": r.get("id") or ""} for r in rows]
        return jsonify({"ok": True, "channels": cleaned})

    @bp.get("/admin/discord/guilds")
    def admin_discord_guilds():
        resp = require_admin()
        if resp is not None:
            return resp
        cfg = _load_config(ctx)
        token = str(cfg.get("DISCORD_BOT_TOKEN") or cfg.get("BOT_TOKEN") or "").strip()
        if not token:
            return jsonify({"ok": False, "error": "missing_bot_token"}), 500

        url = "https://discord.com/api/v10/users/@me/guilds"
        try:
            resp = requests.get(url, headers={"Authorization": f"Bot {token}"}, timeout=10)
        except requests.RequestException as exc:
            return jsonify({"ok": False, "error": "discord_request_failed", "detail": str(exc)}), 502
        if resp.status_code >= 300:
            detail = resp.text.strip() if resp.text else ""
            return jsonify({
                "ok": False,
                "error": f"discord_error ({resp.status_code})",
                "status": resp.status_code,
                "detail": detail[:200],
            }), 502
        payload = resp.json() if resp.content else []
        if not isinstance(payload, list):
            payload = []
        guilds = []
        for g in payload:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("id") or "").strip()
            if not gid:
                continue
            guilds.append({
                "id": gid,
                "name": str(g.get("name") or "").strip()
            })
        return jsonify({"ok": True, "guilds": guilds})

    def _parse_embed_color(raw: str):
        val = str(raw or "").strip()
        if not val:
            return None
        if val.startswith("#"):
            val = val[1:]
        if not re.match(r"^[0-9a-fA-F]{6}$", val):
            return None
        try:
            return int(val, 16)
        except Exception:
            return None

    @bp.post("/admin/embed")
    def admin_embed_post():
        resp = require_admin()
        if resp is not None:
            return resp
        cfg = _load_config(ctx)
        token = str(cfg.get("DISCORD_BOT_TOKEN") or cfg.get("BOT_TOKEN") or "").strip()
        if not token:
            return jsonify({"ok": False, "error": "missing_bot_token"}), 500

        body = request.get_json(silent=True) or {}
        channel_id = str(body.get("channel_id") or "").strip()
        if not channel_id:
            return jsonify({"ok": False, "error": "missing_channel_id"}), 400

        title = str(body.get("title") or "").strip()
        description = str(body.get("description") or "").strip()
        content = str(body.get("content") or "").strip()
        footer_text = str(body.get("footer_text") or "").strip()
        footer_icon_url = str(body.get("footer_icon_url") or "").strip()
        author_name = str(body.get("author_name") or "").strip()
        author_icon_url = str(body.get("author_icon_url") or "").strip()
        thumbnail_url = str(body.get("thumbnail_url") or "").strip()
        image_url = str(body.get("image_url") or "").strip()
        color = _parse_embed_color(body.get("color"))

        embed = {}
        if title:
            embed["title"] = title
        if description:
            embed["description"] = description
        if color is not None:
            embed["color"] = color
        if footer_text or footer_icon_url:
            footer_payload = {"text": footer_text or " "}
            if footer_icon_url:
                footer_payload["icon_url"] = footer_icon_url
            embed["footer"] = footer_payload
        if author_name or author_icon_url:
            author_payload = {"name": author_name or " "}
            if author_icon_url:
                author_payload["icon_url"] = author_icon_url
            embed["author"] = author_payload
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}
        if image_url:
            embed["image"] = {"url": image_url}

        if not embed and not content:
            return jsonify({"ok": False, "error": "empty_embed"}), 400

        payload = {"content": content}
        if embed:
            payload["embeds"] = [embed]

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bot {token}"},
                json=payload,
                timeout=10,
            )
        except requests.RequestException as exc:
            return jsonify({"ok": False, "error": "discord_request_failed", "detail": str(exc)}), 502
        if resp.status_code >= 300:
            detail = resp.text.strip() if resp.text else ""
            return jsonify({
                "ok": False,
                "error": f"discord_error ({resp.status_code})",
                "status": resp.status_code,
                "detail": detail[:200],
            }), 502

        data = resp.json() if resp.content else {}
        message_id = str((data or {}).get("id") or "").strip()
        return jsonify({"ok": True, "message_id": message_id})


    # ---------- FAN ZONE ----------

    def _fanzone_fixture_id_from_fixture(f: dict) -> str:
        home = str((f or {}).get('home') or '').strip()
        away = str((f or {}).get('away') or '').strip()
        when = str((f or {}).get('utc') or (f or {}).get('time') or '').strip()
        return f"{home}-{away}-{when}" if (home and away and when) else ''

    def _load_matches_list() -> list:
        raw = _read_json(_path(ctx, 'matches.json'), [])
        if isinstance(raw, dict):
            raw = raw.get('fixtures') or raw.get('matches') or []
        return raw if isinstance(raw, list) else []

    def _group_from_team_meta(home: str, away: str) -> str:
        meta = _read_json(_path(ctx, "team_meta.json"), {})
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

    def _resolve_fanzone_channel(fixture: dict, home: str, away: str) -> str:
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
            group = _group_from_team_meta(home, away)
        if group:
            return f"group-{group.lower()}"
        return ""

    def _find_fixture_any(match_id: str) -> dict | None:
        mid = str(match_id or '').strip()
        if not mid:
            return None
        fixtures = _load_matches_list()
        for f in fixtures:
            if not isinstance(f, dict):
                continue
            # direct ids if you ever add them
            if mid == str(f.get('id') or '').strip():
                return f
            if mid == str(f.get('fixture_id') or '').strip():
                return f
            # computed fid used by /api/fixtures
            fid = _fanzone_fixture_id_from_fixture(f)
            if fid and mid == fid:
                return f
        return None

    def _append_fanzone_results(discord_ids: list[str], result: str, home: str, away: str, winner_team: str, loser_team: str, fixture_id: str):
        if result not in ('win', 'lose', 'draw'):
            return
        path = _path(ctx, 'fan_zone_results.json')
        data = _read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        events = data.get('events')
        if not isinstance(events, list):
            events = []

        existing = {str(e.get('id')) for e in events if isinstance(e, dict) and e.get('id')}
        now = int(time.time())

        for uid in discord_ids:
            suid = str(uid or '').strip()
            if not suid:
                continue
            eid = f"fz:{fixture_id}:{suid}:{result}"
            if eid in existing:
                continue

            title = 'Match Votes result'
            if result == 'win':
                body = f"✅ {winner_team} beat {loser_team} ({home} vs {away})."
            elif result == 'lose':
                body = f"❌ {loser_team} lost to {winner_team} ({home} vs {away})."
            else:
                body = f"🤝 {home} drew with {away}."

            events.append({
                'id': eid,
                'discord_id': suid,
                'result': result,
                'title': title,
                'body': body,
                'ts': now
            })
            existing.add(eid)

        # keep newest first + cap
        events.sort(key=lambda x: int((x or {}).get('ts') or 0), reverse=True)
        data['events'] = events[:500]
        _write_json_atomic(path, data)

    def _append_fanzone_vote_results(voters: dict, winner_side: str, winner_team: str, fixture_id: str, ts: int):
        if winner_side not in ("home", "away", "draw"):
            return
        path = _path(ctx, 'fan_zone_results.json')
        data = _read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        events = data.get('events')
        if not isinstance(events, list):
            events = []

        existing = {str(e.get('id')) for e in events if isinstance(e, dict) and e.get('id')}

        for uid, choice in voters.items():
            suid = str(uid or '').strip()
            side = str(choice or '').strip().lower()
            if not suid or side not in ('home', 'away', 'draw'):
                continue

            result = 'win' if side == winner_side else 'lose'
            eid = f"fz:{fixture_id}:{suid}:{ts}"
            if eid in existing:
                continue

            title = f"Match Votes: {winner_team} declared" if winner_team else "Match Votes result"
            body = "You won your Match Votes pick." if result == "win" else "You lost your Match Votes pick."

            events.append({
                'id': eid,
                'discord_id': suid,
                'fixture_id': fixture_id,
                'result': result,
                'title': title,
                'body': body,
                'ts': ts
            })
            existing.add(eid)

        events.sort(key=lambda x: int((x or {}).get('ts') or 0), reverse=True)
        data['events'] = events[:500]
        _write_json_atomic(path, data)

    @bp.post("/admin/fanzone/declare")
    def fanzone_declare_winner():
        resp = require_admin()
        if resp is not None:
            return resp

        body = request.get_json(silent=True) or {}

        # Accept either match_id or fixture_id from the panel
        match_id = str(body.get('match_id') or body.get('fixture_id') or '').strip()
        if not match_id:
            return jsonify({'ok': False, 'error': 'missing_match_id'}), 400

        f = _find_fixture_any(match_id)
        if not f:
            return jsonify({'ok': False, 'error': 'fixture_not_found'}), 404

        home = str(f.get('home') or f.get('home_team') or f.get('team1') or '').strip()
        away = str(f.get('away') or f.get('away_team') or f.get('team2') or '').strip()
        utc = str(f.get('utc') or f.get('time') or '').strip()

        fixture_id = match_id

        derived_id = _fanzone_fixture_id_from_fixture({'home': home, 'away': away, 'utc': utc})
        alias_ids = []
        if derived_id and derived_id != fixture_id:
            alias_ids.append(derived_id)

        # Winner can be provided as side (home|away) or as team name.
        side = str(body.get('winner') or '').strip().lower()  # 'home' | 'away' | 'draw'
        winner_team_in = str(body.get('winner_team') or body.get('winnerTeam') or '').strip()
        winner_iso_in = str(body.get('winner_iso') or body.get('winnerIso') or '').strip().lower()

        clear = bool(body.get('clear'))

        winner_team = ''
        loser_team = ''

        if clear:
            winner_team = ''
            loser_team = ''
        elif side in ('home', 'away'):
            winner_team = home if side == 'home' else away
            loser_team = away if side == 'home' else home
        elif side == 'draw':
            winner_team = 'Draw'
            loser_team = ''
        elif winner_team_in:
            if winner_team_in.lower() == home.lower():
                winner_team = home
                loser_team = away
                side = 'home'
            elif winner_team_in.lower() == away.lower():
                winner_team = away
                loser_team = home
                side = 'away'
            else:
                return jsonify({'ok': False, 'error': 'invalid_winner_team'}), 400
        else:
            return jsonify({'ok': False, 'error': 'invalid_winner'}), 400

        # Save winner record + lock voting (JSON path matches routes_public.py)
        winners_path = _path(ctx, 'fan_winners.json')
        winners = _read_json(winners_path, {})
        if not isinstance(winners, dict):
            winners = {}

        if clear:
            winners.pop(fixture_id, None)
            for aid in alias_ids:
                winners.pop(aid, None)
            _write_json_atomic(winners_path, winners)
            log.info("Fan zone winner cleared by %s (fixture_id=%s)", _user_label(), fixture_id)
            return jsonify({'ok': True, 'cleared': True, 'fixture_id': fixture_id})

        rec = {
            'fixture_id': fixture_id,
            'home': home,
            'away': away,
            'utc': utc,
            'winner': side,  # <- your public stats endpoint reads this
            'winner_side': side,
            'winner_team': winner_team,
            'winner_iso': winner_iso_in,
            'ts': int(time.time())
        }

        winners[fixture_id] = rec
        for aid in alias_ids:
            winners[aid] = rec  # alias lock
        _write_json_atomic(winners_path, winners)

        # Snapshot votes at declare-time for fairness/audit
        votes_path = _fanzone_votes_path(ctx)
        votes_blob = _read_json(votes_path, {'fixtures': {}})
        if not isinstance(votes_blob, dict):
            votes_blob = {'fixtures': {}}

        fixtures_votes = votes_blob.get('fixtures') or {}
        if not isinstance(fixtures_votes, dict):
            fixtures_votes = {}

        fx = fixtures_votes.get(fixture_id, {})
        if not isinstance(fx, dict) and alias_ids:
            for aid in alias_ids:
                fx = fixtures_votes.get(aid, {})
                if isinstance(fx, dict):
                    break
        if not isinstance(fx, dict):
            fx = {}

        home_votes = int(fx.get('home') or 0)
        away_votes = int(fx.get('away') or 0)
        draw_votes = int(fx.get('draw') or 0)
        total_votes = max(0, home_votes + away_votes + draw_votes)

        discord_voters = fx.get('discord_voters')
        if not isinstance(discord_voters, dict):
            discord_voters = {}

        snapshots_path = _path(ctx, 'fan_vote_snapshots.json')
        snap_blob = _read_json(snapshots_path, {'fixtures': {}})
        if not isinstance(snap_blob, dict):
            snap_blob = {'fixtures': {}}

        snap_fixtures = snap_blob.setdefault('fixtures', {})
        if not isinstance(snap_fixtures, dict):
            snap_fixtures = {}
            snap_blob['fixtures'] = snap_fixtures

        snap_fixtures[fixture_id] = {
            'fixture_id': fixture_id,
            'home': home,
            'away': away,
            'utc': utc,
            'winner_side': side,
            'winner_team': winner_team,
            'loser_team': loser_team,
            'declared_at': int(time.time()),
            'home_votes': home_votes,
            'away_votes': away_votes,
            'draw_votes': draw_votes,
            'total': total_votes
        }
        _write_json_atomic(snapshots_path, snap_blob)

        # Determine owners for DM + site notifications
        winner_owner_ids = _owners_for_team(ctx, winner_team) if side in ('home', 'away') else []
        loser_owner_ids = _owners_for_team(ctx, loser_team) if side in ('home', 'away') else []
        draw_owner_ids = []
        if side == 'draw':
            draw_owner_ids = _owners_for_team(ctx, home) + _owners_for_team(ctx, away)
            draw_owner_ids = list(dict.fromkeys(draw_owner_ids))
        dm_winner_owner_ids = _filter_notification_ids(ctx, winner_owner_ids, "dms", "matches")
        dm_loser_owner_ids = _filter_notification_ids(ctx, loser_owner_ids, "dms", "matches")
        dm_draw_owner_ids = _filter_notification_ids(ctx, draw_owner_ids, "dms", "matches")
        bell_winner_owner_ids = _filter_notification_ids(ctx, winner_owner_ids, "bell", "matches")
        bell_loser_owner_ids = _filter_notification_ids(ctx, loser_owner_ids, "bell", "matches")
        bell_draw_owner_ids = _filter_notification_ids(ctx, draw_owner_ids, "bell", "matches")

        # Queue bot announcement + DMs
        cfg = _read_json(_path(ctx, 'config.json'), {})
        channel_name = _resolve_fanzone_channel(f, home, away)
        if not channel_name:
            channel_name = str(cfg.get('FANZONE_CHANNEL_NAME') or cfg.get('FANZONE_CHANNEL') or 'fanzone')

        _enqueue_command(ctx, 'fanzone_winner', {
            'fixture_id': fixture_id,
            'home': home,
            'away': away,
            'utc': utc,
            'group': str(f.get('group') or ''),
            'stage': str(f.get('stage') or f.get('round') or f.get('phase') or ''),
            'winner_side': side,
            'winner_team': winner_team,
            'loser_team': loser_team,
            'winner_iso': winner_iso_in,
            'loser_iso': '',
            'winner_owner_ids': dm_winner_owner_ids,
            'loser_owner_ids': dm_loser_owner_ids,
            'draw_owner_ids': dm_draw_owner_ids,
            'channel': channel_name,
            'home_votes': home_votes,
            'away_votes': away_votes,
            'draw_votes': draw_votes,
            'total_votes': total_votes
        })

        # Website bell notifications
        if side in ('home', 'away'):
            _append_fanzone_results(bell_winner_owner_ids, 'win', home, away, winner_team, loser_team, fixture_id)
            _append_fanzone_results(bell_loser_owner_ids, 'lose', home, away, winner_team, loser_team, fixture_id)
        elif side == 'draw':
            _append_fanzone_results(bell_draw_owner_ids, 'draw', home, away, winner_team, loser_team, fixture_id)
        _append_fanzone_vote_results(_filter_notification_voters(ctx, discord_voters, "matches"), side, winner_team, fixture_id, int(time.time()))

        log.info(
            "Fan zone winner declared by %s (fixture_id=%s winner_side=%s winner_team=%s home_votes=%s away_votes=%s draw_votes=%s)",
            _user_label(),
            fixture_id,
            side,
            winner_team,
            home_votes,
            away_votes,
            draw_votes,
        )

        return jsonify({
            'ok': True,
            'fixture_id': fixture_id,
            'winner_side': side,
            'winner_team': winner_team,
            'loser_team': loser_team,
            'winner_owner_ids': winner_owner_ids,
            'loser_owner_ids': loser_owner_ids,
            'home_votes': home_votes,
            'away_votes': away_votes,
            'draw_votes': draw_votes,
            'total_votes': total_votes
        })


    return bp
log = logging.getLogger("launcher")
