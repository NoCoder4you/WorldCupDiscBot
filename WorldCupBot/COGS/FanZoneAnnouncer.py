import os, json
import discord
from discord.ext import commands, tasks

from queue_utils import compact_command_queue

class FanZoneAnnouncer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.runtime_dir = os.path.join(self.base_dir, "runtime")
        os.makedirs(self.runtime_dir, exist_ok=True)

        self.queue_path = os.path.join(self.runtime_dir, "bot_commands.jsonl")
        self.state_path = os.path.join(self.runtime_dir, "fanzone_queue_state.json")
        self.commands_state_path = os.path.join(self.runtime_dir, "bot_commands_state.json")
        self.stage_state_path = os.path.join(self.runtime_dir, "stage_queue_state.json")

        self.team_iso_path = os.path.join(self.base_dir, "team_iso.json")
        self.team_iso = self._load_team_iso()

        self._offset = 0
        self._load_state()
        self._loop.start()

    def cog_unload(self):
        try:
            self._loop.cancel()
        except Exception:
            pass

    def _load_team_iso(self):
        try:
            if os.path.isfile(self.team_iso_path):
                with open(self.team_iso_path, "r", encoding="utf-8") as f:
                    m = json.load(f)
                if isinstance(m, dict):
                    # normalize keys and codes
                    out = {}
                    for k, v in m.items():
                        if not k or not v:
                            continue
                        out[str(k).strip().lower()] = str(v).strip().lower()
                    return out
        except Exception:
            pass
        return {}

    def _load_settings(self) -> dict:
        path = os.path.join(self.base_dir, "JSON", "admin_settings.json")
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            pass
        return {}

    def _selected_guild_id(self) -> str:
        settings = self._load_settings()
        return str(settings.get("SELECTED_GUILD_ID") or "").strip()

    def _config_guild_id(self) -> str:
        try:
            cfg_path = os.path.join(self.base_dir, "config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f) or {}
                for key in ("DISCORD_GUILD_ID", "GUILD_ID", "PRIMARY_GUILD_ID", "ADMIN_GUILD_ID", "GUILD", "GUILDID"):
                    gid = str(cfg.get(key) or "").strip()
                    if gid:
                        return gid
        except Exception:
            pass
        return ""

    def _iso_for_team(self, team_name: str, provided_iso: str | None = None) -> str:
        if provided_iso:
            return str(provided_iso).strip().lower()
        key = (team_name or "").strip().lower()
        return self.team_iso.get(key, "")

    def _flag_url(self, iso_code: str) -> str | None:
        code = (iso_code or "").strip().lower()
        if not code:
            return None
        # flagcdn supports both iso-2 and gb-eng style codes
        return f"https://flagcdn.com/w80/{code}.png"

    def _load_state(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self._offset = int(d.get("offset") or 0)
        except Exception:
            self._offset = 0

    def _save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"offset": int(self._offset)}, f)
        except Exception:
            pass

    def _get_guild(self) -> discord.Guild | None:
        for gid in (self._selected_guild_id(), self._config_guild_id()):
            if gid:
                try:
                    return self.bot.get_guild(int(gid))
                except Exception:
                    pass

        return self.bot.guilds[0] if self.bot.guilds else None

    async def _find_text_channel(self, guild: discord.Guild, name: str) -> discord.TextChannel | None:
        if not guild:
            return None
        name = (name or "").strip().lower()
        if not name:
            return None
        for ch in guild.text_channels:
            if ch.name.lower() == name:
                return ch
        return None

    async def _dm_user_embed(self, user_id: str, embed: discord.Embed):
        try:
            uid = int(str(user_id))
        except Exception:
            return
        try:
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            if not user:
                return
            await user.send(embed=embed)
        except Exception:
            return

    def _public_embed(self, home: str, away: str, winner: str, loser: str, thumb_iso: str | None):
        is_draw = str(winner or "").strip().lower() == "draw" or not loser
        result_line = f"Result: **Draw**" if is_draw else f"Winner: **{winner}**"
        e = discord.Embed(
            title="Match Votes Result",
            description=f"**{home}** vs **{away}**\n{result_line}",
            color=discord.Color.gold()
        )
        e.add_field(name="Stats", value="COMING SOON", inline=False)
        url = self._flag_url(thumb_iso or "")
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text="World Cup 2026 Match Votes")
        e.timestamp = discord.utils.utcnow()
        return e

    def _dm_embed(self, won: bool, your_team: str, other_team: str, thumb_iso: str | None):
        e = discord.Embed(
            title=("✅ Your team won" if won else "❌ Your team lost"),
            description=f"**{your_team}** {'beat' if won else 'lost to'} **{other_team}**",
            color=(discord.Color.green() if won else discord.Color.red())
        )
        e.add_field(name="Stats", value="COMING SOON", inline=False)
        url = self._flag_url(thumb_iso or "")
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text="World Cup 2026 Match Votes")
        e.timestamp = discord.utils.utcnow()
        return e

    def _dm_draw_embed(self, home: str, away: str, thumb_iso: str | None):
        e = discord.Embed(
            title="🤝 Match ended in a draw",
            description=f"**{home}** drew with **{away}**",
            color=discord.Color.gold()
        )
        e.add_field(name="Stats", value="COMING SOON", inline=False)
        url = self._flag_url(thumb_iso or "")
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text="World Cup 2026 Match Votes")
        e.timestamp = discord.utils.utcnow()
        return e

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

        guild = self._get_guild()
        if not guild:
            return

        for ln in lines:
            try:
                cmd = json.loads(ln)
            except Exception:
                continue

            if cmd.get("kind") != "fanzone_winner":
                continue

            data = cmd.get("data") or {}
            home = str(data.get("home") or "")
            away = str(data.get("away") or "")
            winner_team = str(data.get("winner_team") or "")
            loser_team = str(data.get("loser_team") or "")
            channel_name = str(data.get("channel") or "fanzone")

            winner_iso = self._iso_for_team(winner_team, data.get("winner_iso"))
            loser_iso = self._iso_for_team(loser_team, data.get("loser_iso"))

            # Public embed announcement
            ch = await self._find_text_channel(guild, channel_name)
            if not ch:
                ch = guild.system_channel
            if not ch and guild.text_channels:
                ch = guild.text_channels[0]

            if ch:
                try:
                    emb = self._public_embed(home, away, winner_team, loser_team, winner_iso)
                    await ch.send(embed=emb)
                except Exception:
                    pass

            # DM embeds to owners
            win_owner_ids = data.get("winner_owner_ids") or []
            lose_owner_ids = data.get("loser_owner_ids") or []
            draw_owner_ids = data.get("draw_owner_ids") or []

            if str(data.get("winner_side") or "").strip().lower() != "draw":
                win_emb = self._dm_embed(True, winner_team, loser_team, winner_iso)
                lose_emb = self._dm_embed(False, loser_team, winner_team, loser_iso)

                for uid in win_owner_ids:
                    await self._dm_user_embed(uid, win_emb)
                for uid in lose_owner_ids:
                    await self._dm_user_embed(uid, lose_emb)
            else:
                draw_emb = self._dm_draw_embed(home, away, winner_iso or loser_iso)
                for uid in draw_owner_ids:
                    await self._dm_user_embed(uid, draw_emb)

        compact_command_queue(
            self.queue_path,
            [self.state_path, self.commands_state_path, self.stage_state_path],
        )

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(FanZoneAnnouncer(bot))
