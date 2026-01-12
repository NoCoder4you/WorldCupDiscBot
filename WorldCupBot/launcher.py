#!/usr/bin/env python3
import os, sys, time, json, signal, subprocess, logging, threading, collections
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Deque, TextIO
import psutil
from flask import Flask

# ---------- Paths & Config ----------
HERE = Path(__file__).resolve().parent
BASE_DIR = HERE
STATIC_DIR = BASE_DIR / "static"
LOG_DIR = BASE_DIR / "LOGS"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = BASE_DIR / "config.json"
CONFIG = {}
try:
    if CONFIG_PATH.is_file():
        CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
except Exception as e:
    print(f"[launcher] Failed to read config.json: {e}", file=sys.stderr)

# Flask secret pulled from env or config (supports both key casings)
FLASK_SECRET = (
    os.getenv("FLASK_SECRET") or
    str(CONFIG.get("flask_secret", CONFIG.get("FLASK_SECRET", "")))
)

# ---------- Logging ----------
def _resolve_log_level(value: str) -> int:
    if not value:
        return logging.INFO
    upper = value.strip().upper()
    return logging._nameToLevel.get(upper, logging.INFO)

LOG_LEVEL = _resolve_log_level(os.getenv("LOG_LEVEL") or str(CONFIG.get("LOG_LEVEL", "")))

def _mk_logger(name, fname):
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    fh = RotatingFileHandler(LOG_DIR / fname, maxBytes=1_000_000, backupCount=3)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(module)s.%(funcName)s:%(lineno)d: %(message)s"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger

log = _mk_logger("launcher", "launcher.log")
log_bot = _mk_logger("bot", "bot.log")
log_health = _mk_logger("health", "health.log")

# ---------- Bot process management ----------
bot_process: Optional[subprocess.Popen] = None
bot_log_fp: Optional[TextIO] = None
bot_last_start_ref = {"value": None}
bot_last_stop_ref = {"value": None}
_manual_stop_flag = False  # True when stop_bot() intentionally stops the process
AUTO_START = bool(CONFIG.get("auto_start_bot", True))

# Crash policy
CRASH_WINDOW_SEC = int(CONFIG.get("crash_window_seconds", 60))
MAX_CRASHES_IN_WINDOW = int(CONFIG.get("max_crashes_in_window", 3))
RETRY_COOLDOWN_SEC = int(CONFIG.get("retry_cooldown_seconds", 60))
_crash_times: Deque[float] = collections.deque(maxlen=100)
_cooldown_until = 0.0

def _record_crash(ts=None):
    global _cooldown_until
    t = ts or time.time()
    _crash_times.append(t)
    # prune older than window
    while _crash_times and (t - _crash_times[0]) > CRASH_WINDOW_SEC:
        _crash_times.popleft()
    if len(_crash_times) >= MAX_CRASHES_IN_WINDOW:
        _cooldown_until = t + RETRY_COOLDOWN_SEC
        log.warning(f"Crash threshold reached - cooldown until {time.strftime('%H:%M:%S', time.localtime(_cooldown_until))}")

