import json
import random
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
import logging
from COGS.role_utils import (
    check_root_interaction, check_referee_interaction
)

JSON_DIR = Path("/home/pi/WorldCupDiscBot/WorldCupBot/JSON")
TEAMS_FILE = JSON_DIR / "teams.json"
PLAYERS_FILE = JSON_DIR / "players.json"
ISO_FILE = JSON_DIR / "team_iso.json"
COUNTRYROLES_FILE = JSON_DIR / "countryroles.json"

log = logging.getLogger(__name__)

def load_json(path):
    if not path.exists():
        return {} if path.name.endswith(".json") else []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def flag_url(team, iso_mapping):
    iso = iso_mapping.get(team)
    if not iso:
        return None
    return f"https://flagcdn.com/w320/{iso.lower()}.png"

def format_share_percent(total_owners):
    if total_owners <= 0:
        return ""
    share = 100 / total_owners
    if share.is_integer():
        return f"{int(share)}%"
    return f"{share:.1f}%"

def format_owner_mentions(owner_mentions, share):
    if not owner_mentions:
        return "N/A"
    return ", ".join(f"{mention} ({share})" for mention in owner_mentions)

class TeamsDistribution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.iso_mapping = load_json(ISO_FILE)

    async def get_or_create_country_role(self, guild, country, existing_roles, countryroles, reason="World Cup Team Assignment"):
        role = existing_roles.get(country)
        if not role and guild:
            try:
                role = await guild.create_role(name=country, mentionable=True, reason=reason)
                existing_roles[country] = role
                countryroles[country] = role.id
                save_json(COUNTRYROLES_FILE, countryroles)
            except Exception:
                role = None
        elif role:
            countryroles[country] = role.id
            save_json(COUNTRYROLES_FILE, countryroles)
        return role

    @app_commands.command(
        name="addplayer",
        description="Add a user to the World Cup pool."
    )
    async def addplayer(self, interaction: discord.Interaction, user: discord.User):
        if not await check_root_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        players = load_json(PLAYERS_FILE)
        teams = load_json(TEAMS_FILE)
        if str(user.id) not in players:
            players[str(user.id)] = {"username": user.name, "teams": []}

        players[str(user.id)]["teams"].append({"pending": True})

        save_json(PLAYERS_FILE, players)

        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None
        pending_entries = sum(
            1 for entry in players[str(user.id)]["teams"]
            if isinstance(entry, dict) and entry.get("pending")
        )
        assigned_teams = set()
        for pdata in players.values():
            for entry in pdata.get("teams", []):
                if isinstance(entry, dict):
                    if entry.get("team"):
                        assigned_teams.add(entry["team"])
                elif entry:
                    assigned_teams.add(entry)
        teams_left = max(len(teams) - len(assigned_teams), 0)

        confirm_embed = discord.Embed(
            title="New Player Added",
            description=(
                f"# {user.mention}\n"
                "- Player added to the pool\n"
                f"- Pending team assignments: {pending_entries}\n"
                f"- There are {teams_left} Teams Left"
            ),
            colour=discord.Colour.gold()
        )
        if bot_avatar:
            confirm_embed.set_thumbnail(url=bot_avatar)

        # Find "World Cup Admin" > "player-confirmation"
        guild = interaction.guild
        confirm_channel = None
        if guild:
            for category in guild.categories:
                if category.name.lower() == "world cup admin":
                    for channel in category.text_channels:
                        if channel.name.lower() == "player-confirmation":
                            confirm_channel = channel
                            break
                if confirm_channel:
                    break

        if confirm_channel:
            msg = await confirm_channel.send(embed=confirm_embed)
            log.info(
                "Player add embed posted (actor_id=%s target_id=%s channel_id=%s message_id=%s)",
                interaction.user.id,
                user.id,
                confirm_channel.id,
                msg.id,
            )

        dm_embed = discord.Embed(
            title="World Cup 2026",
            description=(
                "Thank You for joining Noah's FIFA 2026 World Cup Tournament!\n"
                "- Your team will be randomly assigned before the tournament starts!\n"
                "- Your team will be revealed before the tournament starts!\n"
                "- You are more than welcome to purchase more than one team!"
            ),
            colour=discord.Colour.green()
        )
        if bot_avatar:
            dm_embed.set_thumbnail(url=bot_avatar)
        dm_embed.set_footer(text="All sales are final and no refunds will be provided.")
        try:
            await user.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.followup.send(
            f"{user.mention} has been added to the pool.", ephemeral=True
        )
        log.info("Player added (actor_id=%s target_id=%s)", interaction.user.id, user.id)

    @app_commands.command(
        name="randomiseteams",
        description="Randomly assign teams to unassigned players."
    )
    async def randomiseteams(self, interaction: discord.Interaction):
        if not await check_root_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        players = load_json(PLAYERS_FILE)
        teams = load_json(TEAMS_FILE)

        assigned_teams = set()
        for pdata in players.values():
            for entry in pdata.get("teams", []):
                if isinstance(entry, dict):
                    team = entry.get("team")
                    if team:
                        assigned_teams.add(team)
                elif entry:
                    assigned_teams.add(entry)

        unassigned_teams = [team for team in teams if team not in assigned_teams]
        pending_entries = []
        for pid, pdata in players.items():
            for entry in pdata.get("teams", []):
                if isinstance(entry, dict) and entry.get("pending"):
                    pending_entries.append((pid, pdata, entry))

        if not pending_entries:
            await interaction.followup.send(
                "No players are waiting for assignments.", ephemeral=True
            )
            return

        if len(unassigned_teams) < len(pending_entries):
            await interaction.followup.send(
                "Not enough unassigned teams to cover all pending players.",
                ephemeral=True
            )
            return

        random.shuffle(unassigned_teams)
        for (pid, _pdata, entry), team in zip(pending_entries, unassigned_teams):
            entry.clear()
            entry.update({
                "team": team,
                "ownership": {
                    "main_owner": int(pid),
                    "split_with": []
                }
            })

        save_json(PLAYERS_FILE, players)

        await interaction.followup.send(
            f"Assigned teams to {len(pending_entries)} pending entry(ies).", ephemeral=True
        )
        log.info("Teams randomly assigned (actor_id=%s count=%s)", interaction.user.id, len(pending_entries))

        if sum(
            1 for pdata in players.values() for entry in pdata.get("teams", [])
            if isinstance(entry, dict) and entry["team"] or isinstance(entry, str)
        ) == len(teams):
            app_owner = (self.bot.get_user(self.bot.owner_id) or
                         await self.bot.fetch_user(self.bot.owner_id))
            if app_owner:
                try:
                    await app_owner.send("All World Cup teams have now been assigned to players.")
                except Exception:
                    pass

    @app_commands.command(
        name="reveal",
        description="Reveal and DM each player their teams."
    )
    async def reveal(self, interaction: discord.Interaction):
        if not await check_referee_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        players = load_json(PLAYERS_FILE)
        guild = interaction.guild
        public_channel = None
        if guild:
            for category in guild.categories:
                if category.name.lower() == "world cup":
                    for channel in category.text_channels:
                        if channel.name.lower() == "players-and-teams":
                            public_channel = channel
                            break
                if public_channel:
                    break
        if not public_channel:
            await interaction.followup.send(
                "Could not find a channel named 'players-and-teams' in the 'World Cup' category.",
                ephemeral=True
            )
            return

        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None
        existing_roles = {role.name: role for role in guild.roles} if guild else {}
        countryroles = load_json(COUNTRYROLES_FILE)

        # Collect main ownership per team (alphabetical)
        alphabetical_assignments = []
        for pid, pdata in players.items():
            for entry in pdata.get("teams", []):
                country = entry["team"] if isinstance(entry, dict) else entry
                ownership = entry["ownership"] if isinstance(entry, dict) else {}
                if ownership and str(ownership.get("main_owner")) == pid:
                    alphabetical_assignments.append((country, pid, entry))

        alphabetical_assignments.sort(key=lambda x: x[0].lower())

        country_to_split_with = {}
        for pid, pdata in players.items():
            for entry in pdata.get("teams", []):
                if isinstance(entry, dict) and entry.get("ownership"):
                    country = entry["team"]
                    for split_uid in entry["ownership"].get("split_with", []):
                        country_to_split_with.setdefault(country, set()).add(split_uid)

        for country, pid, entry in alphabetical_assignments:
            user = self.bot.get_user(int(pid)) or await self.bot.fetch_user(int(pid))
            user_member = guild.get_member(int(pid)) if guild else None
            user_avatar = user.display_avatar.url if user else None
            flag = flag_url(country, self.iso_mapping)

            country_role = await self.get_or_create_country_role(guild, country, existing_roles, countryroles)
            if user_member and country_role:
                try:
                    await user_member.add_roles(country_role, reason="World Cup Team Assignment")
                except Exception:
                    pass

            split_with_users = []
            for split_uid in country_to_split_with.get(country, []):
                split_user_obj = guild.get_member(split_uid) or self.bot.get_user(split_uid)
                split_with_users.append(split_user_obj.mention if split_user_obj else str(split_uid))
            total_owners = 1 + len(split_with_users)
            share = format_share_percent(total_owners)
            split_with_value = format_owner_mentions(split_with_users, share)
            main_value = user.mention if user else pid
            if split_with_users:
                main_value = f"{main_value} ({share})"

            public_embed = discord.Embed(
                title=country,
                colour=discord.Colour.blue()
            )
            public_embed.add_field(name="Main User", value=main_value, inline=False)
            public_embed.add_field(name="Split With", value=split_with_value, inline=False)
            if user_avatar:
                public_embed.set_thumbnail(url=user_avatar)
            if flag:
                public_embed.set_image(url=flag)
            msg = await public_channel.send(embed=public_embed)
            log.info(
                "Team reveal embed posted (actor_id=%s team=%s channel_id=%s message_id=%s)",
                interaction.user.id,
                country,
                public_channel.id,
                msg.id,
            )

            if isinstance(entry, dict):
                entry["public_message_id"] = msg.id

            dm_embed = discord.Embed(
                title=f"World Cup 2026 - {country}",
                description=(
                    "Thank you and Welcome to the 2026 World Cup Tournament!\n"
                    "This will be your main team during this tournament. "
                    "Players may request to split this team with you but this will solely be your decision.\n\n"
                    "You may request to split other teams with the command:\n"
                    "`/split team:COUNTRY`"
                ),
                colour=discord.Colour.green()
            )
            if bot_avatar:
                dm_embed.set_thumbnail(url=bot_avatar)
            if flag:
                dm_embed.set_image(url=flag)
            try:
                await user.send(embed=dm_embed)
            except Exception:
                pass

        save_json(PLAYERS_FILE, players)

        await interaction.followup.send(
            "All assignments have been revealed (in alphabetical order) and sent. See the players-and-teams channel.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(TeamsDistribution(bot))
