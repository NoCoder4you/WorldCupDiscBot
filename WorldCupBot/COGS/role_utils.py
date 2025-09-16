import discord
from discord.ext import commands

ROLE_ROOT = "root"
ROLE_REFEREE = "Referee"
ROLE_PLAYER = "Player"
ROLE_SPECTATORS = "Spectators"

def has_role(member: discord.Member, role_name: str) -> bool:
    """Check if a member has a given role by name (case-insensitive)."""
    return any(role.name.lower() == role_name.lower() for role in getattr(member, "roles", []))

def has_root(member: discord.Member) -> bool:
    return has_role(member, ROLE_ROOT)

def has_referee(member: discord.Member) -> bool:
    return has_role(member, ROLE_REFEREE)

def has_player(member: discord.Member) -> bool:
    return has_role(member, ROLE_PLAYER)

def has_spectator(member: discord.Member) -> bool:
    return has_role(member, ROLE_SPECTATORS)

async def check_root_interaction(interaction):
    """Async check to restrict to Root only."""
    member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
    if not member or not has_root(member):
        await interaction.response.send_message(
            "You are not authorized to use this command. (Root role required)", ephemeral=True
        )
        return False
    return True

async def check_referee_interaction(interaction):
    """Async check to use at the top of slash commands. Restricts to Referees only."""
    member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
    if not member or not has_referee(member):
        await interaction.response.send_message(
            "You are not authorized to use this command. (Referee role required)", ephemeral=True
        )
        return False
    return True

async def check_player_interaction(interaction):
    """Async check to restrict to Players only."""
    member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
    if not member or not has_player(member):
        await interaction.response.send_message(
            "You are not authorized to use this command. (Player role required)", ephemeral=True
        )
        return False
    return True

async def check_spectator_interaction(interaction):
    """Async check to restrict to Spectators only."""
    member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
    if not member or not has_spectator(member):
        await interaction.response.send_message(
            "You are not authorized to use this command. (Spectator role required)", ephemeral=True
        )
        return False
    return True

class RoleUtils(commands.Cog):
    """Utility cog for role checks—no commands."""
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(RoleUtils(bot))
