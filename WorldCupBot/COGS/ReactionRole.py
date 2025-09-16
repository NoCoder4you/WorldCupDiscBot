import discord
from discord.ext import commands
import json

MESSAGE_ID = 1394475178611966106
ROLE_ID = 1394431170707456111  # Unverified role
GREEN_TICK = "✅"
VERIFIED_FILE = "/home/pi/WorldCupDiscBot/WorldCupBot/JSON/verified.json"

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
        if payload.message_id == MESSAGE_ID and str(payload.emoji) == GREEN_TICK:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
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

            channel = guild.get_channel(payload.channel_id)
            if not channel:
                return
            try:
                message = await channel.fetch_message(payload.message_id)
            except Exception:
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
