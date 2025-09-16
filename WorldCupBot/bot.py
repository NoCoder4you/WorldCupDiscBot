import os
import sys
import discord
from discord.ext import commands
from discord import ui
import asyncio
import logging
import json

COGS_DIR = "/home/pi/WorldCupDiscBot/WorldCupBot/COGS"
JSON_DIR = "/home/pi/WorldCupDiscBot/WorldCupBot/JSON"

# --- Logging Setup ---
LOG_FILE = "WC.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Bot token (never hardcode in production!)
BOT_TOKEN = "MTM4NTQwMjk0OTU4MDIyNjY1MA.GcoaGn.-V2q66NwlsAObCixV60He-izsMT9XTEo0fqNgw"
if not BOT_TOKEN:
    print("INVALID BOT TOKEN")
    sys.exit(1)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="wc ", intents=intents, help_command=None)

# Expose JSON_DIR for cogs
bot.JSON_DIR = JSON_DIR


async def update_guilds_json():
    while True:
        data = {
            "guild_count": len(bot.guilds),
            "guilds": [{"id": g.id, "name": g.name} for g in bot.guilds]
        }
        with open(os.path.join(JSON_DIR, "guilds.json"), "w") as f:
            json.dump(data, f)
        await asyncio.sleep(30)

# --- Dynamic Cog Loader ---
def discover_extensions():
    cogs = []
    for file in os.listdir(COGS_DIR):
        if file.endswith('.py') and not file.startswith("_"):
            module = f"COGS.{file[:-3]}"
            cogs.append(module)
    return cogs

async def load_cogs():
    extensions = discover_extensions()
    for extension in extensions:
        try:
            await bot.load_extension(extension)
            print(f'[LOADED] - {extension}')
        except Exception as e:
            logging.error(f"Failed to load cog {extension}: {e}")
            print(f"--- !!! [FAILED] !!! --- - {extension}: {e}")
    print("All Cogs Loaded")

# --- Owner-only Admin Commands ---
@bot.command(name="load")
async def load(ctx, extension: str):
    """Dynamically load a cog."""
    ext = f"COGS.{extension}" if not extension.startswith("COGS.") else extension
    try:
        await bot.load_extension(ext)
        await ctx.send(f"Loaded `{ext}` successfully.", delete_after=2.5)
    except Exception as e:
        logging.error(f"Failed to load cog {ext}: {e}")
        await ctx.send(f"Failed to load `{ext}`: {e}", delete_after=2.5)

@bot.command(name="unload")
async def unload(ctx, extension: str):
    """Dynamically unload a cog."""
    ext = f"COGS.{extension}" if not extension.startswith("COGS.") else extension
    try:
        await bot.unload_extension(ext)
        await ctx.send(f"Unloaded `{ext}` successfully.", delete_after=2.5)
    except Exception as e:
        logging.error(f"Failed to unload cog {ext}: {e}")
        await ctx.send(f"Failed to unload `{ext}`: {e}", delete_after=2.5)

@commands.command(name="reload")
async def reload(self, ctx, cog: str):
    """Reloads a specified cog."""
    try:
        cog_path = f"COGS.{cog}"
        self.bot.reload_extension(cog_path)
        msg = f"✅ Successfully reloaded `{cog}`"
        await ctx.send(msg)
        logging.info(f"Reloaded cog: {cog} by {ctx.author}")
    except Exception as e:
        error_msg = f"❌ Failed to reload `{cog}`\n```{traceback.format_exc()}```"
        await ctx.send(error_msg)
        logging.error(f"Failed to reload cog: {cog} by {ctx.author}\n{traceback.format_exc()}")


class ReloadCogView(ui.View):
    def __init__(self, bot, cogs):
        super().__init__(timeout=60)
        self.bot = bot
        for cog in cogs:
            self.add_item(self.ReloadButton(bot, cog))

    class ReloadButton(ui.Button):
        def __init__(self, bot, cog):
            label = cog.replace("COGS.", "")
            super().__init__(label=label, style=discord.ButtonStyle.primary)
            self.bot = bot
            self.cog = cog

        async def callback(self, interaction: discord.Interaction):
            try:
                await self.bot.reload_extension(self.cog)

                await interaction.response.send_message(f"Reloaded `{self.cog}`.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Failed to reload `{self.cog}`: {e}", ephemeral=True)

@bot.command(name="rc")
async def rc(ctx):
    cogs = discover_extensions()
    view = ReloadCogView(bot, cogs)
    await ctx.send("Reload any cog:", view=view, delete_after=60)



@bot.command(name="cogs")
async def list_cogs(ctx):
    """List all currently loaded cogs and available .py files."""
    loaded_cogs = list(bot.extensions.keys())
    available_cogs = discover_extensions()

    response = "**Loaded Cogs:**\n"
    response += "\n".join(f"- {cog}" for cog in loaded_cogs) if loaded_cogs else "No cogs loaded."

    response += "\n\n**Available .py Files:**\n"
    response += "\n".join(f"- {cog}" for cog in available_cogs)

    await ctx.send(response, delete_after=5)

@bot.command(name="restart")
async def restart(ctx):
    """Restart the bot dynamically."""
    try:
        await ctx.send("Restarting the bot... Please wait!", delete_after=2.5)
        print("Bot is restarting...")
        await bot.close()
        os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        logging.error(f"Failed to restart the bot: {e}")
        await ctx.send(f"Failed to restart the bot: {e}", delete_after=5)

@bot.command(name="stop")
@commands.is_owner()
async def stop(ctx):
    await bot.close()
    
@bot.command(name="sync")
@commands.is_owner()
async def sync(command):
    await bot.tree.sync()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await load_cogs()
    await bot.tree.sync()
    await bot.loop.create_task(update_guilds_json())
    print("Bot is ready.")

bot.run(BOT_TOKEN)
