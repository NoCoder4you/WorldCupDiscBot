import datetime as dt
import json
import os
import re
from typing import Any

import discord
from discord.ext import commands, tasks

from stage_constants import STAGE_CHANNEL_MAP, normalize_stage


class MatchStartAnnouncer(commands.Cog):
    """Announce fixtures that are within one hour of kickoff in stage/group channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.json_dir = os.path.join(self.base_dir, "JSON")
        os.makedirs(self.json_dir, exist_ok=True)

        # Canonical fixture storage is JSON/matches.json. Keep a legacy fallback
        # path for environments that still mirror files at repository root.
        self.matches_path = os.path.join(self.json_dir, "matches.json")
        self.legacy_matches_path = os.path.join(self.base_dir, "matches.json")
        self.country_roles_path = os.path.join(self.json_dir, "countryroles.json")
        self.team_meta_path = os.path.join(self.json_dir, "team_meta.json")
        self.state_path = os.path.join(self.json_dir, "match_start_announcer_state.json")
        self.commands_path = os.path.join(self.json_dir, "bot_commands.jsonl")

        self._sent_hour_keys: set[str] = set()
        self._sent_kickoff_keys: set[str] = set()
        self._commands_offset = 0
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
                data = json.load(f) or {}
            # Backward compatibility: previous state versions used "sent_keys"
            # for one-hour reminders only.
            old_hour_keys = data.get("sent_keys") or []
            hour_keys = data.get("sent_hour_keys") or old_hour_keys
            kickoff_keys = data.get("sent_kickoff_keys") or []
            if isinstance(hour_keys, list):
                self._sent_hour_keys = {str(k) for k in hour_keys if str(k).strip()}
            if isinstance(kickoff_keys, list):
                self._sent_kickoff_keys = {str(k) for k in kickoff_keys if str(k).strip()}
            self._commands_offset = int(data.get("commands_offset") or 0)
        except Exception:
            self._sent_hour_keys = set()
            self._sent_kickoff_keys = set()

    def _save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({
                    "sent_hour_keys": sorted(self._sent_hour_keys)[-5000:],
                    "sent_kickoff_keys": sorted(self._sent_kickoff_keys)[-5000:],
                    "commands_offset": int(self._commands_offset),
                }, f)
        except Exception:
            pass

    def _load_json(self, path: str, default: Any):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if data is not None else default
        except Exception:
            return default

    def _load_matches(self) -> list[dict[str, Any]]:
        # Prefer JSON/matches.json because admin/public routes persist there.
        for path in (self.matches_path, self.legacy_matches_path):
            raw_matches = self._load_json(path, [])
            if isinstance(raw_matches, dict):
                raw_matches = raw_matches.get("fixtures") or raw_matches.get("matches") or []
            if isinstance(raw_matches, list) and raw_matches:
                return [m for m in raw_matches if isinstance(m, dict)]
        return []

    def _selected_guild_id(self) -> str:
        settings = self._load_json(os.path.join(self.json_dir, "admin_settings.json"), {})
        return str((settings or {}).get("SELECTED_GUILD_ID") or "").strip()

    def _config_guild_id(self) -> str:
        cfg = self._load_json(os.path.join(self.base_dir, "config.json"), {})
        if not isinstance(cfg, dict):
            return ""
        for key in ("DISCORD_GUILD_ID", "GUILD_ID", "PRIMARY_GUILD_ID", "ADMIN_GUILD_ID", "GUILD", "GUILDID"):
            gid = str(cfg.get(key) or "").strip()
            if gid:
                return gid
        return ""

    def _get_guild(self) -> discord.Guild | None:
        for gid in (self._selected_guild_id(), self._config_guild_id()):
            if gid:
                try:
                    return self.bot.get_guild(int(gid))
                except Exception:
                    pass
        return self.bot.guilds[0] if self.bot.guilds else None

    def _parse_utc_ts(self, raw: str) -> int | None:
        value = str(raw or "").strip()
        if not value:
            return None
        try:
            if value.isdigit():
                return int(value)
            # Normalise common ISO forms, including trailing Z.
            iso = value.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(iso)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return int(parsed.timestamp())
        except Exception:
            return None

    def _extract_group_from_stage(self, stage: str) -> str:
        match = re.search(r"group\\s*([a-l])", str(stage or ""), re.IGNORECASE)
        return match.group(1).upper() if match else ""

    def _group_from_team_meta(self, home: str, away: str) -> str:
        meta = self._load_json(self.team_meta_path, {})
        groups = meta.get("groups") if isinstance(meta, dict) else None
        if not isinstance(groups, dict):
            return ""

        lookup: dict[str, str] = {}
        for group, teams in groups.items():
            if not group or not isinstance(teams, list):
                continue
            for team in teams:
                if isinstance(team, str) and team.strip():
                    lookup[team.strip().lower()] = str(group).strip().upper()

        home_group = lookup.get(str(home or "").strip().lower(), "")
        away_group = lookup.get(str(away or "").strip().lower(), "")
        if home_group and away_group and home_group == away_group:
            return home_group
        return home_group or away_group or ""

    def _resolve_channel_name(self, fixture: dict, home: str, away: str) -> str:
        # Knockout fixtures go to their dedicated stage channels; group fixtures
        # go to the matching group-x channel.
        stage_raw = str(
            fixture.get("stage")
            or fixture.get("round")
            or fixture.get("phase")
            or fixture.get("tournament_stage")
            or ""
        ).strip()
        stage_norm = normalize_stage(stage_raw) or stage_raw
        if stage_norm and stage_norm not in ("Group Stage", "Groups"):
            mapped = STAGE_CHANNEL_MAP.get(stage_norm)
            if mapped:
                return mapped

        group = str(fixture.get("group") or "").strip().upper()
        if not group:
            group = self._extract_group_from_stage(stage_raw)
        if not group:
            group = self._group_from_team_meta(home, away)
        if group:
            return f"group-{group.lower()}"
        return "announcements"

    async def _find_text_channel(self, guild: discord.Guild, name: str) -> discord.TextChannel | None:
        target = str(name or "").strip().lower()
        if not target:
            return None
        for ch in guild.text_channels:
            if ch.name.lower() == target:
                return ch
        return None

    def _country_role_mentions(self, guild: discord.Guild, home: str, away: str) -> str | None:
        mapping = self._load_json(self.country_roles_path, {})
        mentions: list[str] = []

        def resolve(team: str) -> str | None:
            tid = (mapping or {}).get(team)
            if tid:
                try:
                    role = guild.get_role(int(tid))
                    if role:
                        return role.mention
                except Exception:
                    pass
            # Fallback requested by product requirement: role names match country names.
            by_name = discord.utils.find(lambda r: r.name.lower() == str(team or "").strip().lower(), guild.roles)
            return by_name.mention if by_name else None

        for team in (home, away):
            mention = resolve(team)
            if mention and mention not in mentions:
                mentions.append(mention)
        return " ".join(mentions) if mentions else None

    def _reminder_kind(self, seconds_until: int) -> str | None:
        """
        Return which reminder should fire at the current poll tick.

        - hour: within the final hour, but not in the kickoff minute window.
        - kickoff: within ±60 seconds from kickoff.
        """
        if -60 <= seconds_until <= 60:
            return "kickoff"
        if 60 < seconds_until <= 3600:
            return "hour"
        return None

    def _read_new_delay_commands(self) -> list[dict[str, Any]]:
        """Read queued kickoff-adjustment announcements for this cog only.

        The shared bot command queue is append-only and consumed by several cogs,
        so this cog keeps its own byte offset and ignores unrelated command kinds.
        """
        try:
            if not os.path.isfile(self.commands_path):
                return []
            size = os.path.getsize(self.commands_path)
            if self._commands_offset > size:
                self._commands_offset = 0
            with open(self.commands_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._commands_offset)
                lines = f.read().splitlines()
                self._commands_offset = f.tell()
        except Exception:
            return []
        finally:
            self._save_state()

        commands: list[dict[str, Any]] = []
        for raw in lines:
            if not raw.strip():
                continue
            try:
                cmd = json.loads(raw)
            except Exception:
                continue
            if cmd.get("kind") == "fixture_kickoff_adjusted" and isinstance(cmd.get("data"), dict):
                commands.append(cmd["data"])
        return commands

    def _kickoff_adjusted_embed(self, home: str, away: str, previous_ts: int | None, kickoff_ts: int, hours: float) -> discord.Embed:
        direction = "Delayed" if hours > 0 else "Brought forward" if hours < 0 else "Adjusted"
        magnitude = abs(hours)
        hours_label = f"{magnitude:g} hour" + ("" if magnitude == 1 else "s")
        embed = discord.Embed(
            title=f"📅 Match kickoff {direction.lower()}",
            description=(
                f"**{home}** vs **{away}**\n"
                f"New kickoff: <t:{kickoff_ts}:F> (<t:{kickoff_ts}:R>)"
            ),
            color=discord.Color.blurple(),
        )
        if previous_ts:
            embed.add_field(name="Previous kickoff", value=f"<t:{previous_ts}:F> (<t:{previous_ts}:R>)", inline=False)
        embed.add_field(name="Adjustment", value=f"{direction} by {hours_label}", inline=False)
        embed.set_footer(text="World Cup 2026")
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def _send_kickoff_adjustment(self, guild: discord.Guild, data: dict[str, Any]) -> None:
        """Announce a staff-entered schedule change like normal start alerts.

        Schedule changes should reach the same audience as start reminders, so
        this reuses channel resolution and country-role mentions instead of
        posting a generic dashboard toast only.
        """
        home = str(data.get("home") or "").strip()
        away = str(data.get("away") or "").strip()
        kickoff_ts = self._parse_utc_ts(str(data.get("utc") or ""))
        previous_ts = self._parse_utc_ts(str(data.get("previous_utc") or ""))
        if not (home and away and kickoff_ts):
            return
        try:
            hours = float(data.get("hours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        channel_name = self._resolve_channel_name(data.get("fixture") if isinstance(data.get("fixture"), dict) else data, home, away)
        channel = await self._find_text_channel(guild, channel_name)
        if not channel:
            channel = guild.system_channel
        if not channel and guild.text_channels:
            channel = guild.text_channels[0]
        if not channel:
            return
        await channel.send(
            content=self._country_role_mentions(guild, home, away),
            embed=self._kickoff_adjusted_embed(home, away, previous_ts, kickoff_ts, hours),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

    def _announcement_embed(self, home: str, away: str, kickoff_ts: int, reminder_kind: str) -> discord.Embed:
        if reminder_kind == "kickoff":
            title = "🚨 Kickoff is now"
        else:
            title = "⏰ Match starts in 1 hour"
        embed = discord.Embed(
            title=title,
            description=(
                f"**{home}** vs **{away}**\n"
                f"Kickoff: <t:{kickoff_ts}:F> (<t:{kickoff_ts}:R>)"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="World Cup 2026")
        embed.timestamp = discord.utils.utcnow()
        return embed

    @tasks.loop(seconds=60)
    async def _loop(self):
        guild = self._get_guild()
        if not guild:
            return

        for data in self._read_new_delay_commands():
            try:
                await self._send_kickoff_adjustment(guild, data)
            except Exception:
                continue

        matches = self._load_matches()

        now_ts = int(dt.datetime.now(tz=dt.timezone.utc).timestamp())

        for fixture in matches:
            if not isinstance(fixture, dict):
                continue
            home = str(fixture.get("home") or "").strip()
            away = str(fixture.get("away") or "").strip()
            kickoff_raw = str(fixture.get("utc") or fixture.get("time") or "").strip()
            kickoff_ts = self._parse_utc_ts(kickoff_raw)
            if not (home and away and kickoff_ts):
                continue

            seconds_until = kickoff_ts - now_ts
            reminder_kind = self._reminder_kind(seconds_until)
            if not reminder_kind:
                continue

            fixture_id = str(fixture.get("id") or "").strip() or f"{home}-{away}-{kickoff_ts}"
            state_key = f"{fixture_id}:{kickoff_ts}"
            sent_keys = self._sent_kickoff_keys if reminder_kind == "kickoff" else self._sent_hour_keys
            if state_key in sent_keys:
                continue

            channel_name = self._resolve_channel_name(fixture, home, away)
            channel = await self._find_text_channel(guild, channel_name)
            if not channel:
                channel = guild.system_channel
            if not channel and guild.text_channels:
                channel = guild.text_channels[0]
            if not channel:
                continue

            try:
                content = self._country_role_mentions(guild, home, away)
                await channel.send(
                    content=content,
                    embed=self._announcement_embed(home, away, kickoff_ts, reminder_kind),
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
                sent_keys.add(state_key)
                self._save_state()
            except Exception:
                continue

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchStartAnnouncer(bot))
