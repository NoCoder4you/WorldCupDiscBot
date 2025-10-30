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

def _ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p

def _backup_dir(base_dir):   return _ensure_dir(os.path.join(base_dir, "Backups"))
def _json_dir(base_dir):     return _ensure_dir(os.path.join(base_dir, "JSON"))
def _runtime_dir(base_dir):  return _ensure_dir(os.path.join(base_dir, "runtime"))

def _bets_path(base_dir):       return os.path.join(_json_dir(base_dir), "bets.json")
def _ownership_path(base_dir):  return os.path.join(_json_dir(base_dir), "ownership.json")
def _verified_path(base_dir):   return os.path.join(_json_dir(base_dir), "verified.json")
def _players_path(base_dir):    return os.path.join(_json_dir(base_dir), "players.json")
def _teams_path(base_dir):      return os.path.join(_json_dir(base_dir), "teams.json")
def _team_iso_path(base_dir):   return os.path.join(_json_dir(base_dir), "team_iso.json")

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

# --------- Normalizers ---------
def _verified_list(base):
    blob = _json_load(_verified_path(base), {})
    raw = blob.get("verified_users") if isinstance(blob, dict) else blob
    return raw if isinstance(raw, list) else []

def _id_to_display(base):
    out = {}
    for u in _verified_list(base):
        if not isinstance(u, dict): 
            continue
        did = str(u.get("discord_id") or u.get("id") or u.get("user_id") or "").strip()
        disp = (u.get("display_name") or u.get("username") or u.get("name") or "").strip()
        if did:
            out[did] = disp or did
    return out

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

    # ---------- Minimal health ----------
    @api.get("/log/<kind>")
    def log_get(kind):
        paths = ctx.get("LOG_PATHS", {})
        fp = paths.get(kind)
        if not fp or not os.path.exists(fp):
            return jsonify({"ok": True, "lines": []})
        return jsonify({"ok": True, "lines": _tail_file(fp, max_lines=500)})

    # ---------- Verified (normalized) ----------
    @api.get("/verified")
    def api_verified():
        base = ctx.get("BASE_DIR", "")
        out = []
        for v in _verified_list(base):
            if not isinstance(v, dict): 
                continue
            out.append({
                "discord_id": str(v.get("discord_id") or v.get("id") or v.get("user_id") or ""),
                "username": v.get("username") or v.get("name") or "",
                "display_name": v.get("display_name") or v.get("username") or "",
                "habbo_name": v.get("habbo_name") or ""
            })
        return jsonify(out)

    # ---------- Bets (enriched with display_name) ----------
    @api.get("/bets")
    def api_bets():
        base = ctx.get("BASE_DIR", "")
        bets = _json_load(_bets_path(base), [])
        id_to_disp = _id_to_display(base)

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

    # ---------- Ownership legacy normalized ----------
    @api.get("/ownerships")
    def ownerships_get():
        base = ctx.get("BASE_DIR","")
        id_to_disp = _id_to_display(base)
        raw = _json_load(_ownership_path(base), {})
        items = []

        def resolve_name(x):
            if x is None: return ""
            if isinstance(x, dict):
                did = str(x.get("discord_id") or x.get("id") or x.get("user_id") or "").strip()
                disp = (x.get("display_name") or x.get("username") or x.get("name") or "").strip()
                if did and did in id_to_disp: return id_to_disp[did]
                return disp or did
            sx = str(x).strip()
            if sx.isdigit() and sx in id_to_disp: return id_to_disp[sx]
            return sx

        if isinstance(raw, dict):
            for team, val in raw.items():
                if isinstance(val, list):
                    owners = val; splits = []
                elif isinstance(val, dict):
                    owners = val.get("owners") or val.get("owner") or []
                    splits = val.get("splits") or val.get("split_with") or []
                else:
                    owners = [val]; splits = []
                if isinstance(owners, (str, dict)): owners = [owners]
                if isinstance(splits, (str, dict)): splits = [splits]

                owners_disp = [resolve_name(o) for o in owners if o is not None]
                splits_disp = [resolve_name(s) for s in splits if s is not None]

                owner_main = owners_disp[0] if owners_disp else ""
                split_with = ", ".join([n for n in splits_disp if n and n != owner_main])
                items.append({"team": str(team), "owner": owner_main, "split_with": split_with})

        elif isinstance(raw, list):
            for row in raw:
                if not isinstance(row, dict): continue
                team = row.get("team") or row.get("country") or ""
                owners = row.get("owners") or row.get("owner") or []
                splits = row.get("splits") or row.get("split_with") or []
                if isinstance(owners, (str, dict)): owners = [owners]
                if isinstance(splits, (str, dict)): splits = [splits]
                owners_disp = [resolve_name(o) for o in owners if o is not None]
                splits_disp = [resolve_name(s) for s in splits if s is not None]
                owner_main = owners_disp[0] if owners_disp else ""
                split_with = ", ".join([n for n in splits_disp if n and n != owner_main])
                items.append({"team": str(team), "owner": owner_main, "split_with": split_with})

        return jsonify({"items": items, "ownerships": items})

    # ---------- Ownership from players (expected by app.js) ----------
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
                if not isinstance(pdata, dict): continue
                for entry in (pdata.get("teams") or []):
                    if not isinstance(entry, dict): continue
                    team = entry.get("team")
                    own = entry.get("ownership") or {}
                    main_owner = own.get("main_owner")
                    split_with = [str(x) for x in (own.get("split_with") or [])]
                    if not team: continue
                    rec = country_map.setdefault(team, {"main_owner": None, "split_with": []})
                    if main_owner is not None:
                        if rec["main_owner"] is None or str(main_owner) == str(uid):
                            rec["main_owner"] = str(main_owner)
                    for sid in split_with:
                        if sid and sid not in rec["split_with"]:
                            rec["split_with"].append(sid)

        rows = []
        for team in sorted(country_map.keys(), key=lambda x: x.lower()):
            rec = country_map[team]
            main_id = rec.get("main_owner")
            split_ids = [sid for sid in rec.get("split_with", []) if sid and sid != str(main_id)]
            rows.append({
                "country": team,
                "main_owner": None if main_id is None else {"id": str(main_id), "username": id_to_name.get(str(main_id))},
                "split_with": [{"id": sid, "username": id_to_name.get(sid)} for sid in split_ids],
                "owners_count": (1 if main_id else 0) + len(split_ids)
            })
        return jsonify({"rows": rows, "count": len(rows)})

    # ---------- Ownership merged (teams list + players mapping) ----------
    @api.get("/ownership_merged")
    def api_ownership_merged():
        base = ctx.get("BASE_DIR", "")
        teams_raw = _json_load(_teams_path(base), [])
        teams = teams_raw["teams"] if isinstance(teams_raw, dict) and "teams" in teams_raw else teams_raw
        if not isinstance(teams, list):
            teams = []

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
                if not isinstance(pdata, dict): continue
                for entry in (pdata.get("teams") or []):
                    if not isinstance(entry, dict): continue
                    team = entry.get("team")
                    if not team: continue
                    own = entry.get("ownership") or {}
                    main_owner = own.get("main_owner")
                    split_with = [str(x) for x in (own.get("split_with") or [])]
                    rec = country_map.setdefault(team, {"main_owner": None, "split_with": []})
                    if main_owner is not None:
                        if rec["main_owner"] is None or str(main_owner) == str(uid):
                            rec["main_owner"] = str(main_owner)
                    for sid in split_with:
                        if sid and sid not in rec["split_with"]:
                            rec["split_with"].append(sid)

        rows = []
        for team in sorted([str(t) for t in teams], key=lambda s: s.lower()):
            rec = country_map.get(team, {"main_owner": None, "split_with": []})
            main_id = rec.get("main_owner")
            split_ids = [sid for sid in rec.get("split_with", []) if sid and sid != str(main_id)]
            rows.append({
                "country": team,
                "main_owner": None if main_id is None else {"id": str(main_id), "username": id_to_name.get(str(main_id))},
                "split_with": [{"id": sid, "username": id_to_name.get(sid)} for sid in split_ids],
                "owners_count": (1 if main_id else 0) + len(split_ids)
            })
        return jsonify({"rows": rows, "count": len(rows)})

    # ---------- Player names map (optional helper) ----------
    @api.get("/player_names")
    def api_player_names():
        base = ctx.get("BASE_DIR", "")
        players = _json_load(_players_path(base), {})
        out = {}
        if isinstance(players, dict):
            for uid, pdata in players.items():
                if isinstance(pdata, dict):
                    name = pdata.get("display_name") or pdata.get("username") or pdata.get("name")
                    if name:
                        out[str(uid)] = str(name)
        return jsonify(out)

    return [root, api]
