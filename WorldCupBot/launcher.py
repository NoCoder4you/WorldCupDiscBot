
import os
import subprocess
import threading
import time
import psutil
import json
from flask import Flask
from routes_public import create_public_routes
from routes_admin import create_admin_routes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except Exception as e:
    print(f"Failed to load config.json: {e}")
    CONFIG = {}

DISCORD_WEBHOOK_URL = CONFIG.get("DISCORD_WEBHOOK_URL", "").strip()
BETS_WEBHOOK_URL = CONFIG.get("BETS_WEBHOOK_URL", "").strip()
ADMIN_PASSWORD = CONFIG.get("ADMIN_PASSWORD", "").strip()
FLASK_SECRET = CONFIG.get("FLASK_SECRET", "change-me-super-secret")

bot_process = None
manual_stop_ref = {"value": False}
bot_last_start_ref = {"value": None}
bot_last_stop_ref = {"value": None}

def log_health_line(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {msg}\n"
    with open(HEALTH_LOG, "a") as f:
        f.write(line)
    try:
        if os.path.getsize(HEALTH_LOG) > HEALTH_LOG_MAX_SIZE:
            with open(HEALTH_LOG, "r") as f:
                lines = f.readlines()[-500:]
            with open(HEALTH_LOG, "w") as f:
                f.writelines(lines)
    except Exception:
        pass

def pip_install_requirements():
    print("Installing requirements from requirements.txt with python -m pip...")
    log_health_line("pip install start")
    try:
        subprocess.run([PYTHON_BIN, '-m', 'pip', 'install', '-r', REQUIREMENTS], check=True)
        log_health_line("pip install success")
    except subprocess.CalledProcessError as e:
        log_health_line(f"pip install failed - {e}")

def start_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        return False
    bot_process = subprocess.Popen([PYTHON_BIN, BOT_FILE])
    bot_last_start_ref["value"] = time.time()
    bot_last_stop_ref["value"] = None
    print(f"Started bot.py with PID {bot_process.pid}")
    log_health_line(f"bot start PID={bot_process.pid}")
    return True

def stop_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        print("Stopping bot.py...")
        bot_process.terminate()
        try:
            bot_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("Bot did not exit cleanly, killing.")
            bot_process.kill()
        print("Bot stopped.")
        bot_last_stop_ref["value"] = time.time()
        log_health_line("bot stop")
        return True
    print("Bot was not running.")
    if bot_last_stop_ref["value"] is None:
        bot_last_stop_ref["value"] = time.time()
    return False

def restart_bot():
    print("Restarting bot.py...")
    log_health_line("bot restart requested")
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
    log_health_line(f"Memory: {mem_mb:.2f} MB | CPU: {cpu_percent:.1f}%")

def run_flask():
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET

    context = {
        "BASE_DIR": BASE_DIR,
        "LOG_PATHS": LOG_PATHS,
        "DISCORD_WEBHOOK_URL": DISCORD_WEBHOOK_URL,
        "BETS_WEBHOOK_URL": BETS_WEBHOOK_URL,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "bot_process": bot_process,
        "manual_stop_ref": manual_stop_ref,
        "bot_last_start_ref": bot_last_start_ref,
        "bot_last_stop_ref": bot_last_stop_ref,
        "start_bot": start_bot,
        "stop_bot": stop_bot,
        "restart_bot": restart_bot,
        "is_bot_running": is_bot_running,
        "get_bot_resource_usage": get_bot_resource_usage,
    }

    app.register_blueprint(create_public_routes(context))
    app.register_blueprint(create_admin_routes(context))

    print("Starting Flask admin panel at http://0.0.0.0:5000 ...")
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    # No git pull here - updater runs before this script
    pip_install_requirements()
    start_bot()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    bot_crash_count = 0
    last_crash_time = None

    try:
        while True:
            time.sleep(10)
            now = time.time()

            if not is_bot_running() and not manual_stop_ref["value"]:
                if last_crash_time and now - last_crash_time < 60:
                    bot_crash_count += 1
                else:
                    bot_crash_count = 1
                last_crash_time = now
                if bot_crash_count > 3:
                    log_health_line("Bot crashed >3 times in 60s - halting auto-restart")
                    print("Bot has crashed 3 times within a minute. Not restarting automatically. Check logs!")
                    break
                print("Bot process not running. Attempting to restart...")
                start_bot()
                log_health_line("Bot process not running, restarted.")

            usage = get_bot_resource_usage()
            if usage['mem_mb'] is not None and usage['cpu_percent'] is not None:
                write_health_log(usage['mem_mb'], usage['cpu_percent'])
    except KeyboardInterrupt:
        print("Shutting down launcher and bot...")
        stop_bot()
        os._exit(0)
