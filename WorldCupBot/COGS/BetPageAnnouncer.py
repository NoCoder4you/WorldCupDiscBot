import json
import os
import tempfile
from typing import Optional
import logging

import discord
from discord.ext import commands, tasks

from queue_utils import compact_command_queue

log = logging.getLogger(__name__)

def _json_read(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _json_write_atomic(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="bet_page_", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


class BetPageAnnouncer(commands.Cog):
    """
    Mirror web-created/claimed bets into Discord by consuming runtime commands.

    The web API writes commands to JSON/bot_commands.jsonl so this cog can post
    and update embeds without requiring direct Discord credentials in Flask.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.json_dir = os.path.join(self.base_dir, "JSON")
        os.makedirs(self.json_dir, exist_ok=True)

        self.queue_path = os.path.join(self.json_dir, "bot_commands.jsonl")
        self.state_path = os.path.join(self.json_dir, "bet_queue_state.json")
        self.commands_state_path = os.path.join(self.json_dir, "bot_commands_state.json")
        self.fanzone_state_path = os.path.join(self.json_dir, "fanzone_queue_state.json")
        self.stage_state_path = os.path.join(self.json_dir, "stage_queue_state.json")
        self.bets_path = os.path.join(self.json_dir, "bets.json")

        self._offset = 0
        self._load_state()
        self._loop.start()

    def cog_unload(self):
        try:
            self._loop.cancel()
        except Exception:
            pass

    def _load_state(self):
        data = _json_read(self.state_path, {})
        self._offset = int(data.get("offset") or 0) if isinstance(data, dict) else 0

    def _save_state(self):
        _json_write_atomic(self.state_path, {"offset": int(self._offset)})

    def _load_config(self) -> dict:
        return _json_read(os.path.join(self.base_dir, "config.json"), {})

    def _load_settings(self) -> dict:
        return _json_read(os.path.join(self.json_dir, "admin_settings.json"), {})

    def _selected_guild_id(self) -> str:
        settings = self._load_settings()
        if isinstance(settings, dict):
            return str(settings.get("SELECTED_GUILD_ID") or "").strip()
        return ""

    def _config_guild_id(self) -> str:
        cfg = self._load_config()
        if not isinstance(cfg, dict):
            return ""
        for key in ("DISCORD_GUILD_ID", "GUILD_ID", "PRIMARY_GUILD_ID", "ADMIN_GUILD_ID", "GUILD", "GUILDID"):
            gid = str(cfg.get(key) or "").strip()
            if gid:
                return gid
        return ""

    def _get_guild(self) -> Optional[discord.Guild]:
        for gid in (self._selected_guild_id(), self._config_guild_id()):
            if gid:
                try:
                    return self.bot.get_guild(int(gid))
                except Exception:
                    continue
        return self.bot.guilds[0] if self.bot.guilds else None

    async def _find_bets_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        if not guild:
            return None

        settings = self._load_settings()
        cfg = self._load_config()

        # Explicit IDs are still supported, but we intentionally force the
        # default to the dedicated #bets channel.
        candidates = [
            settings.get("BETS_CHANNEL_ID"),
            settings.get("BETS_CHANNEL"),
            cfg.get("BETS_CHANNEL_ID"),
            cfg.get("BETS_CHANNEL"),
            cfg.get("BETS_CHANNEL_NAME"),
            cfg.get("BET_CHANNEL_ID"),
            cfg.get("BET_CHANNEL"),
            cfg.get("BET_CHANNEL_NAME"),
            "bets",
        ]

        for raw in candidates:
            token = str(raw or "").strip()
            if not token:
                continue
            if token.isdigit():
                ch = guild.get_channel(int(token))
                if isinstance(ch, discord.TextChannel):
                    return ch
                try:
                    fetched = await self.bot.fetch_channel(int(token))
                    if isinstance(fetched, discord.TextChannel):
                        return fetched
                except Exception:
                    pass
            else:
                for ch in guild.text_channels:
                    if ch.name.lower() == token.lower():
                        return ch

        # Do not fall back to arbitrary channels; requirement is to post in #bets.
        return None

    def _load_bets(self):
        data = _json_read(self.bets_path, [])
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("bets"), list):
            return data["bets"]
        return []

    def _save_bets(self, bets):
        _json_write_atomic(self.bets_path, bets)

    def _find_bet(self, bet_id: str):
        bets = self._load_bets()
        for b in bets:
            if isinstance(b, dict) and str(b.get("bet_id") or "").strip() == str(bet_id).strip():
                return bets, b
        return bets, None

    def _mention_or_name(self, uid, uname):
        sid = str(uid or "").strip()
        if sid:
            return f"<@{sid}>"
        return str(uname or "Unclaimed")

    def _display_name(self, user: discord.abc.User) -> str:
        """Resolve a stable display label for persisted bet claim records."""
        return (
            str(getattr(user, "display_name", "") or "").strip()
            or str(getattr(user, "global_name", "") or "").strip()
            or str(getattr(user, "name", "") or "").strip()
            or str(getattr(user, "id", "") or "").strip()
        )

    async def _claim_bet_from_discord(self, bet_id: str, user: discord.abc.User):
        """
        Handle in-Discord claim button interactions for web-posted bets so the
        same claim state is reflected in JSON and on the Bets page.
        """
        bets, bet = self._find_bet(bet_id)
        if not bet:
            return False, "Bet not found in records."

        claimer_id = str(getattr(user, "id", "") or "").strip()
        if not claimer_id:
            return False, "Unable to identify your account."
        if claimer_id == str(bet.get("option1_user_id") or "").strip():
            return False, "You cannot claim your own bet."
        if str(bet.get("option2_user_id") or "").strip():
            return False, "This bet has already been claimed."

        bet["option2_user_id"] = claimer_id
        bet["option2_user_name"] = self._display_name(user)
        self._save_bets(bets)
        return True, f'You claimed: **{bet.get("option2") or "Option 2"}**'

    async def _bet_message_view(self, bet_id: str, *, claimable: bool):
        if not claimable:
            return None

        view = discord.ui.View(timeout=None)

        async def _on_claim(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            ok, message = await self._claim_bet_from_discord(bet_id, interaction.user)
            if not ok:
                await interaction.followup.send(message, ephemeral=True)
                return

            # Reload from JSON to guarantee the embed reflects persisted state.
            _, fresh = self._find_bet(bet_id)
            if fresh and interaction.message:
                try:
                    await interaction.message.edit(embed=self._build_bet_embed(fresh), view=None)
                except Exception:
                    pass
            await interaction.followup.send(message, ephemeral=True)

        claim_btn = discord.ui.Button(label="Claim Bet", style=discord.ButtonStyle.success)
        claim_btn.callback = _on_claim
        view.add_item(claim_btn)
        return view

    def _build_bet_embed(self, bet: dict) -> discord.Embed:
        option1 = str(bet.get("option1") or "Option 1")
        option2 = str(bet.get("option2") or "Option 2")
        winner = str(bet.get("winner") or "").strip().lower()

        opt1_user = self._mention_or_name(bet.get("option1_user_id"), bet.get("option1_user_name"))
        opt2_user = self._mention_or_name(bet.get("option2_user_id"), bet.get("option2_user_name"))

        color = discord.Color.gold() if not str(bet.get("option2_user_id") or "").strip() else discord.Color.green()
        embed = discord.Embed(
            title=f"📝 Bet: {bet.get('bet_title') or 'Bet'}",
            description=f"### Wager: {bet.get('wager') or '-'}",
            color=color,
        )

        o1_label = option1
        o2_label = option2
        if winner == "option1":
            o1_label = f"🏆 {option1} 🏆"
            o2_label = f"~~{option2}~~"
        elif winner == "option2":
            o1_label = f"~~{option1}~~"
            o2_label = f"🏆 {option2} 🏆"

        embed.add_field(name=o1_label, value=f"Claimed By: {opt1_user}", inline=False)
        embed.add_field(name=o2_label, value=f"Claimed By: {opt2_user}", inline=False)

        if self.bot.user:
            avatar = self.bot.user.avatar.url if self.bot.user.avatar else self.bot.user.default_avatar.url
            embed.set_thumbnail(url=avatar)
            embed.set_footer(text=f"{self.bot.user.display_name} • All bets claimed are final.")
        return embed

    async def _handle_bet_created(self, bet_id: str):
        bets, bet = self._find_bet(bet_id)
        if not bet:
            return

        # If a message_id already exists (e.g. slash command-created bet), do
        # not duplicate announcements.
        if str(bet.get("message_id") or "").strip():
            return

        guild = self._get_guild()
        if not guild:
            return

        channel = await self._find_bets_channel(guild)
        if not channel:
            log.warning("Skipping bet post because #bets channel was not found (bet_id=%s)", bet_id)
            return

        try:
            view = await self._bet_message_view(bet_id, claimable=True)
            sent = await channel.send(embed=self._build_bet_embed(bet), view=view)
        except Exception:
            return

        bet["message_id"] = str(sent.id)
        bet["channel_id"] = str(channel.id)
        self._save_bets(bets)

    async def _handle_bet_claimed(self, bet_id: str):
        bets, bet = self._find_bet(bet_id)
        if not bet:
            return

        try:
            channel_id = int(str(bet.get("channel_id") or "0"))
            message_id = int(str(bet.get("message_id") or "0"))
        except Exception:
            return
        if not channel_id or not message_id:
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return

        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return

        try:
            await msg.edit(embed=self._build_bet_embed(bet), view=None)
        except Exception:
            return

    @tasks.loop(seconds=2.5)
    async def _loop(self):
        if not os.path.isfile(self.queue_path):
            return

        try:
            size = os.path.getsize(self.queue_path)
            if self._offset > size:
                self._offset = 0
        except Exception:
            return

        try:
            with open(self.queue_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._offset)
                chunk = f.read()
                self._offset = f.tell()
        except Exception:
            return
        finally:
            self._save_state()

        if not chunk:
            return

        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            return

        for ln in lines:
            try:
                cmd = json.loads(ln)
            except Exception:
                continue

            kind = str(cmd.get("kind") or "").strip().lower()
            data = cmd.get("data") if isinstance(cmd.get("data"), dict) else {}
            bet_id = str(data.get("bet_id") or "").strip()
            if not bet_id:
                continue

            if kind == "bet_created":
                await self._handle_bet_created(bet_id)
            elif kind == "bet_claimed":
                await self._handle_bet_claimed(bet_id)

        compact_command_queue(
            self.queue_path,
            [self.state_path, self.commands_state_path, self.fanzone_state_path, self.stage_state_path],
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(BetPageAnnouncer(bot))
