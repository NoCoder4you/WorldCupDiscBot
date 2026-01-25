import os, json, logging
import discord
from discord.ext import commands, tasks

from queue_utils import compact_command_queue

log = logging.getLogger(__name__)

class StageProgressAnnouncer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.json_dir = os.path.join(self.base_dir, "JSON")
        os.makedirs(self.json_dir, exist_ok=True)

        self.queue_path = os.path.join(self.json_dir, "bot_commands.jsonl")
        self.state_path = os.path.join(self.json_dir, "stage_queue_state.json")
        self.commands_state_path = os.path.join(self.json_dir, "bot_commands_state.json")
        self.fanzone_state_path = os.path.join(self.json_dir, "fanzone_queue_state.json")

        self.team_iso_path = os.path.join(self.base_dir, "team_iso.json")
        self.country_roles_path = os.path.join(self.base_dir, "JSON", "countryroles.json")
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
                    out = {}
                    for k, v in m.items():
                        if not k or not v:
                            continue
                        out[str(k).strip().lower()] = str(v).strip().lower()
                    return out
        except Exception:
            pass
        return {}

    def _load_country_roles(self) -> dict:
        try:
            if os.path.isfile(self.country_roles_path):
                with open(self.country_roles_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
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

    def _get_team_role(self, guild: discord.Guild | None, team: str) -> discord.Role | None:
        if not guild:
            return None
        roles = self._load_country_roles()
        role_id = roles.get(team)
        if not role_id:
            return None
        try:
            return guild.get_role(int(role_id))
        except Exception:
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

    def _stage_line(self, team: str, stage: str) -> str:
        stage = str(stage or "").strip()
        if stage == "Eliminated":
            return f"**{team}** was eliminated."
        return f"**{team}** advanced to **{stage}**."

    def _public_embed(self, team: str, stage: str, thumb_iso: str | None):
        stage = str(stage or "").strip()
        if stage == "Eliminated":
            title = "Stage Update"
            color = discord.Color.red()
        else:
            title = "Stage Update"
            color = discord.Color.blue()
        e = discord.Embed(
            title=title,
            description=self._stage_line(team, stage),
            color=color
        )
        url = self._flag_url(thumb_iso or "")
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text="World Cup 2026")
        e.timestamp = discord.utils.utcnow()
        return e

    def _dm_embed(self, team: str, stage: str, thumb_iso: str | None):
        stage = str(stage or "").strip()
        if stage == "Eliminated":
            title = "🚫 Your team was eliminated"
            color = discord.Color.red()
            description = f"**{team}** was eliminated."
        else:
            title = "🏟️ Your team advanced"
            color = discord.Color.green()
            description = f"**{team}** moved on to **{stage}**."
        e = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        url = self._flag_url(thumb_iso or "")
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text="World Cup 2026")
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

            if cmd.get("kind") != "team_stage_progress":
                continue

            data = cmd.get("data") or {}
            team = str(data.get("team") or "")
            stage = str(data.get("stage") or "")
            channel_name = str(data.get("channel") or "announcements")
            owner_ids = data.get("owner_ids") or []
            log.info(
                "Country stage announcement queued (team=%s stage=%s channel=%s owners=%s)",
                team,
                stage,
                channel_name,
                len(owner_ids),
            )

            thumb_iso = self._iso_for_team(team, data.get("team_iso"))

            ch = await self._find_text_channel(guild, channel_name)
            if not ch:
                ch = guild.system_channel
            if not ch and guild.text_channels:
                ch = guild.text_channels[0]

            if ch:
                try:
                    emb = self._public_embed(team, stage, thumb_iso)
                    role = self._get_team_role(guild, team)
                    content = role.mention if role else None
                    await ch.send(
                        content=content,
                        embed=emb,
                        allowed_mentions=discord.AllowedMentions(roles=True)
                    )
                except Exception:
                    pass

            if owner_ids:
                dm_emb = self._dm_embed(team, stage, thumb_iso)
                for uid in owner_ids:
                    await self._dm_user_embed(uid, dm_emb)

        compact_command_queue(
            self.queue_path,
            [self.state_path, self.commands_state_path, self.fanzone_state_path],
        )

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(StageProgressAnnouncer(bot))
