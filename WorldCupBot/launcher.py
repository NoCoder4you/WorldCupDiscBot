
#!/usr/bin/env python3
import os, sys, time, json, signal, subprocess, logging, threading, collections
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Deque
import psutil
from flask import Flask, jsonify

# ---------- Paths & Config ----------
HERE = Path(__file__).resolve().parent
BASE_DIR = HERE  # repo root
STATIC_DIR = BASE_DIR / "static"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = BASE_DIR / "config.json"
CONFIG = {}
ADMIN_PASSWORD = (os.getenv('ADMIN_PASSWORD') or str(CONFIG.get('admin_password', CONFIG.get('ADMIN_PASSWORD', ''))))
if CONFIG_PATH.exists():
    try:
        CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[launcher] Failed to read config.json: {e}", file=sys.stderr)

FLASK_SECRET = CONFIG.get("flask_secret") or os.environ.get("FLASK_SECRET") or "dev-secret-change-me"
ADMIN_PASSWORD = CONFIG.get("admin_password") or os.environ.get("ADMIN_PASSWORD") or ""

# Optionally tell the QueueWorker where to log admin actions
AUDIT_CHANNEL_ID = CONFIG.get("audit_channel_id")

# ---------- Logging ----------
def _make_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fh = RotatingFileHandler(LOG_DIR / filename, maxBytes=2_000_000, backupCount=3)
    fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.propagate = False
    return logger

log_bot = _make_logger("discord.bot", "bot.log")
log_health = _make_logger("launcher", "health.log")

# ---------- Bot process management ----------
bot_process: Optional[subprocess.Popen] = None
bot_last_start_ref = {"value": None}
bot_last_stop_ref = {"value": None}
_manual_stop_flag = False  # True when stop_bot() intentionally stops the process
AUTO_START = bool(CONFIG.get("auto_start_bot", True))

# Crash policy
CRASH_WINDOW_SEC = int(CONFIG.get("crash_window_sec", 60))     # track crashes within this window
CRASH_MAX = int(CONFIG.get("crash_max", 3))                    # max crashes allowed per window
CRASH_BACKOFF_SEC = int(CONFIG.get("crash_backoff_sec", 60))   # wait after a crash before restart attempt
NO_AUTORESTART_COOLDOWN_SEC = int(CONFIG.get("no_autorestart_cooldown_sec", 300))  # after hitting limit

_crash_times: Deque[float] = collections.deque(maxlen=100)
_no_autorestart_until = 0.0

def get_crash_status():
    now = time.time()
    # _crash_times and _no_autorestart_until already exist in the launcher
    crash_count = len(_crash_times)
    cooldown_active = _no_autorestart_until > now
    return {
        "crash_count": crash_count,
        "cooldown_active": cooldown_active,
        "cooldown_until": _no_autorestart_until,
        "window_seconds": CRASH_WINDOW_SEC,
        "max_crashes": CRASH_MAX,
    }

def is_bot_running() -> bool:
    global bot_process
    if not bot_process:
        return False
    return bot_process.poll() is None

def _spawn_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return env

def start_bot() -> bool:
    global bot_process, bot_last_start_ref, _manual_stop_flag
    if is_bot_running():
        log_bot.info("start_bot: already running")
        return True
    try:
        py = sys.executable
        bot_py = str((BASE_DIR / "bot.py").resolve())
        bot_process = subprocess.Popen(
            [py, bot_py],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_spawn_env()
        )
        _manual_stop_flag = False
        bot_last_start_ref["value"] = time.time()
        log_bot.info(f"Started bot.py with PID {bot_process.pid}")
        return True
    except Exception as e:
        log_bot.error(f"Failed to start bot: {e}")
        return False

def stop_bot() -> bool:
    global bot_process, bot_last_stop_ref, _manual_stop_flag
    if not is_bot_running():
        log_bot.info("stop_bot: not running")
        bot_last_stop_ref["value"] = time.time()
        return True
    try:
        _manual_stop_flag = True
        pid = bot_process.pid
        bot_process.terminate()
        try:
            bot_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log_bot.warning("terminate timeout, sending kill")
            bot_process.kill()
            bot_process.wait(timeout=5)
        log_bot.info(f"Stopped bot.py PID {pid}")
        bot_last_stop_ref["value"] = time.time()
        return True
    except Exception as e:
        log_bot.error(f"Failed to stop bot: {e}")
        return False
    finally:
        bot_process = None

def restart_bot() -> bool:
    ok1 = stop_bot()
    time.sleep(1.0)
    ok2 = start_bot()
    return ok1 and ok2

