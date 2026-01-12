import os
import json
import logging
from typing import List

import discord
from discord.ext import commands

# -------------------- Paths & Config --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COGS_DIR = os.path.join(BASE_DIR, "COGS")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_DIR = os.path.join(BASE_DIR, "LOGS")
LOG_PATH = os.path.join(LOG_DIR, "bot.log")

JSON_DIR = os.path.join(BASE_DIR, "JSON")
COGS_STATUS_PATH = os.path.join(JSON_DIR, "cogs_status.json")

os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(COGS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# -------------------- Logging --------------------
def _resolve_log_level(value: str) -> int:
    if not value:
        return logging.INFO
    upper = value.strip().upper()
    return logging._nameToLevel.get(upper, logging.INFO)

LOG_LEVEL = _resolve_log_level(os.getenv("LOG_LEVEL", ""))

_file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
_file_handler.setLevel(LOG_LEVEL)
_stream_handler = logging.StreamHandler()
_stream_handler.setLevel(LOG_LEVEL)

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(module)s.%(funcName)s:%(lineno)d | %(message)s",
    handlers=[_file_handler, _stream_handler]
)
log = logging.getLogger("WorldCupBot")

# -------------------- Load config --------------------
def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("Failed to load config.json: %s", e)
        return {}

CONFIG = load_config()
BOT_TOKEN = CONFIG.get("BOT_TOKEN", "").strip()

WorldCupAdminCategory = "World Cup Admin"

ADMIN_CATEGORY_NAME = str(CONFIG.get("ADMIN_CATEGORY_NAME", "") or "")
ADMIN_ROLE_NAME = str(CONFIG.get("ADMIN_ROLE_NAME", "") or "")
_admin_ids_raw = CONFIG.get("ADMIN_LOG_CHANNEL_IDS", [])
ADMIN_LOG_CHANNEL_IDS: List[int] = []
for x in _admin_ids_raw:
    try:
        ADMIN_LOG_CHANNEL_IDS.append(int(x))
    except Exception:
        pass

if not BOT_TOKEN:
    log.error("BOT_TOKEN missing in config.json. Exiting.")
    raise SystemExit(2)

# -------------------- Intents --------------------
intents = discord.Intents.all()

