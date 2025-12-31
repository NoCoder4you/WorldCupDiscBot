import discord
from discord.ext import commands
from discord import app_commands

from stage_constants import STAGE_CHANNEL_SLUGS

IGNORED_TEXT_CHANNEL_ID = 1389403009766920325

STAGE_KEY_ALIASES = {
    "groups": "Group Stage",
    "32": "Round of 32",
    "16": "Round of 16",
    "quarters": "Quarter-finals",
    "semi": "Semi-finals",
    "third": "Third Place Play-off",
    "finals": "Final",
}

VOICE_STAGE_NAMES = {
    "Round of 32": "Round of 32",
    "Round of 16": "Round of 16",
    "Quarter-finals": "Quarter Finals",
    "Semi-finals": "Semi Finals",
    "Third Place Play-off": "Third Place Play",
    "Final": "Final",
    "Winner": "Final",
}

GROUP_TEXT_CHANNELS = [f"group-{chr(97 + i)}" for i in range(12)]
GROUP_VOICE_CHANNELS = [f"Group {chr(65 + i)}" for i in range(12)]

DIVIDER_CHANNEL_NAME = "________________"
TEXT_CATEGORY_NAME = "world cup"
VOICE_CATEGORY_NAME = "world cup vc"

def has_referee_role(member):
    return any(role.name.lower() == "referee" for role in getattr(member, "roles", []))

def get_stage_channels(stage_key: str, is_voice: bool):
    key = (stage_key or "").strip().lower()
    canonical = STAGE_KEY_ALIASES.get(key, "")
    if key == "groups" or canonical == "Group Stage":
        targets = GROUP_VOICE_CHANNELS if is_voice else GROUP_TEXT_CHANNELS
        return targets, True
    if not canonical:
        return [], False
    if is_voice:
        voice_name = VOICE_STAGE_NAMES.get(canonical)
        return ([voice_name] if voice_name else []), False
    slug = STAGE_CHANNEL_SLUGS.get(canonical)
    return ([slug] if slug else []), False

