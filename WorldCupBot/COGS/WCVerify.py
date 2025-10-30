import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import os
import time
import random
import string

SPECTATORS_ROLE_ID = 1388690743782146178
UNVERIFIED_ROLE_ID = 1394431170707456111

VERIFIED_PATH = "/home/pi/WorldCupDiscBot/WorldCupBot/JSON/verified.json"
VERIFICATION_CODES_PATH = "/home/pi/WorldCupDiscBot/WorldCupBot/JSON/verification_codes.json"
VERIFICATION_LOG_CHANNEL_ID = 1394481766739218554

def ensure_json_file(path, default):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(default, f, indent=4)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        with open(path, "w") as f:
            json.dump(default, f, indent=4)
        return default

def save_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def generate_code(length=5):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

class SpectatorVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verification_data = ensure_json_file(VERIFICATION_CODES_PATH, {"verification_data": {}})
        self.verified_data = ensure_json_file(VERIFIED_PATH, {"verified_users": []})

    def save_all(self):
        save_json_file(VERIFICATION_CODES_PATH, self.verification_data)
        save_json_file(VERIFIED_PATH, self.verified_data)

    @app_commands.command(name="verify", description="Verify yourself and get the Spectators role.")
    @app_commands.describe(habbo="Your Habbo username")
    async def verify(self, interaction: discord.Interaction, habbo: str):
        member = interaction.guild.get_member(interaction.user.id)
        unverified_role = interaction.guild.get_role(UNVERIFIED_ROLE_ID)
        if not member or not unverified_role or unverified_role not in member.roles:
            embed = discord.Embed(
                title="Not Allowed",
                description="You must have the **Unverified** role to use this command.",
                color=discord.Color.red()
            )
            embed.set_footer(text="World Cup 2026 - Habbo Verification")
            embed.set_thumbnail(url=f"https://www.habbo.com/habbo-imaging/avatarimage?user={habbo}&direction=3&head_direction=3&gesture=nor&action=wav&size=l")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)

        # If already verified, tell user
        for entry in self.verified_data.get("verified_users", []):
            if entry["discord_id"] == user_id:
                embed = discord.Embed(
                    title="Already Verified",
                    description=f"You are already verified as \n# `{entry['habbo_name']}`",
                    color=discord.Color.green()
                )
                embed.set_footer(text="World Cup 2026 - Habbo Verification")
                embed.set_thumbnail(url=f"https://www.habbo.com/habbo-imaging/avatarimage?user={entry['habbo_name']}&direction=3&head_direction=3&gesture=nor&action=wav&size=l")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        # Check for existing verification in progress
        ongoing = self.verification_data["verification_data"].get(user_id)
        if ongoing:
            code = ongoing["code"]
            stored_habbo = ongoing["habbo"]
            if stored_habbo.lower() != habbo.lower():
                embed = discord.Embed(
                    title="Verification Failed",
                    description=f"Habbo name does not match the original name used. Please wait 5 minutes and try again.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="World Cup 2026 - Habbo Verification")
                embed.set_thumbnail(url=f"https://www.habbo.com/habbo-imaging/avatarimage?user={habbo}&direction=3&head_direction=3&gesture=nor&action=wav&size=l")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            # Check Habbo motto for code
            url = f"https://www.habbo.com/api/public/users?name={habbo}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        motto = data.get("motto")
                        habbo_name = data.get("name")
                        if motto and code in motto:
                            # Assign Spectators role and remove Unverified
                            role = interaction.guild.get_role(SPECTATORS_ROLE_ID)
                            if member and role:
                                try:
                                    await member.add_roles(role)
                                    await member.remove_roles(unverified_role)
                                    await member.edit(nick=habbo_name)
                                except Exception:
                                    pass
                            # Add user to verified.json
                            self.verified_data.setdefault("verified_users", []).append({
                                "discord_id": user_id,
                                "habbo_name": habbo_name
                            })
                            if user_id in self.verification_data["verification_data"]:
                                del self.verification_data["verification_data"][user_id]
                            self.save_all()
                            embed = discord.Embed(
                                title="Verification Successful",
                                description=f"Welcome! \n# `{habbo_name}`! \nYou are now a Spectator.",
                                color=discord.Color.green()
                            )
                            embed.set_footer(text="World Cup 2026 - Habbo Verification")
                            embed.set_thumbnail(url=f"https://www.habbo.com/habbo-imaging/avatarimage?user={habbo}&direction=3&head_direction=3&gesture=nor&action=wav&size=l")
                            await interaction.followup.send(embed=embed, ephemeral=False)

                            # Send log embed to the verification log channel (public, do not delete)
                            verification_log_channel = interaction.guild.get_channel(VERIFICATION_LOG_CHANNEL_ID)
                            if verification_log_channel:
                                log_embed = discord.Embed(
                                    title="Verification Successful",
                                    description=f"# {member.mention}\n# {habbo_name}",
                                    color=discord.Color.green()
                                )
                                log_embed.set_thumbnail(url=f"https://www.habbo.com/habbo-imaging/avatarimage?user={habbo_name}&direction=3&head_direction=3&gesture=nor&action=wav&size=l")
                                log_embed.set_footer(text="World Cup 2026 - Habbo Verification")
                                try:
                                    await verification_log_channel.send(embed=log_embed)
                                except Exception:
                                    pass
                            return
                        else:
                            embed = discord.Embed(
                                title="Verification Failed",
                                description=f"Your motto does not contain the code: \n# `{code}`\nTry again after updating your motto.",
                                color=discord.Color.red()
                            )
                            embed.set_footer(text="World Cup 2026 - Habbo Verification")
                            embed.set_thumbnail(url=f"https://www.habbo.com/habbo-imaging/avatarimage?user={habbo}&direction=3&head_direction=3&gesture=nor&action=wav&size=l")
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return
        # No ongoing verification, create new code
        code = generate_code()
        self.verification_data["verification_data"][user_id] = {
            "code": code,
            "habbo": habbo,
            "timestamp": time.time()
        }
        self.save_all()
        embed = discord.Embed(
            title="Verification Started",
            description=(
                f"Set this code as your **Habbo motto**:\n"
                f"# `{code}`\n"
                "Then run `/verify` again to complete verification."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="World Cup 2026 - Habbo Verification")
        embed.set_thumbnail(url=f"https://www.habbo.com/habbo-imaging/avatarimage?user={habbo}&direction=3&head_direction=3&gesture=nor&action=wav&size=l")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Auto-verify if user is in verified.json when they rejoin."""
        # Reload file (handles changes while bot was running)
        verified_data = ensure_json_file(VERIFIED_PATH, {"verified_users": []})
        for entry in verified_data.get("verified_users", []):
            if entry["discord_id"] == str(member.id):
                # Assign spectator role if not already present
                role = member.guild.get_role(SPECTATORS_ROLE_ID)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Auto-verified on rejoin (World Cup 2026)")
                    except Exception:
                        pass
                # Optionally, remove "unverified" role if present
                unverified_role = member.guild.get_role(UNVERIFIED_ROLE_ID)
                if unverified_role and unverified_role in member.roles:
                    try:
                        await member.remove_roles(unverified_role, reason="Auto-verified on rejoin (World Cup 2026)")
                    except Exception:
                        pass
                break

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """When a member's server nickname changes, persist their display_name to verified.json."""
        # Only act when the guild-specific nickname actually changed
        if before.nick == after.nick:
            return

        # Reload the latest file on each change
        data = ensure_json_file(VERIFIED_PATH, {"verified_users": []})

        user_id = str(after.id)
        updated = False
        for entry in data.get("verified_users", []):
            if entry.get("discord_id") == user_id:
                entry["display_name"] = after.display_name  # display_name = nick if set, else username
                updated = True
                break

        if updated:
            save_json_file(VERIFIED_PATH, data)


async def setup(bot):
    await bot.add_cog(SpectatorVerify(bot))
