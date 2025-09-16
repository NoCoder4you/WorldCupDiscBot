import os
import sys
import subprocess
import threading
import time
import psutil
import json
import requests
import glob
from flask import Flask, jsonify, request, send_from_directory, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(BASE_DIR, "JSON")
VENV_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'WCenv'))
PYTHON_BIN = os.path.join(VENV_DIR, 'bin', 'python')
REQUIREMENTS = os.path.join(BASE_DIR, 'requirements.txt')
BOT_FILE = os.path.join(BASE_DIR, 'bot.py')

HEALTH_LOG = os.path.join(BASE_DIR, "health.log")
HEALTH_LOG_MAX_SIZE = 2 * 1024 * 1024  
LOG_PATHS = {
    "bot": os.path.join(BASE_DIR, "WC.log"),
    "health": HEALTH_LOG
}

PLAYERS_JSON = os.path.join(BASE_DIR, "JSON", "players.json")
TEAMS_JSON = os.path.join(BASE_DIR, "JSON", "teams.json")
VERIFIED_JSON = os.path.join(BASE_DIR, "JSON", "verified.json")
COGS_PATH = os.path.join(BASE_DIR, "COGS")
BACKUPS_DIR = os.path.join(BASE_DIR, "Backups")
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1400194528249643029/96jWJ_tk8iUwIfsHnG1PuUgXW9E-tyqwIOjlvQvabeHFo3R1CIMDc1mHrlTdJTlBunBl"
BETS_WEBHOOK_URL = "https://discord.com/api/webhooks/1401718176370397246/bIYNjKW73E4RU0nfzz_hVUg4fMHepy0zNAHB5_XyAIYeOPQykz7Idj-7lkd4_PdZiCDU"

BACKUP_RETENTION = 6
BACKUP_INTERVAL_SECS = 6 * 60 * 60  # 6 hours
os.makedirs(BACKUPS_DIR, exist_ok=True)

LAUNCH_TIME = time.time()
manual_stop = False
bot_last_start = None
bot_last_stop = None

app = Flask(__name__)
bot_process = None

def pip_install_requirements():
    print("Installing requirements from requirements.txt with python -m pip...")
    subprocess.run([PYTHON_BIN, '-m', 'pip', 'install', '-r', REQUIREMENTS], check=True)

def start_bot():
    global bot_process, bot_last_start, bot_last_stop
    if bot_process and bot_process.poll() is None:
        return False
    bot_process = subprocess.Popen([PYTHON_BIN, BOT_FILE])
    bot_last_start = time.time()
    bot_last_stop = None
    print(f"Started bot.py with PID {bot_process.pid}")
    return True

def stop_bot():
    global bot_process, bot_last_stop
    if bot_process and bot_process.poll() is None:
        print("Stopping bot.py...")
        bot_process.terminate()
        try:
            bot_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("Bot did not exit cleanly, killing.")
            bot_process.kill()
        print("Bot stopped.")
        bot_last_stop = time.time()
        return True
    print("Bot was not running.")
    if bot_last_stop is None:
        bot_last_stop = time.time()
    return False

def restart_bot():
    print("Restarting bot.py...")
    stop_bot()
    time.sleep(1)
    start_bot()
    return True

def is_bot_running():
    return bot_process and bot_process.poll() is None

def get_bot_resource_usage():
    if is_bot_running():
        try:
            proc = psutil.Process(bot_process.pid)
            mem = proc.memory_info().rss / 1024 / 1024
            cpu = proc.cpu_percent(interval=0.1)
            return {"mem_mb": mem, "cpu_percent": cpu}
        except Exception:
            return {"mem_mb": None, "cpu_percent": None}
    return {"mem_mb": None, "cpu_percent": None}

def write_health_log(mem_mb, cpu_percent):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    logline = f"{timestamp} | Memory: {mem_mb:.2f} MB | CPU: {cpu_percent:.1f}%\n"
    with open(HEALTH_LOG, "a") as f:
        f.write(logline)
    if os.path.getsize(HEALTH_LOG) > HEALTH_LOG_MAX_SIZE:
        with open(HEALTH_LOG, "r") as f:
            lines = f.readlines()[-500:]
        with open(HEALTH_LOG, "w") as f:
            f.writelines(lines)

def get_verified_map():
    with open(VERIFIED_JSON, "r") as f:
        verified = json.load(f)["verified_users"]
    return {u["habbo_name"]: u["discord_id"] for u in verified}

