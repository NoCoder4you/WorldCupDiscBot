import json
import os
import time
from typing import Any

from discord.ext import commands

from match_events import sort_match_events
from stage_constants import STAGE_ALLOWED, normalize_stage, stage_rank


EVENT_LABELS = {
    "goal": "Goal",
    "disallowed_goal": "Goal Disallowed",
    "penalty": "Penalty",
    "var_decision": "VAR Decision",
    "yellow_card": "Yellow Card",
    "red_card": "Red Card",
    "half_time": "Half Time",
    "extra_time": "Extra Time",
    "extra_time_half_time": "Extra Time Half Time",
    "extra_time_full_time": "Extra Time Full Time",
    "extra_time_penalties": "Penalties",
}

# Match-state quick options are not owned by either country, so operators can
# announce them without selecting a team or supplying a match clock.
MATCH_STATE_EVENTS = {"half_time", "extra_time", "extra_time_half_time", "extra_time_full_time", "extra_time_penalties"}


class TextQuickOptions(commands.Cog):
    """Text-command equivalents for dashboard quick actions.

    These commands write the same runtime queue records used by the web quick
    options, so the existing announcer cogs continue to own Discord posting,
    owner DMs, role mentions, and channel routing.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.json_dir = os.path.join(self.base_dir, "JSON")
        os.makedirs(self.json_dir, exist_ok=True)
        self.commands_path = os.path.join(self.json_dir, "bot_commands.jsonl")
        self.matches_path = os.path.join(self.json_dir, "matches.json")
        self.team_stage_path = os.path.join(self.json_dir, "team_stage.json")
        self.settings_path = os.path.join(self.json_dir, "admin_settings.json")

    def _read_json(self, path: str, default: Any):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json_atomic(self, path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)

    def _enqueue_command(self, kind: str, data: dict) -> None:
        os.makedirs(os.path.dirname(self.commands_path), exist_ok=True)
        record = {"kind": kind, "data": data, "ts": int(time.time())}
        with open(self.commands_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _fixture_list(self):
        container = self._read_json(self.matches_path, [])
        if isinstance(container, list):
            return container, None, ""
        if isinstance(container, dict):
            for key in ("fixtures", "matches"):
                if isinstance(container.get(key), list):
                    return container[key], container, key
        return [], None, ""

    def _find_fixture(self, match_id: str):
        fixtures, container, key = self._fixture_list()
        wanted = str(match_id or "").strip().lower()
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            ids = (fixture.get("id"), fixture.get("match_id"), fixture.get("fixture_id"))
            if any(str(value or "").strip().lower() == wanted for value in ids):
                return fixture, fixtures, container, key
        return None, fixtures, container, key

    def _active_channel_fixtures(self, channel_name: str):
        """Return non-completed fixtures that belong to the command channel.

        Simple quick commands intentionally omit a match id, so channel names are
        used as the match context in the same way dashboard quick options target
        a match channel.
        """
        fixtures, container, key = self._fixture_list()
        wanted = str(channel_name or "").strip().lower()
        matches = []
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            status = str(fixture.get("status") or "").strip().lower()
            if status in {"completed", "final", "finished"}:
                continue
            if self._fixture_channel(fixture).lower() == wanted:
                matches.append(fixture)
        return matches, fixtures, container, key

    def _completed_channel_fixtures(self, channel_name: str):
        """Return completed fixtures for the command channel in saved order.

        Rebuild commands need the opposite of live quick actions: they should
        target the last finished match in the current Discord match channel so
        operators can recreate a deleted or stale full-time embed without
        changing the stored fixture result.
        """
        fixtures, container, key = self._fixture_list()
        wanted = str(channel_name or "").strip().lower()
        matches = []
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            status = str(fixture.get("status") or "").strip().lower()
            if status not in {"completed", "final", "finished"}:
                continue
            if self._fixture_channel(fixture).lower() == wanted:
                matches.append(fixture)
        return matches, fixtures, container, key

    def _last_completed_fixture(self):
        """Return the most recently saved completed fixture across all matches.

        This is the no-argument fallback for remake commands: operators should
        not need to know a match id just to rebuild the result card for the last
        fixture that was on.
        """
        fixtures, container, key = self._fixture_list()
        for fixture in reversed(fixtures):
            if not isinstance(fixture, dict):
                continue
            status = str(fixture.get("status") or "").strip().lower()
            if status in {"completed", "final", "finished"}:
                return fixture, fixtures, container, key, ""
        return None, fixtures, container, key, "No completed fixture found."

    def _resolve_last_completed_channel_fixture(self, ctx: commands.Context):
        channel_name = str(getattr(getattr(ctx, "channel", None), "name", "") or "").strip()
        matches, fixtures, container, key = self._completed_channel_fixtures(channel_name)
        if matches:
            return matches[-1], fixtures, container, key, ""
        return self._last_completed_fixture()

    def _fixture_id(self, fixture: dict) -> str:
        for field in ("id", "match_id", "fixture_id"):
            value = str(fixture.get(field) or "").strip()
            if value:
                return value
        return ""

    def _resolve_channel_fixture(self, ctx: commands.Context):
        channel_name = str(getattr(getattr(ctx, "channel", None), "name", "") or "").strip()
        matches, fixtures, container, key = self._active_channel_fixtures(channel_name)
        if len(matches) == 1:
            return matches[0], fixtures, container, key, ""
        if not matches:
            return None, fixtures, container, key, "No active fixture found for this channel."
        return None, fixtures, container, key, "Multiple active fixtures match this channel; use `wc quick <match_id> ...`."

    def _save_fixtures(self, fixtures: list, container: Any, key: str) -> None:
        if container is not None and key:
            container[key] = fixtures
            self._write_json_atomic(self.matches_path, container)
        else:
            self._write_json_atomic(self.matches_path, fixtures)

    def _fixture_channel(self, fixture: dict) -> str:
        channel = str(fixture.get("channel") or fixture.get("fanzone_channel") or "").strip()
        if channel:
            return channel
        group = str(fixture.get("group") or "").strip().lower()
        return f"group-{group}" if group else "fanzone"

    def _score_from_live_stats(self, fixture: dict, home: str, away: str) -> tuple[int, int]:
        stats = fixture.get("live_stats") if isinstance(fixture.get("live_stats"), list) else []
        home_score = sum(1 for stat in stats if stat.get("event_type") == "goal" and stat.get("country") == home)
        away_score = sum(1 for stat in stats if stat.get("event_type") == "goal" and stat.get("country") == away)
        return home_score, away_score

    def _fixture_score(self, fixture: dict) -> tuple[int | None, int | None]:
        """Read a completed fixture score without guessing from live events.

        A remade full-time embed should mirror the official stored result,
        including any manual corrections, rather than recalculating from event
        history that may omit shootout or administrative score adjustments.
        """
        try:
            return int(fixture.get("home_score")), int(fixture.get("away_score"))
        except (TypeError, ValueError):
            return None, None

    def _parse_event_details(self, details: str, home: str, away: str) -> tuple[str, str]:
        """Split free-form command text into a team name and optional clock.

        Operators can type multi-word countries naturally, e.g.
        `wc quick M1 goal Costa Rica 67+2`, without needing quotes.
        """
        clean = str(details or "").strip()
        for team in (home, away):
            if clean.lower() == team.lower():
                return team, ""
            prefix = f"{team} "
            if clean.lower().startswith(prefix.lower()):
                return team, clean[len(prefix):].strip()
        return clean, ""

    async def _delete_command_message(self, ctx: commands.Context) -> None:
        # Keep match channels clean: text commands are controls, not content.
        try:
            await ctx.message.delete()
        except Exception:
            pass

    async def _ack(self, ctx: commands.Context, message: str) -> None:
        await ctx.send(message, delete_after=12)

    async def _queue_event_for_fixture(
        self,
        ctx: commands.Context,
        fixture: dict,
        fixtures: list,
        container: Any,
        key: str,
        event_key: str,
        details: str = "",
    ) -> None:
        home = str(fixture.get("home") or fixture.get("home_team") or "").strip()
        away = str(fixture.get("away") or fixture.get("away_team") or "").strip()
        country, match_time = self._parse_event_details(details, home, away)
        if event_key not in MATCH_STATE_EVENTS and country not in {home, away}:
            await self._ack(ctx, f"Country must be `{home}` or `{away}` for that event.")
            return
        if event_key in MATCH_STATE_EVENTS:
            # Match-state controls are intentionally team-neutral one-tap
            # updates, even if an operator accidentally provides extra text.
            country = ""
            match_time = ""

        live_stats = fixture.get("live_stats") if isinstance(fixture.get("live_stats"), list) else []
        if event_key == "disallowed_goal":
            # Disallowing a goal reverses the latest matching goal event while
            # retaining a separate audit-style timeline entry for Discord.
            removed_goal = False
            for idx in range(len(live_stats) - 1, -1, -1):
                stat = live_stats[idx]
                if (
                    isinstance(stat, dict)
                    and stat.get("event_type") == "goal"
                    and stat.get("country") == country
                ):
                    del live_stats[idx]
                    removed_goal = True
                    break
            if not removed_goal:
                await self._ack(ctx, f"No goal found to disallow for `{country}`.")
                return

        home_score, away_score = self._score_from_live_stats(fixture, home, away)
        if event_key == "goal":
            home_score += 1 if country == home else 0
            away_score += 1 if country == away else 0
        message = f"{home} {home_score} - {away_score} {away}"
        live_stats.append({
            "event_type": event_key,
            "label": EVENT_LABELS[event_key],
            "message": message,
            "country": country,
            "match_time": match_time,
            "ts": int(time.time()),
        })
        fixture["live_stats"] = sort_match_events(live_stats)[-100:]
        self._save_fixtures(fixtures, container, key)
        self._enqueue_command("quick_match_announcement", {
            "fixture_id": self._fixture_id(fixture),
            "home": home,
            "away": away,
            "event_type": event_key,
            "event_label": EVENT_LABELS[event_key],
            "message": message,
            "match_time": match_time,
            "home_score": home_score,
            "away_score": away_score,
            "country": country if event_key not in MATCH_STATE_EVENTS else "",
            "channel": self._fixture_channel(fixture),
            "live_stats": fixture["live_stats"],
        })
        await self._ack(ctx, f"Queued {EVENT_LABELS[event_key]} for {home} vs {away}.")

    def _queue_fixture_result_embed(self, fixture: dict, *, corrected: bool = False) -> tuple[bool, str]:
        """Queue a full-time result embed from the fixture's persisted result."""
        home = str(fixture.get("home") or fixture.get("home_team") or "").strip()
        away = str(fixture.get("away") or fixture.get("away_team") or "").strip()
        home_score, away_score = self._fixture_score(fixture)
        if home_score is None or away_score is None:
            return False, "That fixture does not have a saved score yet."

        side = str(fixture.get("winner_side") or "").strip().lower()
        if not side:
            side = "home" if home_score > away_score else "away" if away_score > home_score else "draw"
        if side not in {"home", "away", "draw"}:
            return False, "That fixture has an invalid saved winner side."

        data = {
            "fixture_id": self._fixture_id(fixture),
            "home": home,
            "away": away,
            "home_score": home_score,
            "away_score": away_score,
            "winner_side": side,
            "channel": self._fixture_channel(fixture),
            "live_stats": fixture.get("live_stats") if isinstance(fixture.get("live_stats"), list) else [],
        }
        if corrected:
            data["corrected"] = True
        self._enqueue_command("fixture_result", data)
        return True, f"Queued full-time result embed: {home} {home_score} - {away_score} {away}."

    @commands.command(name="quick", aliases=["qevent", "matchevent"])
    @commands.has_permissions(manage_guild=True)
    async def quick_event(self, ctx: commands.Context, match_id: str, event_type: str, *, details: str = ""):
        """Post a live quick update: wc quick <match_id> <event> [country] [minute]."""
        await self._delete_command_message(ctx)
        event_key = str(event_type or "").strip().lower().replace("-", "_")
        if event_key not in EVENT_LABELS:
            await self._ack(ctx, "Invalid event. Use goal, disallowed_goal, penalty, var_decision, yellow_card, red_card, half_time, extra_time, extra_time_half_time, extra_time_full_time, or extra_time_penalties.")
            return

        fixture, fixtures, container, key = self._find_fixture(match_id)
        if not fixture:
            await self._ack(ctx, f"No fixture found for `{match_id}`.")
            return
        await self._queue_event_for_fixture(ctx, fixture, fixtures, container, key, event_key, details)

    async def _simple_channel_event(self, ctx: commands.Context, event_key: str, details: str = "") -> None:
        await self._delete_command_message(ctx)
        fixture, fixtures, container, key, error = self._resolve_channel_fixture(ctx)
        if error:
            await self._ack(ctx, error)
            return
        await self._queue_event_for_fixture(ctx, fixture, fixtures, container, key, event_key, details)

    @commands.command(name="goal")
    @commands.has_permissions(manage_guild=True)
    async def goal(self, ctx: commands.Context, *, details: str):
        """Queue a goal in this match channel: wc goal <country> [minute]."""
        await self._simple_channel_event(ctx, "goal", details)

    @commands.command(name="disallowgoal", aliases=["disallowedgoal", "nogoal"])
    @commands.has_permissions(manage_guild=True)
    async def disallow_goal(self, ctx: commands.Context, *, details: str):
        """Disallow the latest goal in this match channel: wc disallowgoal <country> [minute]."""
        await self._simple_channel_event(ctx, "disallowed_goal", details)

    @commands.command(name="penalty", aliases=["pen", "pk"])
    @commands.has_permissions(manage_guild=True)
    async def penalty(self, ctx: commands.Context, *, details: str):
        """Queue a penalty decision in this match channel: wc penalty <country> [minute]."""
        await self._simple_channel_event(ctx, "penalty", details)

    @commands.command(name="var", aliases=["vardecision", "varcheck"])
    @commands.has_permissions(manage_guild=True)
    async def var_decision(self, ctx: commands.Context, *, details: str):
        """Queue a VAR decision in this match channel: wc var <country> [minute]."""
        await self._simple_channel_event(ctx, "var_decision", details)

    @commands.command(name="et", aliases=["extratime"])
    @commands.has_permissions(manage_guild=True)
    async def extra_time(self, ctx: commands.Context):
        """Queue the start of extra time for this match channel: wc ET."""
        await self._simple_channel_event(ctx, "extra_time", "")

    @commands.command(name="etht", aliases=["ethalftime", "extratimehalf", "ethalf"])
    @commands.has_permissions(manage_guild=True)
    async def extra_time_half_time(self, ctx: commands.Context):
        """Queue extra-time half time for this match channel: wc ETHT."""
        await self._simple_channel_event(ctx, "extra_time_half_time", "")

    @commands.command(name="etft", aliases=["extratimefulltime", "etfulltime"])
    @commands.has_permissions(manage_guild=True)
    async def extra_time_full_time(self, ctx: commands.Context):
        """Queue full time after extra time for this match channel: wc ETFT."""
        await self._simple_channel_event(ctx, "extra_time_full_time", "")

    @commands.command(name="etp", aliases=["etpenalties", "extratimepenalties", "pens"])
    @commands.has_permissions(manage_guild=True)
    async def extra_time_penalties(self, ctx: commands.Context):
        """Queue penalties after extra time for this match channel: wc ETP."""
        await self._simple_channel_event(ctx, "extra_time_penalties", "")

    @commands.command(name="yellow", aliases=["yellowcard"])
    @commands.has_permissions(manage_guild=True)
    async def yellow(self, ctx: commands.Context, *, details: str):
        """Queue a yellow card in this match channel: wc yellow <country> [minute]."""
        await self._simple_channel_event(ctx, "yellow_card", details)

    @commands.command(name="red", aliases=["redcard"])
    @commands.has_permissions(manage_guild=True)
    async def red(self, ctx: commands.Context, *, details: str):
        """Queue a red card in this match channel: wc red <country> [minute]."""
        await self._simple_channel_event(ctx, "red_card", details)

    @commands.command(name="halftime", aliases=["half", "ht"])
    @commands.has_permissions(manage_guild=True)
    async def halftime(self, ctx: commands.Context):
        """Queue halftime for the active fixture in this match channel: wc halftime."""
        await self._simple_channel_event(ctx, "half_time", "")

    @commands.command(name="stagequick", aliases=["teamstage", "stageupdate"])
    @commands.has_permissions(manage_guild=True)
    async def stage_quick(self, ctx: commands.Context, team: str, *, stage: str):
        """Update a team's stage and queue the normal stage announcement: wc stagequick <team> <stage>."""
        await self._delete_command_message(ctx)
        next_stage = normalize_stage(stage)
        if next_stage not in STAGE_ALLOWED:
            await self._ack(ctx, "Invalid stage name.")
            return
        data = self._read_json(self.team_stage_path, {})
        if not isinstance(data, dict):
            data = {}
        prev_stage = normalize_stage(data.get(team)) or "Group Stage"
        data[team] = next_stage
        self._write_json_atomic(self.team_stage_path, data)
        progressed = stage_rank(next_stage) > stage_rank(prev_stage) >= 0
        eliminated = next_stage == "Eliminated" and prev_stage != "Eliminated"
        if progressed or eliminated:
            settings = self._read_json(self.settings_path, {})
            self._enqueue_command("team_stage_progress", {"team": team, "stage": next_stage, "previous_stage": prev_stage, "owner_ids": [], "channel": str(settings.get("STAGE_ANNOUNCE_CHANNEL") or "announcements")})
        await self._ack(ctx, f"Updated {team} to {next_stage}.")

    @commands.command(name="fulltime", aliases=["resultquick", "matchresult"])
    @commands.has_permissions(manage_guild=True)
    async def full_time(self, ctx: commands.Context, match_id: str, home_score: int, away_score: int, winner_side: str = ""):
        """Post the full-time result: wc fulltime <match_id> <home_score> <away_score> [home|away|draw]."""
        await self._delete_command_message(ctx)
        fixture, fixtures, container, key = self._find_fixture(match_id)
        if not fixture:
            await self._ack(ctx, f"No fixture found for `{match_id}`.")
            return

        home = str(fixture.get("home") or fixture.get("home_team") or "").strip()
        away = str(fixture.get("away") or fixture.get("away_team") or "").strip()
        side = str(winner_side or "").strip().lower()
        if not side:
            side = "home" if home_score > away_score else "away" if away_score > home_score else "draw"
        if side not in {"home", "away", "draw"}:
            await self._ack(ctx, "Winner side must be home, away, or draw.")
            return

        # Persist the score before queueing so the website and Discord embed are
        # based on the same result data.
        fixture["home_score"] = home_score
        fixture["away_score"] = away_score
        fixture["winner_side"] = side
        fixture["status"] = "completed"
        self._save_fixtures(fixtures, container, key)
        queued, message = self._queue_fixture_result_embed(fixture)
        await self._ack(ctx, message if queued else f"Saved result, but {message}")

    @commands.command(name="remakeembed", aliases=["remake", "remakeresult", "repostresult", "lastresult"])
    @commands.has_permissions(manage_guild=True)
    async def remake_embed(self, ctx: commands.Context):
        """Repost the last saved full-time embed: wc remakeembed.

        The current channel is preferred when it has completed fixtures;
        otherwise the latest completed fixture across the saved fixture list is
        used. The command only queues the public fixture result embed; it does
        not recalculate scores, resettle picks, or DM owners.
        """
        await self._delete_command_message(ctx)
        fixture, fixtures, container, key, error = self._resolve_last_completed_channel_fixture(ctx)
        if error:
            await self._ack(ctx, error)
            return

        queued, message = self._queue_fixture_result_embed(fixture)
        await self._ack(ctx, message if queued else message)


async def setup(bot: commands.Bot):
    await bot.add_cog(TextQuickOptions(bot))