def get_bot_resource_usage():
    """Return cpu_percent and mem_mb for the bot process if running."""
    if not is_bot_running():
        return {"cpu_percent": 0.0, "mem_mb": None}
    try:
        p = psutil.Process(bot_process.pid)
        with p.oneshot():
            cpu = p.cpu_percent(interval=0.05)
            mem = p.memory_info().rss / 1024 / 1024
        return {"cpu_percent": float(cpu), "mem_mb": float(mem)}
    except Exception:
        return {"cpu_percent": 0.0, "mem_mb": None}

# ---------- Watchdog thread ----------
def _prune_crashes(now: float):
    # Keep only crash times within the rolling window
    while _crash_times and (now - _crash_times[0]) > CRASH_WINDOW_SEC:
        _crash_times.popleft()

def _record_crash(now: float):
    _crash_times.append(now)
    _prune_crashes(now)

def _watchdog_loop():
    global _no_autorestart_until
    # Boot-time: optionally start bot
    if AUTO_START and not is_bot_running():
        start_bot()
    while True:
        time.sleep(2.0)
        now = time.time()

        # Cooldown after hitting crash limit
        if _no_autorestart_until > 0 and now < _no_autorestart_until:
            continue
        elif _no_autorestart_until > 0 and now >= _no_autorestart_until:
            log_health.info("Cooldown ended - auto-restart re-enabled")
            _no_autorestart_until = 0

        if is_bot_running():
            continue

        # If it is not running and we did not stop it intentionally - treat as crash
        if not _manual_stop_flag:
            _record_crash(now)
            if len(_crash_times) >= CRASH_MAX and (_crash_times[-1] - _crash_times[0]) <= CRASH_WINDOW_SEC:
                log_health.error(f"Bot has crashed {len(_crash_times)} times within {CRASH_WINDOW_SEC}s. Not restarting automatically. Check logs!")
                _no_autorestart_until = now + NO_AUTORESTART_COOLDOWN_SEC
                continue

            log_health.info("Bot process not running. Attempting to restart...")
            ok = start_bot()
            if not ok:
                log_health.error("Restart attempt failed.")
            else:
                # small backoff to avoid tight loops
                time.sleep(CRASH_BACKOFF_SEC)

# ---------- Flask ----------
app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),   # STATIC_DIR = BASE_DIR / "static"
    static_url_path=""               # serve static at /
)

app.secret_key = FLASK_SECRET

# Provide these to route factories
CTX = {
    "BASE_DIR": str(BASE_DIR),
    "is_bot_running": is_bot_running,
    "start_bot": start_bot,
    "stop_bot": stop_bot,
    "restart_bot": restart_bot,
    "get_bot_resource_usage": get_bot_resource_usage,
    "LOG_PATHS": {
        "bot": str(LOG_DIR / "bot.log"),
        "health": str(LOG_DIR / "health.log"),
    },
    "bot_process": None,  # filled after start
    "bot_last_start_ref": bot_last_start_ref,
    "bot_last_stop_ref": bot_last_stop_ref,
    "ADMIN_PASSWORD": ADMIN_PASSWORD,
}

# Import and register blueprints
from routes_public import create_public_routes
try:
    from routes_admin import create_admin_routes
except Exception:
    create_admin_routes = None

root_bp, api_bp = create_public_routes(CTX)
app.register_blueprint(root_bp)
app.register_blueprint(api_bp)

if create_admin_routes:
    admin_bp = create_admin_routes(CTX)
    app.register_blueprint(admin_bp)

# Debug route map
@app.get("/debug/routes")
def debug_routes():
    def row(r):
        methods = ",".join(sorted(r.methods - {"HEAD","OPTIONS"}))
        return {"rule": r.rule, "methods": methods, "endpoint": r.endpoint}
    return jsonify(sorted([row(r) for r in app.url_map.iter_rules()], key=lambda x: x["rule"]))

# ---------- Signals ----------
def _handle_sigterm(signum, frame):
    log_health.info("SIGTERM received, stopping bot and exiting...")
    try:
        stop_bot()
    finally:
        sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)

# ---------- Start watchdog thread ----------
_watchdog = threading.Thread(target=_watchdog_loop, name="bot-watchdog", daemon=True)
_watchdog.start()

# ---------- Main ----------
if __name__ == "__main__":
    host = CONFIG.get("flask_host", "0.0.0.0")
    port = int(CONFIG.get("flask_port", 5000))
    debug = bool(CONFIG.get("flask_debug", False))
    log_health.info(f"Launcher starting on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)
