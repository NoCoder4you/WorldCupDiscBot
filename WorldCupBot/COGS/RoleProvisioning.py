import json
import logging
from pathlib import Path

from discord.ext import commands

from COGS.role_utils import has_root

BASE_DIR = Path(__file__).resolve().parents[1]
JSON_DIR = BASE_DIR / "JSON"
TEAM_META_FILE = JSON_DIR / "team_meta.json"
COUNTRYROLES_FILE = JSON_DIR / "countryroles.json"
GROUPROLES_FILE = JSON_DIR / "grouproles.json"
COUNTRY_GROUP_LINKS_FILE = JSON_DIR / "country_group_links.json"

log = logging.getLogger(__name__)


def load_json(path: Path, default):
    """Load JSON content from disk and gracefully return a default value."""
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    """Persist JSON data with indentation for easy manual inspection."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)



def coerce_country_role_ids(country_roles: dict) -> dict:
    """Return a compatibility-safe mapping of country -> scalar role_id."""
    out = {}
    for team, raw in (country_roles or {}).items():
        if isinstance(raw, dict):
            role_id = raw.get("role_id")
            if role_id:
                out[team] = role_id
        elif raw:
            out[team] = raw
    return out

def group_label(group_key: str) -> str:
    """Normalize stored group keys (A, B...) into role names (Group A, Group B...)."""
    cleaned = str(group_key or "").strip().upper()
    return f"Group {cleaned}" if cleaned else ""


class RoleProvisioning(commands.Cog):
    """Create and store role IDs for teams and groups used in the World Cup flow."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setupgrouproles")
    async def setup_group_roles(self, ctx: commands.Context):
        """Text command: create/refresh Group A-L and country roles from team metadata."""
        # Keep this as a text command (`wc setupgrouproles`) per admin workflow.
        if not has_root(ctx.author):
            await ctx.send("You are not authorized to use this command. (Root role required)")
            return

        if not ctx.guild:
            await ctx.send("This command must be used in a server.")
            return

        team_meta = load_json(TEAM_META_FILE, {"groups": {}})
        groups = team_meta.get("groups", {}) if isinstance(team_meta, dict) else {}

        if not groups:
            await ctx.send("No group data found in team_meta.json.")
            return

        existing_roles = {r.name: r for r in ctx.guild.roles}
        country_roles = load_json(COUNTRYROLES_FILE, {})
        group_roles = load_json(GROUPROLES_FILE, {})
        country_group_links = load_json(COUNTRY_GROUP_LINKS_FILE, {})

        created_groups = 0
        created_countries = 0

        for group_key, countries in groups.items():
            g_label = group_label(group_key)
            if not g_label:
                continue

            role = existing_roles.get(g_label)
            if not role:
                role = await ctx.guild.create_role(
                    name=g_label,
                    mentionable=True,
                    reason="World Cup group role provisioning"
                )
                existing_roles[g_label] = role
                created_groups += 1

            group_roles[g_label] = role.id

            # Keep countryroles.json scalar (country -> role_id) for compatibility with
            # announcers that cast mapping values directly with int(...). Group linkage
            # metadata is persisted separately in country_group_links.json.
            for country in countries:
                if not country or country == "TBA":
                    continue

                country_role = existing_roles.get(country)
                if not country_role:
                    country_role = await ctx.guild.create_role(
                        name=country,
                        mentionable=True,
                        reason=f"World Cup country role provisioning ({g_label})"
                    )
                    existing_roles[country] = country_role
                    created_countries += 1

                country_roles[country] = country_role.id
                country_group_links[country] = {
                    "group": g_label,
                    "group_role_id": role.id,
                }

        # If older runs stored dict entries in countryroles.json, coerce them back
        # to scalar IDs to restore ID lookups in announcer cogs.
        country_roles = coerce_country_role_ids(country_roles)

        save_json(COUNTRYROLES_FILE, country_roles)
        save_json(GROUPROLES_FILE, group_roles)
        save_json(COUNTRY_GROUP_LINKS_FILE, country_group_links)

        summary = (
            f"Group roles synced: {len(group_roles)} total ({created_groups} created).\n"
            f"Country roles synced: {len(country_roles)} total ({created_countries} created)."
        )
        await ctx.send(summary)
        log.info("Role provisioning completed in guild %s by %s", ctx.guild.id, ctx.author.id)


async def setup(bot):
    await bot.add_cog(RoleProvisioning(bot))
