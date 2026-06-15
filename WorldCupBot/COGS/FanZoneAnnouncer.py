import os, json
import discord
from discord.ext import commands, tasks

from match_events import sort_match_events
from queue_utils import compact_command_queue

class FanZoneAnnouncer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.json_dir = os.path.join(self.base_dir, "JSON")
        os.makedirs(self.json_dir, exist_ok=True)

        self.queue_path = os.path.join(self.json_dir, "bot_commands.jsonl")
        self.state_path = os.path.join(self.json_dir, "fanzone_queue_state.json")
        self.commands_state_path = os.path.join(self.json_dir, "bot_commands_state.json")
        self.stage_state_path = os.path.join(self.json_dir, "stage_queue_state.json")

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
        # Installations have used both the project root and JSON directory for
        # this mapping, so check both locations before giving up on thumbnails.
        candidate_paths = (
            self.team_iso_path,
            os.path.join(self.json_dir, "team_iso.json"),
        )
        for path in candidate_paths:
            try:
                if not os.path.isfile(path):
                    continue
                with open(path, "r", encoding="utf-8") as f:
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
                continue
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

    def _public_embed(
        self,
        home: str,
        away: str,
        winner: str,
        loser: str,
        thumb_iso: str | None,
        home_score=None,
        away_score=None,
    ):
        is_draw = str(winner or "").strip().lower() == "draw" or not loser
        result_line = f"Result: **Draw**" if is_draw else f"Winner: **{winner}**"
        # Place the trophy beside the winning country only: before the home
        # country or after the away country, matching their visual positions.
        winner_key = str(winner or "").strip().lower()
        home_display = f"🏆 {home}" if not is_draw and winner_key == home.strip().lower() else home
        away_display = f"{away} 🏆" if not is_draw and winner_key == away.strip().lower() else away
        # Score-driven settlements include the canonical scoreline. Legacy
        # declarations omit scores and retain their existing display.
        score_line = ""
        if home_score is not None and away_score is not None:
            score_line = f"\n**{home_score} – {away_score}**"
        e = discord.Embed(
            title="FULL TIME RESULT",
            description=f"**{home_display}** vs **{away_display}**{score_line}\n\n{result_line}",
            color=discord.Color.gold()
        )
        e.add_field(name="Stats", value="COMING SOON", inline=False)
        url = self._flag_url(thumb_iso or "")
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text="World Cup 2026 Match Picks")
        e.timestamp = discord.utils.utcnow()
        return e

    def _result_embed(
        self,
        home: str,
        away: str,
        home_score: int,
        away_score: int,
        winner_side: str = "",
        live_stats: list | None = None,
        home_penalties: int | None = None,
        away_penalties: int | None = None,
    ):
        """Build the official score embed sent to the fixture's Discord channel."""
        side = str(winner_side or "").strip().lower()
        if home_score > away_score or (home_score == away_score and side == "home"):
            home_display = f"🏆 {home}"
            away_display = away
            color = discord.Color.green()
        elif away_score > home_score or (home_score == away_score and side == "away"):
            home_display = home
            away_display = f"{away} 🏆"
            color = discord.Color.green()
        else:
            home_display = home
            away_display = away
            color = discord.Color.gold()

        penalty_line = ""
        if home_penalties is not None and away_penalties is not None:
            penalty_line = f"\n**Penalties: {home} {home_penalties} – {away_penalties} {away}**"
        embed = discord.Embed(
            title="FULL TIME RESULT",
            description=f"**{home_display} {home_score} – {away_score} {away_display}**{penalty_line}",
            color=color,
        )
        stats_lines = []
        # Sort defensively for older fixtures saved before events were ordered
        # during entry, ensuring their final result summaries are also fixed.
        for stat in sort_match_events(live_stats or []):
            if not isinstance(stat, dict):
                continue
            label = str(stat.get("label") or "Update").strip()
            match_time = str(stat.get("match_time") or "").strip()
            event_type = str(stat.get("event_type") or "").strip().lower()
            country = str(stat.get("country") or "").strip()
            # Half time has a standard clock value even though the dashboard
            # does not ask the operator to enter one. Final summaries describe
            # the incident itself instead of repeating the score after every
            # event, which keeps the score exclusive to the result heading.
            display_time = match_time or ("45" if event_type == "half_time" else "")
            timing = f" - {display_time}'" if display_time else ""
            country_text = f"  {country}" if country else ""
            stats_lines.append(f"**{label}**{timing}{country_text}")
        if stats_lines:
            # Discord embed fields are limited to 1024 characters.
            embed.add_field(name="Match Stats", value="\n".join(stats_lines)[-1024:], inline=False)
        embed.set_footer(text="World Cup 2026 Fixtures")
        embed.timestamp = discord.utils.utcnow()
        return embed

    def _quick_announcement_embed(self, data: dict) -> discord.Embed:
        """Build a compact live update with the selected country's flag thumbnail."""
        event_type = str(data.get("event_type") or "").strip().lower()
        colors = {
            "goal": discord.Color.green(),
            "yellow_card": discord.Color.gold(),
            "red_card": discord.Color.red(),
            "half_time": discord.Color.blurple(),
        }
        icons = {
            "goal": "⚽",
            "yellow_card": "🟨",
            "red_card": "🟥",
            "half_time": "⏸️",
        }
        label = str(data.get("event_label") or "Match Update").strip()
        match_time = str(data.get("match_time") or "").strip()
        # Put the clock in the title so the event and its timing are visible
        # together in Discord notifications and compact embed previews.
        display_time = match_time or ("45" if event_type == "half_time" else "")
        title_timing = f"  {display_time}'" if display_time else ""
        home = str(data.get("home") or "").strip()
        away = str(data.get("away") or "").strip()
        home_score = int(data.get("home_score") or 0)
        away_score = int(data.get("away_score") or 0)
        embed = discord.Embed(
            title=f"{icons.get(event_type, '📣')} {label}{title_timing}",
            color=colors.get(event_type, discord.Color.blurple()),
        )
        # The title communicates the action, so the body only needs the current
        # scoreline rather than repeating the event label and matchup.
        embed.add_field(
            name="Match",
            value=f"**{home} {home_score} - {away_score} {away}**",
            inline=False,
        )
        country = str(data.get("country") or "").strip()
        country_iso = self._iso_for_team(country, data.get("country_iso"))
        flag_url = self._flag_url(country_iso)
        if flag_url:
            embed.set_thumbnail(url=flag_url)
        embed.set_footer(text="World Cup 2026 Live Update")
        embed.timestamp = discord.utils.utcnow()
        return embed

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
        e.set_footer(text="World Cup 2026 Match Picks")
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
        e.set_footer(text="World Cup 2026 Match Picks")
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

            kind = cmd.get("kind")
            if kind not in ("fanzone_winner", "fixture_result", "quick_match_announcement"):
                continue

            data = cmd.get("data") or {}
            home = str(data.get("home") or "")
            away = str(data.get("away") or "")
            channel_name = str(data.get("channel") or "fanzone")

            if kind == "quick_match_announcement":
                ch = await self._find_text_channel(guild, channel_name)
                if not ch:
                    ch = guild.system_channel
                if not ch and guild.text_channels:
                    ch = guild.text_channels[0]
                if ch:
                    try:
                        await ch.send(embed=self._quick_announcement_embed(data))
                    except Exception:
                        pass
                continue

            # Result commands are generated by the Add result action and post
            # the authoritative score to the dedicated match channel.
            if kind == "fixture_result":
                ch = await self._find_text_channel(guild, channel_name)
                if not ch:
                    ch = guild.system_channel
                if not ch and guild.text_channels:
                    ch = guild.text_channels[0]
                if ch:
                    try:
                        await ch.send(embed=self._result_embed(
                            home,
                            away,
                            int(data.get("home_score") or 0),
                            int(data.get("away_score") or 0),
                            str(data.get("winner_side") or ""),
                            data.get("live_stats") if isinstance(data.get("live_stats"), list) else [],
                            data.get("home_penalties"),
                            data.get("away_penalties"),
                        ))
                    except Exception:
                        pass
                continue

            winner_team = str(data.get("winner_team") or "")
            loser_team = str(data.get("loser_team") or "")

            winner_iso = self._iso_for_team(winner_team, data.get("winner_iso"))
            loser_iso = self._iso_for_team(loser_team, data.get("loser_iso"))

            # Public embed announcement
            ch = await self._find_text_channel(guild, channel_name)
            if not ch:
                ch = guild.system_channel
            if not ch and guild.text_channels:
                ch = guild.text_channels[0]

            if ch and not bool(data.get("suppress_public")):
                try:
                    emb = self._public_embed(
                        home,
                        away,
                        winner_team,
                        loser_team,
                        winner_iso,
                        data.get("home_score"),
                        data.get("away_score"),
                    )
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
