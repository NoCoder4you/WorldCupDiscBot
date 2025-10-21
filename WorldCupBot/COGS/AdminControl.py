from discord.ext import commands
import os
import json

COGS_STATUS_FILE = '/home/pi/WorldCupDiscBot/WorldCupBot/JSON/cogs_status.json'  # Adjust path as needed

def update_cogs_status(bot):
    status = {
        "loaded": list(bot.extensions.keys())
    }
    with open(COGS_STATUS_FILE, "w") as f:
        json.dump(status, f)


ADMIN_CHANNEL_ID = 1385997807680356372
BOT_OWNER_ID = 298121351871594497      # Your Discord user ID

class AdminControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # Allow commands from the admin webhook or your user
        if message.channel.id != ADMIN_CHANNEL_ID:
            return
        if not (message.author.id == BOT_OWNER_ID or message.webhook_id is not None):
            return

        if message.content.startswith("wc "):
            parts = message.content.split()
            if len(parts) == 3:
                action, cog = parts[1], parts[2]
                try:
                    if action in {"unload"} and cog == "AdminControl":
                        await message.channel.send("Nice try. I’m the ladder you’re standing on.")
                        return
                    if action == "reload":
                        await self.bot.reload_extension(f"COGS.{cog}")
                        update_cogs_status(self.bot)
                        await message.channel.send(f":white_check_mark: Reloaded `{cog}`.")
                    elif action == "load":
                        await self.bot.load_extension(f"COGS.{cog}")
                        update_cogs_status(self.bot)
                        await message.channel.send(f":white_check_mark: Loaded `{cog}`.")
                    elif action == "unload":
                        await self.bot.unload_extension(f"COGS.{cog}")
                        update_cogs_status(self.bot)
                        await message.channel.send(f":white_check_mark: Unloaded `{cog}`.")
                    else:
                        await message.channel.send("Invalid action.")
                except Exception as e:
                    await message.channel.send(f":x: Error: `{e}`")

async def setup(bot):
    await bot.add_cog(AdminControl(bot))