def _spawn_env():
    env = os.environ.copy()
    env["BOT_LOG_STDOUT_ONLY"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env

def is_bot_running() -> bool:
    global bot_process
    if bot_process and bot_process.poll() is None:
        return True
    # fallback to psutil lookup for resilience
    for p in psutil.process_iter(["pid","name","cmdline"]):
        try:
            if p.is_running() and "python" in (p.info.get("name") or "").lower():
                cmd = " ".join(p.info.get("cmdline") or [])
                if "bot.py" in cmd and str(BASE_DIR) in cmd:
                    return True
        except Exception:
            continue
    return False

def start_bot() -> bool:
    global bot_process, bot_log_fp, _manual_stop_flag
    if is_bot_running():
        log_bot.info("start_bot requested but bot already running")
        return True
    if time.time() < _cooldown_until:
        log_bot.warning("start_bot inhibited by cooldown")
        return False
    py = sys.executable or "python3"
    bot_py = str(BASE_DIR / "bot.py")
    try:
        bot_log_fp = open(LOG_DIR / "bot.log", "a", encoding="utf-8")
        bot_process = subprocess.Popen(
            [py, bot_py],
            cwd=str(BASE_DIR),
            stdout=bot_log_fp,
            stderr=bot_log_fp,
            env=_spawn_env()
        )
        _manual_stop_flag = False
        bot_last_start_ref["value"] = time.time()
        CTX["bot_process"] = bot_process
        log_bot.info(f"Started bot.py with PID {bot_process.pid}")
        return True
    except Exception as e:
        if bot_log_fp:
            bot_log_fp.close()
            bot_log_fp = None
        log_bot.error(f"Failed to start bot: {e}")
        return False

def stop_bot() -> bool:
    global bot_process, bot_log_fp, _manual_stop_flag
    _manual_stop_flag = True
    try:
        if bot_process and bot_process.poll() is None:
            bot_process.terminate()
            try:
                bot_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                bot_process.kill()
        else:
            # Try psutil kill if we lost the handle
            for p in psutil.process_iter(["pid","name","cmdline"]):
                try:
                    cmd = " ".join(p.info.get("cmdline") or [])
                    if p.is_running() and "bot.py" in cmd and str(BASE_DIR) in cmd:
                        p.terminate()
                        try:
                            p.wait(timeout=10)
                        except psutil.TimeoutExpired:
                            p.kill()
                except Exception:
                    pass
        bot_last_stop_ref["value"] = time.time()
        bot_process = None
        if bot_log_fp:
            bot_log_fp.close()
            bot_log_fp = None
        CTX["bot_process"] = None
        log_bot.info("Stopped bot.py")
        return True
    except Exception as e:
        log_bot.error(f"Failed to stop bot: {e}")
        return False

def restart_bot() -> bool:
    ok1 = stop_bot()
    ok2 = start_bot()
    return ok1 and ok2

def get_bot_resource_usage():
    try:
        # launcher process usage
        p = psutil.Process(os.getpid())
        cpu = p.cpu_percent(interval=0.1)
        mem = p.memory_info().rss
        # system
        cpu_total = psutil.cpu_percent(interval=0.1)
        mem_vm = psutil.virtual_memory().percent
        disk = psutil.disk_usage(str(BASE_DIR)).percent
        return {
            "cpu_self": cpu,
            "mem_self_bytes": mem,
            "cpu_total": cpu_total,
            "mem_total_percent": mem_vm,
            "disk_percent": disk,
        }
    except Exception:
        return {}

def get_crash_status():
    now = time.time()
    return {
        "crash_count": len([t for t in _crash_times if now - t <= CRASH_WINDOW_SEC]),
        "cooldown_active": now < _cooldown_until,
        "cooldown_until": _cooldown_until,
        "window_seconds": CRASH_WINDOW_SEC,
        "max_crashes": MAX_CRASHES_IN_WINDOW,
    }

# ---------- Flask app ----------
from routes_public import create_public_routes
from routes_admin import create_admin_routes

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
# Session secret
try:
    if FLASK_SECRET:
        app.secret_key = FLASK_SECRET
    else:
        sec_path = BASE_DIR / ".flask_secret"
        if sec_path.exists():
            app.secret_key = sec_path.read_text().strip()
        else:
            import secrets
            k = secrets.token_hex(32)
            sec_path.write_text(k)
            app.secret_key = k
except Exception as e:
    print(f"[launcher] Failed to set Flask secret key: {e}", file=sys.stderr)

# Shared context for blueprints
CTX = {
    "BASE_DIR": str(BASE_DIR),
    "CONFIG": CONFIG,
    "is_bot_running": is_bot_running,
    "start_bot": start_bot,
    "stop_bot": stop_bot,
    "restart_bot": restart_bot,
    "get_bot_resource_usage": get_bot_resource_usage,
    "get_crash_status": get_crash_status,
    "bot_last_start_ref": bot_last_start_ref,
    "bot_last_stop_ref": bot_last_stop_ref,
    "bot_process": None,

    "LOG_PATHS": {
        "bot": str(LOG_DIR / "bot.log"),
        "health": str(LOG_DIR / "health.log"),
        "launcher": str(LOG_DIR / "launcher.log"),
    }
}

# Register routes
for bp in create_public_routes(CTX):
    app.register_blueprint(bp)
app.register_blueprint(create_admin_routes(CTX))

@app.get("/debug/routes")
def debug_routes():
    out = []
    for r in app.url_map.iter_rules():
        out.append({"rule": str(r), "methods": sorted(list(r.methods - {'HEAD','OPTIONS'}))})
    return {"routes": out}

# ---------- Watchdog ----------
def _watchdog_loop():
    global bot_process
    # Auto start if configured
    if AUTO_START:
        start_bot()
    while True:
        try:
            time.sleep(2.0)
            running = is_bot_running()
            if running:
                continue
            # not running
            # attempt restart if not manual stop and not in cooldown
            if not _manual_stop_flag:
                now = time.time()
                if now >= _cooldown_until:
                    log.warning("Bot not running - attempting restart")
                    ok = start_bot()
                    if not ok:
                        _record_crash(now)
                else:
                    # still cooling down
                    pass
        except Exception:
            time.sleep(2.0)

def _handle_sigterm(sig, frame):
    log.info("SIGTERM received - stopping bot and exiting")
    try:
        stop_bot()
    finally:
        os._exit(0)

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
