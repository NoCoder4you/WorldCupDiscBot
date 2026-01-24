import discord
from discord.ext import commands
import json
from pathlib import Path

ROLE_ID = 1394431170707456111  # Unverified role
GREEN_TICK = "✅"
BASE_DIR = Path(__file__).resolve().parents[1]
VERIFIED_FILE = str(BASE_DIR / "JSON" / "verified.json")
RULES_EMBED_TITLE = "Server Rules"
RULES_EMBED_FOOTER = "World Cup 2026 - Server Rules"

def is_verified(user_id):
    try:
        with open(VERIFIED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(user_id) in {str(u["discord_id"]) for u in data.get("verified_users", [])}
    except Exception:
        return False

class ReactionRoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if str(payload.emoji) != GREEN_TICK:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        if not message.embeds:
            return
        embed = message.embeds[0]
        footer_text = embed.footer.text if embed.footer else None
        if embed.title != RULES_EMBED_TITLE or footer_text != RULES_EMBED_FOOTER:
            return

        # Ensure member object (sometimes not cached)
        member = guild.get_member(payload.user_id)
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception:
                return
        if member.bot:
            return

        # Verified check
        if is_verified(payload.user_id):
            try:
                await message.remove_reaction(GREEN_TICK, member)
            except Exception as e:
                print(f"Could not remove reaction for verified user: {e}")
            return

        # Not verified: Add role, then remove reaction
        role = guild.get_role(ROLE_ID)
        if not role:
            return
        try:
            await member.add_roles(role, reason="Reacted with ✅ for World Cup")
        except Exception as e:
            print(f"Error adding role: {e}")
        try:
            await message.remove_reaction(GREEN_TICK, member)
        except Exception as e:
            print(f"Could not remove reaction: {e}")

    @commands.command(name="react", help="Make the bot react to a message with a green tick.")
    @commands.is_owner()
    async def react(self, ctx, message_id: int):
        try:
            message = await ctx.channel.fetch_message(message_id)
            await message.add_reaction(GREEN_TICK)
            await ctx.send(f"Reacted with ✅ to message {message_id}", delete_after=3)
        except discord.NotFound:
            await ctx.send("Message not found.", delete_after=3)
        except Exception as e:
            await ctx.send(f"Error: {e}", delete_after=3)

async def setup(bot):
    await bot.add_cog(ReactionRoleCog(bot))