@app.route('/api/ping')
def api_ping():
    return jsonify({
        "status": "ok",
        "bot_running": is_bot_running(),
        "pid": bot_process.pid if is_bot_running() else None
    })

@app.route('/api/uptime')
def api_uptime():
    now = time.time()
    global bot_last_start, bot_last_stop
    if is_bot_running():
        if bot_last_start is None:
            bot_last_start = now
        uptime_seconds = int(now - bot_last_start)
        return jsonify({
            "bot_running": True,
            "uptime_seconds": uptime_seconds,
            "uptime_hms": time.strftime("%H:%M:%S", time.gmtime(uptime_seconds))
        })
    else:
        if bot_last_stop:
            downtime_seconds = int(now - bot_last_stop)
        else:
            downtime_seconds = 0
        return jsonify({
            "bot_running": False,
            "downtime_seconds": downtime_seconds,
            "downtime_hms": time.strftime("%H:%M:%S", time.gmtime(downtime_seconds))
        })

@app.route('/api/system')
def api_system():
    usage = get_bot_resource_usage()
    sys_mem = psutil.virtual_memory()
    sys_cpu = psutil.cpu_percent(interval=0.1)
    disk = psutil.disk_usage('/')
    return jsonify({
        "bot": usage,
        "system": {
            "mem_total_mb": sys_mem.total / 1024 / 1024,
            "mem_used_mb": sys_mem.used / 1024 / 1024,
            "mem_percent": sys_mem.percent,
            "cpu_percent": sys_cpu,
            "disk_total_mb": disk.total / 1024 / 1024,
            "disk_used_mb": disk.used / 1024 / 1024,
            "disk_percent": disk.percent
        }
    })