# -------------------- Bot --------------------
class WorldCupBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="wc ", intents=intents, help_command=None)
        self.loaded_exts: List[str] = []

    async def setup_hook(self):
        await self.load_all_cogs()
        log.info("setup_hook completed.")

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        await self._post_config_report()

    async def _post_config_report(self):
        for guild in self.guilds:
            msgs = [
                "WorldCupBot is online.",
                f"Config - ADMIN_ROLE_NAME: {ADMIN_ROLE_NAME or 'MISSING'}",
                f"Config - ADMIN_CATEGORY_NAME: {ADMIN_CATEGORY_NAME or 'MISSING'}",
            ]
            if ADMIN_LOG_CHANNEL_IDS:
                parts = []
                for cid in ADMIN_LOG_CHANNEL_IDS:
                    ch = guild.get_channel(cid)
                    parts.append(f"#{ch.name}" if ch else str(cid))
                msgs.append("Config - ADMIN_LOG_CHANNEL_IDS: " + ", ".join(parts))
            else:
                msgs.append("Config - ADMIN_LOG_CHANNEL_IDS: none set (will use fallback)")

            warn = []
            if not ADMIN_ROLE_NAME:
                warn.append("ADMIN_ROLE_NAME not set - admin commands blocked.")
            if not ADMIN_CATEGORY_NAME:
                warn.append("ADMIN_CATEGORY_NAME not set - admin commands blocked.")
            if warn:
                msgs.append("⚠️ " + " ".join(warn))

            await send_discord_log(guild, "\n".join(msgs))

    # --------------- Cog Helpers ---------------
    async def load_all_cogs(self):
        loaded = []
        for fname in os.listdir(COGS_DIR):
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            ext = f"COGS.{fname[:-3]}"
            try:
                await self.load_extension(ext)
                loaded.append(ext)
                log.info("Loaded cog: %s", ext)
            except Exception as e:
                log.exception("Error loading cog %s: %s", ext, e)
        self.loaded_exts = loaded
        self._write_cogs_status(loaded)

    async def reload_cog(self, short_name: str):
        ext = f"COGS.{short_name}"
        try:
            await self.unload_extension(ext)
        except Exception:
            pass
        await self.load_extension(ext)
        self._mark_cog_loaded(short_name, True)
        log.info("Reloaded cog: %s", ext)
        return f"Reloaded {short_name}"

    async def load_cog(self, short_name: str):
        ext = f"COGS.{short_name}"
        await self.load_extension(ext)
        self._mark_cog_loaded(short_name, True)
        log.info("Loaded cog: %s", ext)
        return f"Loaded {short_name}"

    async def unload_cog(self, short_name: str):
        ext = f"COGS.{short_name}"
        await self.unload_extension(ext)
        self._mark_cog_loaded(short_name, False)
        log.info("Unloaded cog: %s", ext)
        return f"Unloaded {short_name}"

    # --- JSON status tracking (shared with Flask) ---
    def _write_cogs_status(self, loaded_exts):
        data = {"loaded": list(loaded_exts)}
        try:
            with open(COGS_STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            log.info("Updated %s with %d loaded cogs.", COGS_STATUS_PATH, len(loaded_exts))
        except Exception as e:
            log.warning("Failed to write cogs_status.json: %s", e)

    def _mark_cog_loaded(self, short_name: str, is_loaded: bool):
        data = {"loaded": []}
        try:
            if os.path.exists(COGS_STATUS_PATH):
                with open(COGS_STATUS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
        except Exception:
            pass
        ext = f"COGS.{short_name}"
        cur = set(data.get("loaded", []))
        if is_loaded:
            cur.add(ext)
        else:
            cur.discard(ext)
        data["loaded"] = sorted(cur)
        try:
            os.makedirs(JSON_DIR, exist_ok=True)
            with open(COGS_STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.warning("Failed to update cogs_status.json: %s", e)

bot = WorldCupBot()

# -------------------- Helpers --------------------
def member_has_role(member: discord.Member, role_name: str) -> bool:
    if not role_name:
        return False
    return any(r.name == role_name for r in getattr(member, "roles", []))

def in_admin_category(channel: discord.abc.GuildChannel, category_name: str) -> bool:
    if not category_name:
        return False
    if isinstance(channel, discord.Thread):
        parent = channel.parent
        return bool(parent and parent.category and parent.category.name == category_name)
    return bool(getattr(channel, "category", None) and channel.category.name == category_name)

async def get_fallback_log_channels(guild: discord.Guild) -> List[discord.abc.Messageable]:
    chans: List[discord.abc.Messageable] = []
    if ADMIN_LOG_CHANNEL_IDS:
        for cid in ADMIN_LOG_CHANNEL_IDS:
            ch = guild.get_channel(int(cid))
            if ch and isinstance(ch, (discord.TextChannel, discord.Thread)):
                chans.append(ch)
        if chans:
            return chans
    if ADMIN_CATEGORY_NAME:
        for ch in guild.text_channels:
            if ch.category and ch.category.name == ADMIN_CATEGORY_NAME and ch.permissions_for(guild.me).send_messages:
                chans.append(ch)
        if chans:
            return chans
    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        return [guild.system_channel]
    return []

async def send_discord_log(guild: discord.Guild, message: str):
    targets = await get_fallback_log_channels(guild)
    if not targets:
        log.warning("No suitable log channel found in guild %s. Message: %s", guild.name if guild else "?", message)
        return
    for ch in targets:
        try:
            await ch.send(message)
        except Exception:
            pass
    log.info(message)

def admin_only_context():
    async def predicate(ctx: commands.Context):
        if not isinstance(ctx.author, discord.Member):
            await ctx.reply("Must be used in a server.", delete_after=5)
            return False
        if not ADMIN_ROLE_NAME:
            await send_discord_log(ctx.guild, "Admin role not configured in config.json")
            await ctx.reply("Admin role not configured.", delete_after=8)
            return False
        if not ADMIN_CATEGORY_NAME:
            await send_discord_log(ctx.guild, "Admin category not configured in config.json")
            await ctx.reply("Admin category not configured.", delete_after=8)
            return False
        if not member_has_role(ctx.author, ADMIN_ROLE_NAME):
            await ctx.reply(f"You need the {ADMIN_ROLE_NAME} role.", delete_after=8)
            return False
        if not in_admin_category(ctx.channel, ADMIN_CATEGORY_NAME):
            await ctx.reply(f"Use this in the {ADMIN_CATEGORY_NAME} category.", delete_after=8)
            return False
        return True
    return commands.check(predicate)

def in_webhook_helpers(ctx):
    """Allow commands only inside the 'Webhook Helpers' category."""
    if not in_admin_category(ctx.channel, WorldCupAdminCategory):
        return False
    return True


# -------------------- Commands --------------------
@bot.command(name="ping", help="Check latency")
@admin_only_context()
async def cmd_ping(ctx: commands.Context):
    await ctx.reply(f"Pong {round(bot.latency*1000)} ms")
    await send_discord_log(ctx.guild, f"Ping used by {ctx.author} in #{ctx.channel}")

@bot.command(name="load", help="Load a cog by name")
@admin_only_context()
async def cmd_load(ctx: commands.Context, name: str):
    if not in_webhook_helpers(ctx):
        await ctx.reply(f"Use this command inside the '{WorldCupAdminCategory}' category.", delete_after=6)
        return
    try:
        msg = await bot.load_cog(name)
        await ctx.reply(msg)
        await send_discord_log(ctx.guild, f"Cog load by {ctx.author}: {name}")
    except Exception as e:
        await ctx.reply(f"Load failed: {e}")
        await send_discord_log(ctx.guild, f"Cog load FAILED by {ctx.author}: {name} -> {e}")

@bot.command(name="unload", help="Unload a cog by name")
@admin_only_context()
async def cmd_unload(ctx: commands.Context, name: str):
    if not in_webhook_helpers(ctx):
        await ctx.reply(f"Use this command inside the '{WorldCupAdminCategory}' category.", delete_after=6)
        return
    try:
        msg = await bot.unload_cog(name)
        await ctx.reply(msg)
        await send_discord_log(ctx.guild, f"Cog unload by {ctx.author}: {name}")
    except Exception as e:
        await ctx.reply(f"Unload failed: {e}")
        await send_discord_log(ctx.guild, f"Cog unload FAILED by {ctx.author}: {name} -> {e}")

@bot.command(name="rc", help="Reload a cog by name")
@admin_only_context()
async def cmd_reload(ctx: commands.Context, name: str):
    if not in_webhook_helpers(ctx):
        await ctx.reply(f"Use this command inside the '{WorldCupAdminCategory}' category.", delete_after=6)
        return
    try:
        msg = await bot.reload_cog(name)
        await ctx.reply(msg)
        await send_discord_log(ctx.guild, f"Cog reload by {ctx.author}: {name}")
    except Exception as e:
        await ctx.reply(f"Reload failed: {e}")
        await send_discord_log(ctx.guild, f"Cog reload FAILED by {ctx.author}: {name} -> {e}")

@bot.command(name="sync", help="Sync application (slash) commands")
@admin_only_context()
async def cmd_sync(ctx: commands.Context):
    if not in_webhook_helpers(ctx):
        await ctx.reply(f"Use this command inside the '{WorldCupAdminCategory}' category.", delete_after=6)
        return

    try:
        synced = await bot.tree.sync()
        await ctx.reply(f"Synced {len(synced)} commands.")
        await send_discord_log(ctx.guild, f"Slash commands synced by {ctx.author}")
    except Exception as e:
        await ctx.reply(f"Sync failed: {e}")
        await send_discord_log(ctx.guild, f"Slash sync FAILED by {ctx.author}: {e}")

# -------------------- Errors --------------------
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("Missing argument.")
        return
    if isinstance(error, commands.CommandNotFound):
        return
    try:
        await ctx.reply("An error occurred.")
    except Exception:
        pass
    log.exception("Command error: %s", error)

# -------------------- Run --------------------
def main():
    bot.run(BOT_TOKEN, log_handler=None)

if __name__ == "__main__":
    main()