class ChannelManage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def find_category(self, guild, category_name):
        for category in guild.categories:
            if category.name.lower() == category_name:
                return category
        return None

    def get_roles(self, guild):
        players = discord.utils.get(guild.roles, name="Players")
        spectators = discord.utils.get(guild.roles, name="Spectators")
        referees = discord.utils.get(guild.roles, name="Referee")
        everyone = guild.default_role
        return players, spectators, referees, everyone

    async def set_channel_perms(self, channel, players, spectators, referees, everyone, visible: bool, is_divider=False):
        thread_deny = {
            "create_public_threads": False,
            "create_private_threads": False,
            "send_messages_in_threads": False
        }
        overwrite = {}
        if referees:
            if is_divider:
                overwrite[referees] = discord.PermissionOverwrite(
                    view_channel=visible,
                    send_messages=False,
                    read_message_history=visible,
                    connect=False,
                    speak=False,
                    **thread_deny
                )
            else:
                overwrite[referees] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=False,
                    connect=True,
                    speak=True,
                    **thread_deny
                )
        if players:
            if is_divider:
                overwrite[players] = discord.PermissionOverwrite(
                    view_channel=visible,
                    send_messages=False,
                    read_message_history=False,
                    connect=False,
                    speak=False,
                    **thread_deny
                )
            else:
                overwrite[players] = discord.PermissionOverwrite(
                    view_channel=visible,
                    send_messages=visible,
                    read_message_history=visible,
                    connect=visible,
                    speak=visible,
                    **thread_deny
                )
        if spectators:
            if is_divider:
                overwrite[spectators] = discord.PermissionOverwrite(
                    view_channel=visible,
                    send_messages=False,
                    read_message_history=False,
                    connect=False,
                    speak=False,
                    **thread_deny
                )
            else:
                overwrite[spectators] = discord.PermissionOverwrite(
                    view_channel=visible,
                    send_messages=visible,
                    read_message_history=visible,
                    connect=visible,
                    speak=visible,
                    **thread_deny
                )
        overwrite[everyone] = discord.PermissionOverwrite(
            view_channel=False, send_messages=False, read_message_history=False, connect=False, speak=False,
            create_public_threads=False, create_private_threads=False, send_messages_in_threads=False
        )
        await channel.edit(overwrites=overwrite)

    async def toggle_category_stage(self, category, players, spectators, referees, everyone, stage, show, is_voice: bool = False):
        all_channels = [ch for ch in (category.text_channels + category.voice_channels)]
        all_channels.sort(key=lambda c: c.position)

        if is_voice:
            stage_targets, use_prefix = get_stage_channels(stage, is_voice=True)
            stage_indices = [i for i, ch in enumerate(all_channels) if ch.name in stage_targets]
            if use_prefix:
                stage_indices = [i for i, ch in enumerate(all_channels) if ch.name.startswith("Group ")]
        else:
            stage_targets, use_prefix = get_stage_channels(stage, is_voice=False)
            stage_indices = [i for i, ch in enumerate(all_channels) if ch.name.lower() in stage_targets]
            if use_prefix:
                stage_indices = [i for i, ch in enumerate(all_channels) if ch.name.startswith("group-")]

        if not stage_indices:
            return 0

        first_idx = min(stage_indices)
        last_idx = max(stage_indices)

        divider_above = None
        divider_below = None
        for i in range(first_idx - 1, -1, -1):
            if all_channels[i].name == DIVIDER_CHANNEL_NAME:
                divider_above = all_channels[i]
                break
        for i in range(last_idx + 1, len(all_channels)):
            if all_channels[i].name == DIVIDER_CHANNEL_NAME:
                divider_below = all_channels[i]
                break

        changed = 0
        for i, channel in enumerate(all_channels):
            # Ignore permission changing on this text channel
            if not is_voice and channel.id == IGNORED_TEXT_CHANNEL_ID:
                continue

            is_stage = i in stage_indices
            is_above_divider = divider_above and (channel.id == divider_above.id)
            is_below_divider = divider_below and (channel.id == divider_below.id)
            is_divider = channel.name == DIVIDER_CHANNEL_NAME

            if is_stage:
                await self.set_channel_perms(channel, players, spectators, referees, everyone, show, is_divider=False)
                changed += 1
            elif is_above_divider or is_below_divider:
                await self.set_channel_perms(channel, players, spectators, referees, everyone, show, is_divider=True)
            elif is_divider:
                await self.set_channel_perms(channel, players, spectators, referees, everyone, False, is_divider=True)
        return changed


    @app_commands.command(
        name="stage",
        description="Show or hide World Cup channels for any stage."
    )
    @app_commands.describe(
        stage="Which World Cup stage to show or hide.",
        action="Show or hide the selected stage."
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="show", value="show"),
            app_commands.Choice(name="hide", value="hide")
        ]
    )
    async def stage(
        self,
        interaction: discord.Interaction,
        stage: str,
        action: app_commands.Choice[str]
    ):
        await interaction.response.defer(ephemeral=True)
        await self._toggle_stage(interaction, stage.lower(), action.value == "show")

    async def _toggle_stage(self, interaction, stage, show: bool):
        if not has_referee_role(interaction.user) and interaction.user != interaction.guild.owner:
            await interaction.followup.send(
                "Only Referees or the server owner can use this command.", ephemeral=True
            )
            return

        text_category = await self.find_category(interaction.guild, TEXT_CATEGORY_NAME)
        voice_category = await self.find_category(interaction.guild, VOICE_CATEGORY_NAME)
        players, spectators, referees, everyone = self.get_roles(interaction.guild)

        changed_text = 0
        changed_voice = 0

        if text_category:
            changed_text = await self.toggle_category_stage(
                text_category, players, spectators, referees, everyone, stage, show, is_voice=False
            )
        if voice_category:
            changed_voice = await self.toggle_category_stage(
                voice_category, players, spectators, referees, everyone, stage, show, is_voice=True
            )

        total_changed = changed_text + changed_voice
        if total_changed == 0:
            await interaction.followup.send(
                f"No channels found for stage `{stage}` in World Cup categories.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"{'Shown' if show else 'Hidden'} `{total_changed}` channels for stage: **{stage.title()}**.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(ChannelManage(bot))
