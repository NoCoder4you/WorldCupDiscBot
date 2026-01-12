import discord
from discord.ext import commands
from discord import app_commands
import json
from pathlib import Path
import logging

BASE_DIR = Path(__file__).resolve().parents[1]
JSON_DIR = BASE_DIR / "JSON"
PLAYERS_FILE = JSON_DIR / "players.json"
TRACKER_FILE = JSON_DIR / "entries_tracker.json"

ADMIN_CATEGORY = "world cup admin"
ENTRIES_CHANNEL = "entries"

log = logging.getLogger(__name__)

def load_json(path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

class EntriesTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_entries_data(self):
        players = load_json(PLAYERS_FILE)
        data = []
        for uid, pdata in players.items():
            count = len(pdata.get("teams", []))
            name = pdata.get("username", f"User {uid}")
            data.append((int(uid), name, count))
        # Sort by entry count desc, then username
        data.sort(key=lambda x: (-x[2], x[1].lower()))
        return data

    async def get_entries_channel(self, guild: discord.Guild):
        for cat in guild.categories:
            if cat.name.lower() == ADMIN_CATEGORY:
                for chan in cat.text_channels:
                    if chan.name.lower() == ENTRIES_CHANNEL:
                        return chan
        return None

    async def ensure_embed(self, guild: discord.Guild):
        tracker = load_json(TRACKER_FILE)
        guild_id = str(guild.id)
        entries_channel = await self.get_entries_channel(guild)
        if not entries_channel:
            return None, None

        message_id = tracker.get(guild_id, {}).get("message_id")
        message = None

        # Try to fetch old embed
        if message_id:
            try:
                message = await entries_channel.fetch_message(message_id)
                return message, entries_channel
            except Exception:
                pass

        # Create a new embed if not found
        embed = self.build_embed()
        msg = await entries_channel.send(embed=embed)
        log.info("Entries tracker embed posted (guild_id=%s channel_id=%s message_id=%s)", guild.id, entries_channel.id, msg.id)
        tracker[guild_id] = {
            "message_id": msg.id,
            "channel_id": entries_channel.id
        }
        save_json(TRACKER_FILE, tracker)
        return msg, entries_channel

    def build_embed(self):
        data = self.get_entries_data()
        embed = discord.Embed(
            title="World Cup 2026 — Entry Tracker",
            description="Live list of all players and how many entries (teams) they currently have.",
            colour=discord.Colour.gold()
        )
        if not data:
            embed.add_field(name="No entries yet!", value="Players will appear here when added.", inline=False)
        else:
            leaderboard = []
            for uid, name, count in data:
                leaderboard.append(f"<@{uid}> — **{count}** entry{'ies' if count != 1 else ''}")
            embed.add_field(name="Leaderboard", value="\n".join(leaderboard), inline=False)
        embed.set_footer(text="Updated after each /addplayer. Use /updateentries to refresh manually.")
        return embed

    async def update_entries_embed(self, guild):
        msg, channel = await self.ensure_embed(guild)
        if msg:
            await msg.edit(embed=self.build_embed())
            log.info("Entries tracker embed updated (guild_id=%s channel_id=%s message_id=%s)", guild.id, channel.id, msg.id)

    @app_commands.command(
        name="updateentries",
        description="Update the entries tracker embed (Referee/Owner only)"
    )
    async def update_entries(self, interaction: discord.Interaction):
        if not (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == self.bot.owner_id
            or any(r.name.lower() == "referee" for r in getattr(interaction.user, "roles", []))
        ):
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return

        await self.update_entries_embed(interaction.guild)
        await interaction.response.send_message("Entries tracker updated.", ephemeral=True)
        log.info("Entries tracker updated by %s (guild_id=%s)", interaction.user.id, interaction.guild.id if interaction.guild else "unknown")

async def setup(bot):
    await bot.add_cog(EntriesTracker(bot))

# ---- Helper for use in other cogs ----

async def update_entries_embed_for_guild(bot, guild):
    """Import and call this from other cogs (e.g. TeamsDistribution.py) after adding a player."""
    cog = bot.get_cog("EntriesTracker")
    if cog:
        await cog.update_entries_embed(guild)

async def post_country_assignments_embed(bot, guild):
    """
    Posts embeds in the entries channel listing all countries and their assigned users, 16 per embed.
    Import and call from TeamsDistribution.py (after reveal).
    """
    PLAYERS_FILE = JSON_DIR / "players.json"
    TEAMS_FILE = JSON_DIR / "teams.json"

    def load_json(path):
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    players = load_json(PLAYERS_FILE)
    try:
        with open(TEAMS_FILE, "r", encoding="utf-8") as f:
            all_teams = json.load(f)
    except Exception:
        all_teams = []

    # Map: country -> user mention(s)
    country_map = {}
    for uid, pdata in players.items():
        for entry in pdata.get("teams", []):
            country = entry.get("team") if isinstance(entry, dict) else entry
            main_owner = entry.get("ownership", {}).get("main_owner") if isinstance(entry, dict) else None
            if country and str(main_owner) == str(uid):  # Only main owners shown
                country_map[country] = f"<@{uid}>"

    # Sort countries ABC order
    sorted_countries = sorted(all_teams)

    # Prepare batches of 16
    batch_size = 16
    lines = []
    for country in sorted_countries:
        user = country_map.get(country, "*Unassigned*")
        lines.append(f"**{country}**: {user}")

    entries_channel = None
    for cat in guild.categories:
        if cat.name.lower() == "world cup admin":
            for chan in cat.text_channels:
                if chan.name.lower() == "entries":
                    entries_channel = chan
    if not entries_channel:
        return

    # Send one embed for every 16 countries
    for i in range(0, len(lines), batch_size):
        chunk = lines[i:i+batch_size]
        embed = discord.Embed(
            title=f"World Cup 2026 — Team Assignments ({i+1}-{min(i+batch_size, len(lines))})",
            description="Country assignments (ABC order):",
            colour=discord.Colour.blue()
        )
        if bot.user and bot.user.display_avatar:
            embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.add_field(name="Countries", value="\n".join(chunk), inline=False)
        embed.set_footer(text="World Cup 2026 • Team Assignments")
        await entries_channel.send(embed=embed)
        log.info("Country assignments embed posted (guild_id=%s channel_id=%s range=%s-%s)", guild.id, entries_channel.id, i + 1, min(i + batch_size, len(lines)))
