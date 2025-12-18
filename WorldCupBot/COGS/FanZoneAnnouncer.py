import os, json, asyncio
import discord
from discord.ext import commands, tasks

class FanZoneAnnouncer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.runtime_dir = os.path.join(self.base_dir, "runtime")
        os.makedirs(self.runtime_dir, exist_ok=True)
        self.queue_path = os.path.join(self.runtime_dir, "bot_commands.jsonl")
        self.state_path = os.path.join(self.runtime_dir, "fanzone_queue_state.json")
        self._offset = 0
        self._load_state()
        self._loop.start()

    def cog_unload(self):
        try:
            self._loop.cancel()
        except Exception:
            pass

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
        # Prefer configured guild id if present
        gid = None
        try:
            cfg_path = os.path.join(self.base_dir, "config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                gid = cfg.get("GUILD_ID") or cfg.get("GUILD") or cfg.get("GUILDID")
        except Exception:
            gid = None

        if gid:
            try:
                return self.bot.get_guild(int(gid))
            except Exception:
                pass

        # Fallback: first guild
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

    async def _dm_user(self, user_id: str, message: str):
        try:
            uid = int(str(user_id))
        except Exception:
            return
        try:
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            if not user:
                return
            await user.send(message)
        except Exception:
            # DM can fail if user has DMs closed
            return

    @tasks.loop(seconds=2.5)
    async def _loop(self):
        if not os.path.isfile(self.queue_path):
            return

        # If file was truncated, reset
        try:
            size = os.path.getsize(self.queue_path)
            if self._offset > size:
                self._offset = 0
        except Exception:
            return

        lines = []
        try:
            with open(self.queue_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._offset)
                chunk = f.read()
                self._offset = f.tell()
                if chunk:
                    lines = [ln for ln in chunk.splitlines() if ln.strip()]
        except Exception:
            return
        finally:
            self._save_state()

        if not lines:
            return

        for ln in lines:
            try:
                cmd = json.loads(ln)
            except Exception:
                continue

            if cmd.get("kind") != "fanzone_winner":
                continue

            data = cmd.get("data") or {}
            fixture_id = str(data.get("fixture_id") or "")
            home = str(data.get("home") or "")
            away = str(data.get("away") or "")
            winner_team = str(data.get("winner_team") or "")
            loser_team = str(data.get("loser_team") or "")
            channel_name = str(data.get("channel") or "fanzone")

            guild = self._get_guild()
            if not guild:
                continue

            # Announce in channel
            ch = await self._find_text_channel(guild, channel_name)
            if not ch:
                # fallback to a safe place
                ch = guild.system_channel
            if not ch and guild.text_channels:
                ch = guild.text_channels[0]

            if ch:
                try:
                    await ch.send(
                        f"🏆 **Fan Zone Result**\n"
                        f"**{home}** vs **{away}**\n"
                        f"Winner: **{winner_team}**\n"
                        f"Stats: COMING SOON."
                    )
                except Exception:
                    pass

            # DM owners
            win_owner_ids = data.get("winner_owner_ids") or []
            lose_owner_ids = data.get("loser_owner_ids") or []

            for uid in win_owner_ids:
                await self._dm_user(uid, f"✅ Your team **{winner_team}** won vs **{loser_team}**. Stats: COMING SOON.")
            for uid in lose_owner_ids:
                await self._dm_user(uid, f"❌ Your team **{loser_team}** lost vs **{winner_team}**. Stats: COMING SOON.")

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(FanZoneAnnouncer(bot))
