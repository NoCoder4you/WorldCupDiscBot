
from flask import Blueprint, jsonify, send_from_directory
import os, json, psutil, time

def create_public_routes(context):
    BASE_DIR = context["BASE_DIR"]
    is_bot_running = context["is_bot_running"]
    get_bot_resource_usage = context["get_bot_resource_usage"]
    bot_last_start_ref = context["bot_last_start_ref"]
    bot_last_stop_ref = context["bot_last_stop_ref"]

    routes_public = Blueprint("routes_public", __name__)

    @routes_public.route('/api/ping')
    def api_ping():
        return jsonify({
            "status": "ok",
            "bot_running": is_bot_running(),
            "pid": context["bot_process"].pid if is_bot_running() else None
        })

    @routes_public.route('/api/system')
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

    @routes_public.route('/api/guilds')
    def api_guilds():
        try:
            with open(os.path.join(BASE_DIR, "JSON", "guilds.json"), "r") as f:
                data = json.load(f)
            return jsonify(data)
        except Exception:
            return jsonify({"guild_count": 0, "guilds": []})

    @routes_public.route('/api/players')
    def api_players():
        with open(os.path.join(BASE_DIR, "JSON", "players.json")) as f:
            players = json.load(f)
        return jsonify(players)

    @routes_public.route('/api/verified')
    def api_verified():
        with open(os.path.join(BASE_DIR, "JSON", "verified.json")) as vf:
            verified = json.load(vf).get("verified_users", [])
        return jsonify(verified)

    @routes_public.route('/api/bets')
    def api_bets():
        with open(os.path.join(BASE_DIR, "JSON", "players.json")) as pf:
            players = json.load(pf)
        with open(os.path.join(BASE_DIR, "JSON", "bets.json")) as bf:
            bets = json.load(bf)
        def habbo_name(discord_id):
            return players.get(str(discord_id), {}).get("display_name", "")
        enriched_bets = []
        for bet in bets:
            bet = bet.copy()
            if "option1_user_id" in bet:
                bet["option1_user_name"] = habbo_name(bet.get("option1_user_id")) or bet.get("option1_user_name", "")
            if "option2_user_id" in bet:
                bet["option2_user_name"] = habbo_name(bet.get("option2_user_id")) or bet.get("option2_user_name", "")
            enriched_bets.append(bet)
        return jsonify(enriched_bets)

    @routes_public.route('/')
    def index():
        return send_from_directory('static', 'static/index.html')

    @routes_public.route('/<path:path>')
    def static_proxy(path):
        return send_from_directory('static', path)

    return routes_public
