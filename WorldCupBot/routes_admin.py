
from flask import Blueprint, jsonify, request, send_file, session
import os, json, time, requests, glob, functools

def create_admin_routes(context):
    BASE_DIR = context["BASE_DIR"]
    LOG_PATHS = context["LOG_PATHS"]
    start_bot = context["start_bot"]
    stop_bot = context["stop_bot"]
    restart_bot = context["restart_bot"]
    is_bot_running = context["is_bot_running"]
    bot_last_stop_ref = context["bot_last_stop_ref"]
    DISCORD_WEBHOOK_URL = context["DISCORD_WEBHOOK_URL"]
    BETS_WEBHOOK_URL = context["BETS_WEBHOOK_URL"]
    ADMIN_PASSWORD = context.get("ADMIN_PASSWORD", "")

    routes_admin = Blueprint("routes_admin", __name__, url_prefix="/admin")

    # --- Auth helpers ---
    def require_auth(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("admin_authed"):
                return jsonify({"ok": False, "error": "Unauthorized"}), 401
            return fn(*args, **kwargs)
        return wrapper

    @routes_admin.route('/auth/status')
    def auth_status():
        return jsonify({"ok": True, "authed": bool(session.get("admin_authed"))})

    @routes_admin.route('/login', methods=['POST'])
    def login():
        try:
            data = request.get_json(force=True, silent=True) or {}
            pwd = data.get("password", "")
        except Exception:
            pwd = ""
        if not ADMIN_PASSWORD:
            return jsonify({"ok": False, "error": "Admin password not set on server"}), 500
        if pwd == ADMIN_PASSWORD:
            session["admin_authed"] = True
            session.permanent = True
            return jsonify({"ok": True, "message": "Authenticated"})
        return jsonify({"ok": False, "error": "Invalid password"}), 401

    @routes_admin.route('/logout', methods=['POST'])
    def logout():
        session.pop("admin_authed", None)
        return jsonify({"ok": True})

    # --- Protected routes below ---

    # Bot control
    @routes_admin.route('/bot/start', methods=['POST'])
    @require_auth
    def api_bot_start():
        context["manual_stop_ref"]["value"] = False
        if start_bot():
            return jsonify({"status": "started"})
        return jsonify({"status": "already running"})

    @routes_admin.route('/bot/restart', methods=['POST'])
    @require_auth
    def api_bot_restart():
        context["manual_stop_ref"]["value"] = False
        restart_bot()
        return jsonify({"status": "restarted"})

    @routes_admin.route('/bot/stop', methods=['POST'])
    @require_auth
    def api_bot_stop():
        context["manual_stop_ref"]["value"] = True
        if stop_bot():
            return jsonify({"status": "stopped"})
        return jsonify({"status": "not running"})

    # Logs
    @routes_admin.route('/log/<logtype>')
    @require_auth
    def api_log_get(logtype):
        path = LOG_PATHS.get(logtype)
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            if len(lines) > 500:
                lines = lines[-500:]
            return jsonify({"lines": lines})
        return jsonify({"lines": []})

    @routes_admin.route('/log/<logtype>/download')
    @require_auth
    def api_log_download(logtype):
        path = LOG_PATHS.get(logtype)
        if path and os.path.exists(path):
            return send_file(path, as_attachment=True)
        return ("Not found", 404)

    @routes_admin.route('/log/<logtype>/clear', methods=['POST'])
    @require_auth
    def api_log_clear(logtype):
        path = LOG_PATHS.get(logtype)
        if path and os.path.exists(path):
            with open(path, "w", encoding="utf-8"):
                pass
            return jsonify({"cleared": True})
        return jsonify({"cleared": False})

    # Cogs
    @routes_admin.route('/cogs')
    @require_auth
    def api_cogs():
        cogs = []
        cogs_status_file = os.path.join(BASE_DIR, "JSON", "cogs_status.json")
        loaded = []
        if os.path.exists(cogs_status_file):
            with open(cogs_status_file) as f:
                loaded = json.load(f).get("loaded", [])
            loaded = [cog.split('.')[-1] for cog in loaded]
        for cog_path in glob.glob(os.path.join(BASE_DIR, "COGS", "*.py")):
            name = os.path.basename(cog_path)
            if name == "__init__.py":
                continue
            shortname = name[:-3]
            cogs.append({
                "name": shortname,
                "loaded": shortname in loaded,
                "last_error": ""
            })
        return jsonify({"cogs": cogs})

    @routes_admin.route('/cogs/action', methods=['POST'])
    @require_auth
    def api_cogs_action():
        req = request.get_json()
        cog = req.get("cog")
        action = req.get("action")
        if not DISCORD_WEBHOOK_URL:
            return jsonify({"ok": False, "error": "DISCORD_WEBHOOK_URL not set in config.json"})
        content = f"wc {action} {cog}"
        r = requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
        if r.status_code == 204:
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "error": f"Webhook status: {r.status_code}"})

    # Bets
    @routes_admin.route('/bets/settle', methods=['POST'])
    @require_auth
    def api_bets_settle():
        data = request.get_json()
        bet_id = data.get("bet_id")
        winner_id = data.get("winner_id")
        if not bet_id or not winner_id:
            return jsonify({"ok": False, "error": "Missing parameters"})
        if not BETS_WEBHOOK_URL:
            return jsonify({"ok": False, "error": "BETS_WEBHOOK_URL not set in config.json"})
        payload = { "content": f"!bet settle {bet_id} {winner_id}" }
        resp = requests.post(BETS_WEBHOOK_URL, json=payload)
        if resp.status_code in (200, 204):
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": f"Webhook failed: {resp.text}"})

    # Ownership Management
    @routes_admin.route('/ownership/update', methods=['POST'])
    @require_auth
    def api_ownership_update():
        req = request.get_json()
        country = req.get("country")
        owners = req.get("owners", [])
        action = req.get("action", "reassign")

        PLAYERS_JSON = os.path.join(BASE_DIR, "JSON", "players.json")
        VERIFIED_JSON = os.path.join(BASE_DIR, "JSON", "verified.json")

        try:
            with open(VERIFIED_JSON, "r") as f:
                verified = json.load(f).get("verified_users", [])
            verified_map = {str(u["habbo_name"]): str(u["discord_id"]) for u in verified}

            with open(PLAYERS_JSON, "r") as f:
                players = json.load(f)

            def ownership_entry(main_owner_id, split_ids):
                return {
                    "team": country,
                    "ownership": {
                        "main_owner": int(main_owner_id),
                        "split_with": [int(x) for x in split_ids]
                    }
                }

            if action == "reassign":
                # Remove existing instances of the team
                for pdata in players.values():
                    if "teams" in pdata:
                        pdata["teams"] = [t for t in pdata["teams"] if (t.get("team") if isinstance(t, dict) else t) != country]

                if owners:
                    main_habbo = owners[0]
                    main_id = verified_map.get(main_habbo)
                    co_habbos = owners[1:]
                    co_ids = [verified_map[n] for n in co_habbos if n in verified_map]

                    # Ensure all owners exist
                    for hname in owners:
                        uid = verified_map.get(hname)
                        if uid and uid not in players:
                            players[uid] = {"display_name": hname, "teams": []}

                    if main_id:
                        players[main_id].setdefault("teams", [])
                        players[main_id]["teams"].append(ownership_entry(main_id, co_ids))

                    for co_habbo in co_habbos:
                        co_id = verified_map.get(co_habbo)
                        if co_id:
                            players[co_id].setdefault("teams", [])
                            players[co_id]["teams"].append(ownership_entry(main_id, co_ids))

            elif action == "split":
                # Find current main owner id for given country
                main_id = None
                for uid, pdata in players.items():
                    for t in pdata.get("teams", []):
                        if isinstance(t, dict) and t.get("team") == country and t.get("ownership", {}).get("main_owner") == int(uid):
                            main_id = uid
                            break
                    if main_id:
                        break

                if not main_id:
                    return jsonify({"ok": False, "error": "No existing main owner found for split."})

                new_co_habbos = [h for h in owners if verified_map.get(h) != main_id]
                new_co_ids = [verified_map[h] for h in new_co_habbos if h in verified_map]

                for t in players[main_id].get("teams", []):
                    if isinstance(t, dict) and t.get("team") == country:
                        current_split = set(t.get("ownership", {}).get("split_with", []))
                        t["ownership"]["split_with"] = list(current_split.union({int(x) for x in new_co_ids}))

                for co_habbo, co_id in zip(new_co_habbos, new_co_ids):
                    if co_id not in players:
                        players[co_id] = {"display_name": co_habbo, "teams": []}
                    found = False
                    for t in players[co_id].get("teams", []):
                        if isinstance(t, dict) and t.get("team") == country:
                            found = True
                            break
                    if not found:
                        players[co_id]["teams"].append(ownership_entry(main_id, new_co_ids))

            with open(PLAYERS_JSON, "w") as f:
                json.dump(players, f, indent=2)

            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    # Split Requests
    @routes_admin.route('/split_requests')
    @require_auth
    def api_split_requests():
        with open(os.path.join(BASE_DIR, "JSON", "split_requests.json")) as f:
            pending = json.load(f)
        with open(os.path.join(BASE_DIR, "JSON", "split_requests_log.json")) as f:
            log = json.load(f)
        with open(os.path.join(BASE_DIR, "JSON", "verified.json")) as f:
            verified = json.load(f).get("verified_users", [])
        with open(os.path.join(BASE_DIR, "JSON", "players.json")) as f:
            players = json.load(f)

        habbo_map = {str(u["discord_id"]): u["habbo_name"] for u in verified}

        def get_owners(team):
            owners = set()
            for uid, pdata in players.items():
                for t in pdata.get("teams", []):
                    if isinstance(t, dict) and t.get("team") == team:
                        main_owner = str(t["ownership"].get("main_owner"))
                        if main_owner:
                            owners.add(main_owner)
                        for co in t["ownership"].get("split_with", []):
                            owners.add(str(co))
            return list(owners)

        pending_requests = []
        for req_id, req in pending.items():
            owners = get_owners(req["team"])
            count = len(owners)
            percent = round(100 / (count + 1), 2) if count else 100
            pending_requests.append({
                "request_id": req_id,
                "team": req["team"],
                "main_owner_name": habbo_map.get(str(req["main_owner_id"]), ""),
                "requester_name": habbo_map.get(str(req["requester_id"]), ""),
                "status": "pending",
                "timestamp": req.get("expires_at"),
                "ownership_percentage": percent
            })

        resolved_requests = []
        for log_item in log:
            team = log_item.get("team")
            owners = get_owners(team)
            requester_id = str(log_item.get("requester_id"))
            status = log_item.get("status")

            owners_after = set(owners)
            if status == "accepted":
                owners_after.add(requester_id)
            elif status in ("declined", "expired"):
                owners_after.discard(requester_id)

            owner_count = len(owners_after) if owners_after else 1
            percent = round(100 / owner_count, 2) if owner_count else 100

            resolved_requests.append({
                "request_id": log_item.get("request_id"),
                "team": team,
                "main_owner_name": habbo_map.get(str(log_item.get("main_owner_id")), ""),
                "requester_name": habbo_map.get(requester_id, ""),
                "status": status,
                "timestamp": log_item.get("timestamp"),
                "ownership_percentage": percent
            })

        def safe_int(v):
            try:
                return int(v)
            except Exception:
                return 0

        resolved_requests = sorted(resolved_requests, key=lambda x: safe_int(x.get("timestamp", 0)), reverse=True)
        pending_requests = sorted(pending_requests, key=lambda x: safe_int(x.get("timestamp", 0)))

        return jsonify({
            "pending": pending_requests,
            "resolved": resolved_requests
        })

    @routes_admin.route('/split_requests/force', methods=['POST'])
    @require_auth
    def api_split_requests_force():
        data = request.json
        req_id = data.get('request_id')
        action = data.get('action')
        if not req_id or action not in ("forceaccept", "forcedecline", "delete"):
            return jsonify({"ok": False, "error": "Bad params"})

        split_pending_path = os.path.join(BASE_DIR, "JSON", "split_requests.json")
        split_log_path = os.path.join(BASE_DIR, "JSON", "split_requests_log.json")

        with open(split_pending_path, "r") as f:
            pending = json.load(f)
        with open(split_log_path, "r") as f:
            log = json.load(f)

        if action == "delete":
            if req_id in pending:
                del pending[req_id]
                with open(split_pending_path, "w") as f:
                    json.dump(pending, f, indent=2)
                return jsonify({"ok": True, "msg": "Request deleted."})
            return jsonify({"ok": False, "error": "Request not found in pending."})

        if req_id not in pending:
            return jsonify({"ok": False, "error": "Request not in pending."})
        req_data = pending[req_id]
        status = "accepted" if action == "forceaccept" else "declined"
        log_entry = {
            "request_id": req_id,
            "team": req_data.get("team"),
            "main_owner_id": str(req_data.get("main_owner_id")),
            "requester_id": str(req_data.get("requester_id")),
            "timestamp": int(time.time()),
            "status": status
        }
        log.append(log_entry)
        del pending[req_id]
        with open(split_pending_path, "w") as f:
            json.dump(pending, f, indent=2)
        with open(split_log_path, "w") as f:
            json.dump(log, f, indent=2)
        return jsonify({"ok": True, "msg": f"Request {status}."})

    return routes_admin
