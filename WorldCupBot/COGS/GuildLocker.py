import discord
from discord.ext import commands

ALLOWED_GUILD_IDS = [
    1202999519986458765,
    1385778542792544278
]
NOTIFY_CHANNEL_ID = 1385412174180257843  # Channel to notify on illegal join

class GuildLock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def notify_and_leave(self, guild):
        channel = None
        # Find the notify channel in allowed guilds
        for allowed_guild in self.bot.guilds:
            if allowed_guild.id in ALLOWED_GUILD_IDS:
                ch = allowed_guild.get_channel(NOTIFY_CHANNEL_ID)
                if ch:
                    channel = ch
                    break

        if channel:
            embed = discord.Embed(
                title="Guild Lock Activated",
                description=f"Tried to join disallowed guild: **{guild.name}** (`{guild.id}`)",
                color=discord.Color.red()
            )
            embed.set_footer(text="Bot will leave this guild immediately.")
            await channel.send(embed=embed)
        await guild.leave()

    @commands.Cog.listener()
    async def on_ready(self):
        # Leave any non-allowed guilds on startup
        for guild in self.bot.guilds:
            if guild.id not in ALLOWED_GUILD_IDS:
                await self.notify_and_leave(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # If joining a non-allowed guild, notify and leave
        if guild.id not in ALLOWED_GUILD_IDS:
            await self.notify_and_leave(guild)

async def setup(bot):
    await bot.add_cog(GuildLock(bot))
