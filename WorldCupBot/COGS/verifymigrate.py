# WCVerifyMigrate.py
# Simple text command to retro-fill Discord identifiers into verified.json

import discord
from discord.ext import commands
import json
import os

VERIFIED_PATH = "/home/pi/WorldCupDiscBot/WorldCupBot/JSON/verified.json"


# ---------- JSON HELPERS ----------
def ensure_json_file(path, default):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
        return default


def save_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# ---------- DISCORD HELPERS ----------
def build_avatar_url(user: discord.abc.User) -> str:
    """Return the correct Discord avatar URL."""
    if user.avatar:
        ext = "gif" if user.avatar.is_animated() else "png"
        return (
            f"https://cdn.discordapp.com/avatars/"
            f"{user.id}/{user.avatar.key}.{ext}?size=256"
        )

    # default avatar fallback
    index = user.id % 5
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


class VerifyMigration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="migrateverified")
    async def migrate_verified(self, ctx: commands.Context):
        await ctx.send("⏳ Starting migration… This may take a few seconds.")

        guild = ctx.guild
        if guild is None:
            await ctx.send("❌ This command must be used inside a guild.")
            return

        # ensure member cache is populated
        await guild.chunk()

        data = ensure_json_file(VERIFIED_PATH, {"verified_users": []})
        users = data.get("verified_users", [])
        if not isinstance(users, list):
            await ctx.send("❌ verified.json format error.")
            return

        updated = 0
        missing = 0

        for entry in users:
            if not isinstance(entry, dict):
                continue

            did_str = str(entry.get("discord_id") or "").strip()
            if not did_str:
                continue

            try:
                did = int(did_str)
            except ValueError:
                continue

            # Try guild member first
            member = guild.get_member(did)
            user_obj = member

            # Fallback to fetch_user
            if user_obj is None:
                try:
                    user_obj = await self.bot.fetch_user(did)
                except Exception:
                    user_obj = None

            if user_obj is None:
                missing += 1
                continue

            # Fill identifiers saved by WCVerify.py moving forward
            entry["discord_id"] = did_str
            entry["discord_username"] = getattr(user_obj, "name", None)
            entry["discord_global_name"] = getattr(user_obj, "global_name", None)

            if isinstance(user_obj, discord.Member):
                entry["discord_display_name"] = user_obj.display_name
            else:
                entry["discord_display_name"] = (
                    getattr(user_obj, "global_name", None)
                    or getattr(user_obj, "name", None)
                )

            entry["discord_avatar"] = build_avatar_url(user_obj)

            updated += 1

        save_json_file(VERIFIED_PATH, data)

        await ctx.send(
            f"✅ Migration complete!\n"
            f"• Updated entries: **{updated}**\n"
            f"• Users not found: **{missing}**"
        )


async def setup(bot):
    await bot.add_cog(VerifyMigration(bot))