@app.route('/api/guilds')
def api_guilds():
    try:
        with open(os.path.join(BASE_DIR, "JSON", "guilds.json"), "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception:
        return jsonify({"guild_count": 0, "guilds": []})

@app.route('/api/players')
def api_players():
    with open(os.path.join(BASE_DIR, "JSON", "players.json")) as f:
        players = json.load(f)
    return jsonify(players)

@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    global manual_stop
    manual_stop = False
    if start_bot():
        return jsonify({"status": "started"})
    return jsonify({"status": "already running"})

@app.route('/api/bot/restart', methods=['POST'])
def api_bot_restart():
    global manual_stop
    manual_stop = False
    restart_bot()
    return jsonify({"status": "restarted"})

@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    global manual_stop
    manual_stop = True
    if stop_bot():
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not running"})

# --- LOG API ENDPOINTS ---
@app.route('/api/log/<logtype>')
def api_log_get(logtype):
    path = LOG_PATHS.get(logtype)
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        if len(lines) > 500:
            lines = lines[-500:]
        return jsonify({"lines": lines})
    return jsonify({"lines": []})

@app.route('/api/log/<logtype>/download')
def api_log_download(logtype):
    path = LOG_PATHS.get(logtype)
    if path and os.path.exists(path):
        return send_file(path, as_attachment=True)
    return ("Not found", 404)

@app.route('/api/log/<logtype>/clear', methods=['POST'])
def api_log_clear(logtype):
    path = LOG_PATHS.get(logtype)
    if path and os.path.exists(path):
        with open(path, "w", encoding="utf-8"):
            pass
        return jsonify({"cleared": True})
    return jsonify({"cleared": False})


# --- SPLIT REQUEST ENDPOINTS ---
def safe_int(val):
    try:
        return int(val)
    except Exception:
        return 0

@app.route('/api/split_requests')
def api_split_requests():
    # Load everything needed
    with open(os.path.join(BASE_DIR, "JSON", "split_requests.json")) as f:
        pending = json.load(f)
    with open(os.path.join(BASE_DIR, "JSON", "split_requests_log.json")) as f:
        log = json.load(f)
    with open(os.path.join(BASE_DIR, "JSON", "verified.json")) as f:
        verified = json.load(f)["verified_users"]
    with open(os.path.join(BASE_DIR, "JSON", "players.json")) as f:
        players = json.load(f)

    habbo_map = {str(u["discord_id"]): u["habbo_name"] for u in verified}

    # Helper to get all current owners of a team (as string IDs)
    def get_owners(team):
        owners = set()
        for uid, pdata in players.items():
            for t in pdata.get("teams", []):
                if t["team"] == team:
                    main_owner = str(t["ownership"].get("main_owner"))
                    if main_owner:
                        owners.add(main_owner)
                    for co in t["ownership"].get("split_with", []):
                        owners.add(str(co))
        return list(owners)

    # --- Pending Requests (what would happen if accepted) ---
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

    # --- Resolved Requests (accepted/declined/expired) ---
    resolved_requests = []
    for log_item in log:
        team = log_item.get("team")
        owners = get_owners(team)
        requester_id = str(log_item.get("requester_id"))
        status = log_item.get("status")

        # Work with a *copy* so we don't affect players.json
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

    # Sort: pending first, then resolved, newest resolved first
    resolved_requests = sorted(resolved_requests, key=lambda x: safe_int(x.get("timestamp", 0)), reverse=True)
    pending_requests = sorted(pending_requests, key=lambda x: safe_int(x.get("timestamp", 0)))
    
    return jsonify({
        "pending": pending_requests,
        "resolved": resolved_requests
    })

@app.route('/api/split_requests/force', methods=['POST'])
def api_split_requests_force():
    data = request.json
    req_id = data.get('request_id')
    action = data.get('action')
    if not req_id or action not in ("forceaccept", "forcedecline", "delete"):
        return jsonify({"ok": False, "error": "Bad params"})
    
    # Paths
    split_pending_path = os.path.join(BASE_DIR, "JSON", "split_requests.json")
    split_log_path = os.path.join(BASE_DIR, "JSON", "split_requests_log.json")
    
    # Load files
    with open(split_pending_path, "r") as f:
        pending = json.load(f)
    with open(split_log_path, "r") as f:
        log = json.load(f)
    
    # Handle
    if action == "delete":
        # Remove from pending only
        if req_id in pending:
            del pending[req_id]
            with open(split_pending_path, "w") as f:
                json.dump(pending, f, indent=2)
            return jsonify({"ok": True, "msg": "Request deleted."})
        return jsonify({"ok": False, "error": "Request not found in pending."})
    
    # Accept/Decline: Move to log with status
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
    # Write back both files
    with open(split_pending_path, "w") as f:
        json.dump(pending, f, indent=2)
    with open(split_log_path, "w") as f:
        json.dump(log, f, indent=2)
    return jsonify({"ok": True, "msg": f"Request {status}."})


# --- TEAM OWNERSHIP ENDPOINTS ---
@app.route('/api/ownerships')
def api_ownerships():
    try:
        with open(PLAYERS_JSON, "r") as f:
            players = json.load(f)
        with open(TEAMS_JSON, "r") as f:
            teams = json.load(f)
        verified_map = get_verified_map()
        verified_names = list(verified_map.keys())

        ownerships = []
        for country in teams:
            main_owner_name = None
            co_owner_names = set()
            # Find main owner and co-owners for this country
            for user_id, pdata in players.items():
                for team_entry in pdata.get("teams", []):
                    if isinstance(team_entry, dict) and team_entry.get("team") == country and "ownership" in team_entry:
                        ownership = team_entry["ownership"]
                        # Main owner
                        if ownership.get("main_owner") == user_id:
                            main_owner_name = pdata.get("display_name") or pdata.get("username") or user_id
                            for split_id in ownership.get("split_with", []):
                                if split_id in players:
                                    co_owner_name = players[split_id].get("display_name") or players[split_id].get("username") or split_id
                                    co_owner_names.add(co_owner_name)
            owners_list = []
            if main_owner_name:
                owners_list.append(main_owner_name)
            for name in co_owner_names:
                if name != main_owner_name:
                    owners_list.append(name)
            ownerships.append({
                "country": country,
                "owners": owners_list
            })
        return jsonify({"ownerships": ownerships, "verified_users": verified_names})
    except Exception as e:
        return jsonify({"ownerships": [], "verified_users": [], "error": str(e)})

@app.route('/api/ownership/update', methods=['POST'])
def api_ownership_update():
    req = request.get_json()
    country = req.get("country")
    owners = req.get("owners", [])
    action = req.get("action", "reassign")

    try:
        with open(VERIFIED_JSON, "r") as f:
            verified = json.load(f)["verified_users"]
        verified_map = {u["habbo_name"]: u["discord_id"] for u in verified}

        with open(PLAYERS_JSON, "r") as f:
            players = json.load(f)

        def ownership_entry(main_owner_id, split_ids):
            return {
                "team": country,
                "ownership": {
                    "main_owner": main_owner_id,
                    "split_with": split_ids
                }
            }

        if action == "reassign":
            for pdata in players.values():
                if "teams" in pdata:
                    pdata["teams"] = [t for t in pdata["teams"] if (t.get("team") if isinstance(t, dict) else t) != country]
            if owners:
                main_habbo = owners[0]
                main_id = verified_map.get(main_habbo)
                co_habbos = owners[1:]
                co_ids = [verified_map[n] for n in co_habbos if n in verified_map]
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
            main_id = None
            for uid, pdata in players.items():
                for t in pdata.get("teams", []):
                    if isinstance(t, dict) and t.get("team") == country and t.get("ownership", {}).get("main_owner") == uid:
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
                    t["ownership"]["split_with"] = list(current_split.union(new_co_ids))
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

# --- COGS ENDPOINTS ---
@app.route('/api/cogs')
def api_cogs():
    import glob
    cogs = []
    cogs_status_file = os.path.join(BASE_DIR, "JSON", "cogs_status.json")
    loaded = []
    if os.path.exists(cogs_status_file):
        with open(cogs_status_file) as f:
            loaded = json.load(f).get("loaded", [])
        loaded = [cog.split('.')[-1] for cog in loaded]  # Keep only the last part, e.g. Betting
    for cog_path in glob.glob(os.path.join(COGS_PATH, "*.py")):
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

@app.route('/api/cogs/action', methods=['POST'])
def api_cogs_action():
    req = request.get_json()
    cog = req.get("cog")
    action = req.get("action")  # "reload", "unload", "load"
    content = f"wc {action} {cog}"
    r = requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
    if r.status_code == 204:
        return jsonify({"ok": True})
    else:
        return jsonify({"ok": False, "error": f"Webhook status: {r.status_code}"})
        
    
# --- BETS ENDPOINTS ---
@app.route('/api/bets')
def api_bets():
    # Load player name mapping
    with open(os.path.join(BASE_DIR, "JSON", "players.json")) as pf:
        players = json.load(pf)
    with open(os.path.join(BASE_DIR, "JSON", "bets.json")) as bf:
        bets = json.load(bf)

    def habbo_name(discord_id):
        return players.get(str(discord_id), {}).get("display_name", "")

    # Enrich each bet with up-to-date Habbo names
    enriched_bets = []
    for bet in bets:
        # Defensive fallback to bet["option1_user_name"] if player mapping fails
        bet = bet.copy()
        if "option1_user_id" in bet:
            bet["option1_user_name"] = habbo_name(bet["option1_user_id"]) or bet.get("option1_user_name", "")
        if "option2_user_id" in bet:
            bet["option2_user_name"] = habbo_name(bet["option2_user_id"]) or bet.get("option2_user_name", "")
        enriched_bets.append(bet)
    return jsonify(enriched_bets)

@app.route('/api/bets/settle', methods=['POST'])
def api_bets_settle():
    data = request.get_json()
    bet_id = data.get("bet_id")
    winner_id = data.get("winner_id")
    if not bet_id or not winner_id:
        return jsonify({"ok": False, "error": "Missing parameters"})
    # Send Discord webhook message
    payload = {
        "content": f"!bet settle {bet_id} {winner_id}"
    }
    resp = requests.post(BETS_WEBHOOK_URL, json=payload)
    if resp.status_code in (200, 204):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": f"Webhook failed: {resp.text}"})

# --- VERIFIED ENDPOINTS ---
@app.route('/api/verified')
def api_verified():
    with open(os.path.join(BASE_DIR, "JSON", "verified.json")) as vf:
        verified = json.load(vf)["verified_users"]
    return jsonify(verified)

# --- BACKUP HELPER AND ENDPOINTS
def _list_json_files():
    return sorted(glob.glob(os.path.join(JSON_DIR, "*.json")))

def _backup_one(json_path):
    base = os.path.splitext(os.path.basename(json_path))[0]  # e.g., "players"
    target_dir = os.path.join(BACKUPS_DIR, base)
    os.makedirs(target_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = f"{base}__{ts}.json"
    out_path = os.path.join(target_dir, out_name)
    shutil.copy2(json_path, out_path)

    # Retention: keep newest BACKUP_RETENTION
    existing = sorted(glob.glob(os.path.join(target_dir, f"{base}__*.json")))
    excess = len(existing) - BACKUP_RETENTION
    for p in existing[:max(0, excess)]:
        try:
            os.remove(p)
        except Exception:
            pass
    return out_path

def backup_all_json():
    made = []
    for p in _list_json_files():
        try:
            made.append(_backup_one(p))
        except Exception as e:
            with open(HEALTH_LOG, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Backup failed for {p}: {e}\n")
    if made:
        with open(HEALTH_LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Backed up {len(made)} JSON file(s).\n")
    return made

@app.route('/api/backups')
def api_backups_list():
    # Structure: folders -> [{name, display, count, files:[{name, rel, bytes, mtime}]}]
    result = []
    # Derive folders from actual JSON files to keep UX tidy
    for src in _list_json_files():
        basefile = os.path.basename(src)          # e.g. players.json
        base = os.path.splitext(basefile)[0]      # e.g. players
        folder = os.path.join(BACKUPS_DIR, base)
        files = []
        if os.path.isdir(folder):
            for fn in sorted(os.listdir(folder)):
                fp = os.path.join(folder, fn)
                if not os.path.isfile(fp):
                    continue
                st = os.stat(fp)
                files.append({
                    "name": fn,
                    "rel": f"{base}/{fn}",
                    "bytes": st.st_size,
                    "mtime": int(st.st_mtime)
                })
        files = sorted(files, key=lambda x: x["mtime"], reverse=True)
        result.append({
            "name": base,
            "display": basefile,
            "count": len(files),
            "files": files
        })
    # Show any extra folders (if any exist without a source JSON)
    for base in sorted(os.listdir(BACKUPS_DIR)):
        folder = os.path.join(BACKUPS_DIR, base)
        if not os.path.isdir(folder):
            continue
        display = f"{base}.json"
        if not any(f["name"] == base for f in result):
            files = []
            for fn in sorted(os.listdir(folder)):
                fp = os.path.join(folder, fn)
                if os.path.isfile(fp):
                    st = os.stat(fp)
                    files.append({
                        "name": fn,
                        "rel": f"{base}/{fn}",
                        "bytes": st.st_size,
                        "mtime": int(st.st_mtime)
                    })
            files = sorted(files, key=lambda x: x["mtime"], reverse=True)
            result.append({
                "name": base, "display": display, "count": len(files), "files": files
            })
    return jsonify({"folders": sorted(result, key=lambda x: x["display"].lower())})

@app.route('/api/backups/download')
def api_backups_download():
    rel = request.args.get("rel", "").strip()
    # Sanitize
    full_path = os.path.normpath(os.path.join(BACKUPS_DIR, rel))
    if not full_path.startswith(os.path.abspath(BACKUPS_DIR)) or not os.path.isfile(full_path):
        return ("Not found", 404)
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    return send_from_directory(directory, filename, as_attachment=True)




@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    pip_install_requirements()
    print("Starting Flask admin panel at http://localhost:5000 ...")
    start_bot()

    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False), daemon=True)
    flask_thread.start()

    last_backup_time = 0
    bot_crash_count = 0
    last_crash_time = None

    try:
        while True:
            time.sleep(10)
            
            now = time.time()
            if now - last_backup_time >= BACKUP_INTERVAL_SECS:
                backup_all_json()
                last_backup_time = now
            
            if not is_bot_running() and not manual_stop:
                now = time.time()
                if last_crash_time and now - last_crash_time < 60:
                    bot_crash_count += 1
                else:
                    bot_crash_count = 1
                last_crash_time = now
                if bot_crash_count > 3:
                    with open(HEALTH_LOG, "a") as f:
                        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Bot crashed too many times, halting restart.\n")
                    print("Bot has crashed 3 times within a minute. Not restarting automatically. Check logs!")
                    break
                print("Bot process not running. Attempting to restart...")
                start_bot()
                with open(HEALTH_LOG, "a") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Bot process not running, restarted.\n")
            usage = get_bot_resource_usage()
            if usage['mem_mb'] is not None and usage['cpu_percent'] is not None:
                write_health_log(usage['mem_mb'], usage['cpu_percent'])
    except KeyboardInterrupt:
        print("Shutting down launcher and bot...")
        stop_bot()
        os._exit(0)
