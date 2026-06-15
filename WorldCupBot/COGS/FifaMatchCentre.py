import hashlib
import io
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands, tasks

from stage_constants import STAGE_CHANNEL_MAP, normalize_stage


log = logging.getLogger(__name__)


class FifaMatchCentre(commands.Cog):
    """Capture a FIFA match-centre view and publish it to a Discord channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = getattr(bot, "BASE_DIR", None) or os.getcwd()
        self.config_path = os.path.join(self.base_dir, "config.json")
        self.settings_path = os.path.join(
            self.base_dir, "JSON", "fifa_match_centre_settings.json"
        )
        self.matches_path = os.path.join(self.base_dir, "JSON", "matches.json")
        self.legacy_matches_path = os.path.join(self.base_dir, "matches.json")
        self.team_meta_path = os.path.join(self.base_dir, "JSON", "team_meta.json")
        self.state_path = os.path.join(self.base_dir, "JSON", "fifa_match_centre_state.json")
        self._last_capture_at = 0.0
        self._last_image_hash = ""
        self._load_state()
        self._loop.start()

    def cog_unload(self):
        self._loop.cancel()

    def _load_json(self, path: str) -> dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _settings(self) -> dict[str, Any]:
        """Return Discord-managed settings, with legacy config keys as a fallback."""
        saved = self._load_json(self.settings_path)
        config = self._load_json(self.config_path)

        # Existing deployments may already have the original config.json keys.
        # Keep reading them until an administrator runs /fifamatchsetup, which
        # writes the easier-to-manage Discord settings file.
        enabled = saved.get(
            "enabled", config.get("FIFA_MATCH_CENTRE_ENABLED", False)
        )
        url = saved.get("url", config.get("FIFA_MATCH_CENTRE_URL", ""))
        fixture_id = saved.get("fixture_id", "")
        guild_id = saved.get("guild_id", "")
        interval = saved.get(
            "interval_minutes",
            config.get("FIFA_MATCH_CENTRE_INTERVAL_MINUTES", 5),
        )
        try:
            interval_minutes = max(1, min(60, int(interval or 5)))
        except (TypeError, ValueError):
            interval_minutes = 5

        return {
            "enabled": bool(enabled),
            "url": str(url or "").strip(),
            "fixture_id": str(fixture_id or "").strip(),
            "guild_id": str(guild_id or "").strip(),
            "interval_minutes": interval_minutes,
        }

    def _save_settings(self, settings: dict[str, Any]):
        """Atomically persist settings changed through Discord slash commands."""
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        temporary_path = f"{self.settings_path}.tmp"
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
        os.replace(temporary_path, self.settings_path)

    def _valid_fifa_url(self, url: str) -> bool:
        """Only allow HTTPS FIFA pages to be opened by the bot's browser."""
        parsed = urlparse(str(url or "").strip())
        hostname = (parsed.hostname or "").lower()
        return (
            parsed.scheme == "https"
            and bool(parsed.path)
            and (hostname == "fifa.com" or hostname.endswith(".fifa.com"))
        )

    def _load_matches(self) -> list[dict[str, Any]]:
        """Load fixtures from the same canonical storage used by match announcements."""
        for path in (self.matches_path, self.legacy_matches_path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except (OSError, ValueError):
                continue
            if isinstance(raw, dict):
                raw = raw.get("fixtures") or raw.get("matches") or []
            if isinstance(raw, list) and raw:
                return [fixture for fixture in raw if isinstance(fixture, dict)]
        return []

    def _find_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        target = str(fixture_id or "").strip().lower()
        for fixture in self._load_matches():
            candidate = str(
                fixture.get("id")
                or fixture.get("fixture_id")
                or fixture.get("match_id")
                or ""
            ).strip()
            if candidate.lower() == target:
                return fixture
        return None

    def _group_from_team_meta(self, home: str, away: str) -> str:
        raw = self._load_json(self.team_meta_path)
        groups = raw.get("groups") if isinstance(raw, dict) else None
        if not isinstance(groups, dict):
            return ""

        lookup: dict[str, str] = {}
        for group, teams in groups.items():
            if not isinstance(teams, list):
                continue
            for team in teams:
                lookup[str(team).strip().lower()] = str(group).strip().upper()
        home_group = lookup.get(str(home).strip().lower(), "")
        away_group = lookup.get(str(away).strip().lower(), "")
        if home_group and away_group and home_group == away_group:
            return home_group
        return home_group or away_group

    def _channel_name_for_fixture(self, fixture: dict[str, Any]) -> str:
        """Resolve the fixture's group or knockout channel using tournament rules."""
        home = str(fixture.get("home") or "").strip()
        away = str(fixture.get("away") or "").strip()
        stage = str(
            fixture.get("stage")
            or fixture.get("round")
            or fixture.get("phase")
            or fixture.get("tournament_stage")
            or ""
        ).strip()
        normalized_stage = normalize_stage(stage) or stage
        if normalized_stage and normalized_stage not in ("Group Stage", "Groups"):
            knockout_channel = STAGE_CHANNEL_MAP.get(normalized_stage)
            if knockout_channel:
                return knockout_channel

        group = str(fixture.get("group") or "").strip().upper()
        if not group:
            match = re.search(r"group\s*([a-l])", stage, re.IGNORECASE)
            group = match.group(1).upper() if match else ""
        if not group:
            group = self._group_from_team_meta(home, away)
        return f"group-{group.lower()}" if group else "announcements"

    def _guild_for_settings(self, settings: dict[str, Any]):
        try:
            guild_id = int(settings.get("guild_id") or 0)
        except (TypeError, ValueError):
            guild_id = 0
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            if guild:
                return guild
        return self.bot.guilds[0] if self.bot.guilds else None

    async def _resolve_fixture_channel(self, settings: dict[str, Any]):
        fixture = self._find_fixture(settings.get("fixture_id", ""))
        if fixture is None:
            return None
        guild = self._guild_for_settings(settings)
        if guild is None:
            return None
        channel_name = self._channel_name_for_fixture(fixture)
        return discord.utils.find(
            lambda channel: channel.name.lower() == channel_name.lower(),
            guild.text_channels,
        )

    def _load_state(self):
        state = self._load_json(self.state_path)
        self._last_capture_at = float(state.get("last_capture_at") or 0)
        self._last_image_hash = str(state.get("last_image_hash") or "")

    def _save_state(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        temporary_path = f"{self.state_path}.tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "last_capture_at": self._last_capture_at,
                        "last_image_hash": self._last_image_hash,
                    },
                    handle,
                )
            os.replace(temporary_path, self.state_path)
        except OSError:
            log.exception("Could not save FIFA match-centre state")

    def _capture_is_due(self, interval_minutes: int, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        return current_time - self._last_capture_at >= interval_minutes * 60

    async def _capture_match_centre(self, url: str) -> bytes:
        """
        Render FIFA's JavaScript application and return the useful match area as PNG.

        Discord cannot display third-party iframes. A browser-rendered image preserves
        the iframe/page presentation while the accompanying embed links to the live page.
        """
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1440, "height": 1100},
                device_scale_factor=1,
            )
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_load_state("networkidle", timeout=30_000)

                # Cookie banners can cover the score card, so accept them when FIFA
                # presents a conventional consent button. Missing buttons are harmless.
                for label in ("Accept All", "Accept all", "I Accept"):
                    button = page.get_by_role("button", name=label, exact=True)
                    if await button.count():
                        await button.first.click(timeout=3_000)
                        break

                await page.add_style_tag(
                    content="*,*::before,*::after{animation:none!important;transition:none!important}"
                )

                # Prefer the iframe body requested by the operator, then FIFA's main
                # match-centre container, and finally the full page as a safe fallback.
                for frame in page.frames[1:]:
                    body = frame.locator("body")
                    if await body.count() and await body.first.is_visible():
                        return await body.first.screenshot(type="png")

                for selector in ("main", "[data-testid*='match']", "#main-content"):
                    target = page.locator(selector).first
                    if await target.count() and await target.is_visible():
                        return await target.screenshot(type="png")

                return await page.screenshot(type="png", full_page=True)
            finally:
                await browser.close()

    def _build_embed(self, url: str) -> discord.Embed:
        embed = discord.Embed(
            title="FIFA Match Centre",
            description=(
                "Live match-centre snapshot. Use the link above for FIFA's "
                "interactive, continuously updated view."
            ),
            url=url,
            color=discord.Color.blue(),
        )
        embed.set_image(url="attachment://fifa-match-centre.png")
        embed.set_footer(text="Source: FIFA.com")
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def _publish(self, *, force: bool = False) -> str:
        settings = self._settings()
        if not settings["enabled"] and not force:
            return "disabled"
        if not settings["url"]:
            return "missing-url"
        if not settings["fixture_id"]:
            return "missing-fixture"

        image = await self._capture_match_centre(settings["url"])
        image_hash = hashlib.sha256(image).hexdigest()
        self._last_capture_at = time.time()

        if image_hash == self._last_image_hash and not force:
            self._save_state()
            return "unchanged"

        # Resolve the destination for every post so a fixture can move from a
        # provisional group into its correct knockout channel without reconfiguration.
        channel = await self._resolve_fixture_channel(settings)
        if channel is None:
            return "missing-channel"

        attachment = discord.File(io.BytesIO(image), filename="fifa-match-centre.png")
        await channel.send(file=attachment, embed=self._build_embed(settings["url"]))
        self._last_image_hash = image_hash
        self._save_state()
        return "published"

    @tasks.loop(seconds=60)
    async def _loop(self):
        settings = self._settings()
        if not settings["enabled"]:
            return
        if not self._capture_is_due(settings["interval_minutes"]):
            return
        try:
            await self._publish()
        except Exception:
            # A transient FIFA/browser failure should not unload the cog or stop
            # future updates. The exception remains visible in the bot log.
            log.exception("FIFA match-centre capture failed")

    @_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="refreshfifamatch",
        description="Immediately post a fresh FIFA match-centre snapshot.",
    )
    @app_commands.default_permissions(administrator=True)
    async def refresh_fifa_match(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self._publish(force=True)
        except Exception:
            log.exception("Manual FIFA match-centre capture failed")
            await interaction.followup.send(
                "The FIFA capture failed. Check the bot log and Playwright installation.",
                ephemeral=True,
            )
            return

        messages = {
            "published": "Posted a fresh FIFA match-centre snapshot.",
            "missing-url": "Run `/fifamatchsetup` and provide a FIFA match URL first.",
            "missing-fixture": "Run `/fifamatchsetup` and provide a fixture ID first.",
            "missing-channel": (
                "I could not find the group or stage channel for that fixture. "
                "Check `/fifamatchstatus` and the fixture data."
            ),
        }
        await interaction.followup.send(
            messages.get(result, f"FIFA capture result: {result}."),
            ephemeral=True,
        )

    @app_commands.command(
        name="fifamatchsetup",
        description="Configure automatic FIFA match-centre posts.",
    )
    @app_commands.describe(
        url="The FIFA match-centre URL to capture.",
        fixture_id="Fixture ID from the bot's match list, for example M12.",
        interval_minutes="How often to check for visual updates (1-60 minutes).",
    )
    @app_commands.default_permissions(administrator=True)
    async def fifa_match_setup(
        self,
        interaction: discord.Interaction,
        url: str,
        fixture_id: str,
        interval_minutes: app_commands.Range[int, 1, 60] = 5,
    ):
        """Save and enable the complete integration without editing server files."""
        clean_url = str(url or "").strip()
        clean_fixture_id = str(fixture_id or "").strip()
        if not self._valid_fifa_url(clean_url):
            await interaction.response.send_message(
                "Please provide an HTTPS URL hosted on `fifa.com`.",
                ephemeral=True,
            )
            return

        fixture = self._find_fixture(clean_fixture_id)
        if fixture is None:
            await interaction.response.send_message(
                (
                    f"I could not find fixture `{clean_fixture_id}` in the bot's match list. "
                    "Use the fixture ID shown in the admin match schedule."
                ),
                ephemeral=True,
            )
            return

        channel_name = self._channel_name_for_fixture(fixture)
        channel = discord.utils.find(
            lambda candidate: candidate.name.lower() == channel_name.lower(),
            interaction.guild.text_channels,
        )
        if channel is None:
            await interaction.response.send_message(
                (
                    f"Fixture `{clean_fixture_id}` belongs in `#{channel_name}`, but that "
                    "channel does not exist in this server."
                ),
                ephemeral=True,
            )
            return

        settings = {
            "enabled": True,
            "url": clean_url,
            "fixture_id": clean_fixture_id,
            "guild_id": str(interaction.guild.id),
            "interval_minutes": int(interval_minutes),
        }
        try:
            self._save_settings(settings)
        except OSError:
            log.exception("Could not save FIFA settings from Discord")
            await interaction.response.send_message(
                "I could not save the settings. Check the bot's filesystem permissions.",
                ephemeral=True,
            )
            return

        # Make the newly configured integration eligible on the next loop tick.
        self._last_capture_at = 0
        self._save_state()
        await interaction.response.send_message(
            (
                f"✅ FIFA match-centre posts are enabled in {channel.mention}.\n"
                f"**Fixture:** `{clean_fixture_id}`\n"
                f"**Update check:** every {int(interval_minutes)} minute(s)\n"
                f"**Match:** {clean_url}\n\n"
                "Use `/refreshfifamatch` to post the first snapshot immediately."
            ),
            ephemeral=True,
        )

    @fifa_match_setup.autocomplete("fixture_id")
    async def fifa_match_fixture_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Offer fixtures from matches.json so administrators need not memorize IDs."""
        query = str(current or "").strip().lower()
        choices: list[app_commands.Choice[str]] = []
        for fixture in self._load_matches():
            fixture_id = str(
                fixture.get("id")
                or fixture.get("fixture_id")
                or fixture.get("match_id")
                or ""
            ).strip()
            home = str(fixture.get("home") or "TBD").strip()
            away = str(fixture.get("away") or "TBD").strip()
            label = f"{fixture_id}: {home} vs {away}"
            if fixture_id and (not query or query in label.lower()):
                # Discord limits autocomplete labels to 100 characters and
                # responses to 25 choices.
                choices.append(app_commands.Choice(name=label[:100], value=fixture_id))
            if len(choices) == 25:
                break
        return choices

    @app_commands.command(
        name="fifamatchstatus",
        description="Show the current FIFA match-centre configuration.",
    )
    @app_commands.default_permissions(administrator=True)
    async def fifa_match_status(self, interaction: discord.Interaction):
        settings = self._settings()
        fixture = self._find_fixture(settings["fixture_id"])
        channel_name = self._channel_name_for_fixture(fixture) if fixture else ""
        channel = discord.utils.find(
            lambda candidate: candidate.name.lower() == channel_name.lower(),
            interaction.guild.text_channels,
        ) if channel_name else None
        channel_text = channel.mention if channel else (
            f"`#{channel_name}` (not found)" if channel_name else "Not resolved"
        )
        embed = discord.Embed(
            title="FIFA Match Centre Settings",
            color=discord.Color.green() if settings["enabled"] else discord.Color.orange(),
        )
        embed.add_field(
            name="Status",
            value="Enabled" if settings["enabled"] else "Disabled",
            inline=True,
        )
        embed.add_field(name="Channel", value=channel_text, inline=True)
        embed.add_field(
            name="Fixture",
            value=f"`{settings['fixture_id']}`" if settings["fixture_id"] else "Not configured",
            inline=True,
        )
        embed.add_field(
            name="Check interval",
            value=f"{settings['interval_minutes']} minute(s)",
            inline=True,
        )
        embed.add_field(
            name="FIFA URL",
            value=settings["url"] or "Not configured",
            inline=False,
        )
        embed.set_footer(
            text="Use /fifamatchsetup to change settings or /fifamatchdisable to stop posts."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="fifamatchdisable",
        description="Stop automatic FIFA match-centre posts.",
    )
    @app_commands.default_permissions(administrator=True)
    async def fifa_match_disable(self, interaction: discord.Interaction):
        settings = self._settings()
        settings["enabled"] = False
        try:
            self._save_settings(settings)
        except OSError:
            log.exception("Could not disable FIFA settings from Discord")
            await interaction.response.send_message(
                "I could not save the change. Check the bot's filesystem permissions.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "FIFA match-centre automatic posts are now disabled.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(FifaMatchCentre(bot))
