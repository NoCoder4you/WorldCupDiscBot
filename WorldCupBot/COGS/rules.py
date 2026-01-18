import asyncio
from typing import List, Tuple

import discord
from discord.ext import commands

from role_utils import is_referee  # existing helper in your project


# =========================
# Rules content
# =========================
# Must stay aligned with Terms & Conditions
# Each section is kept below Discord's 2000 character limit

RULES_SECTIONS: List[Tuple[str, str]] = [
    (
        "# World Cup 2026 Rules Summary",
        "These rules summarise the official Terms & Conditions. Referees enforce both."
    ),

    (
        "## 1. Authority and Roles",
        "- Referees are the final authority on all matters including registration, disputes, enforcement, and payouts.\n"
        "- Players hold one or more teams and are eligible for winnings.\n"
        "- Spectators may take part in permitted betting but cannot hold or inherit teams."
    ),

    (
        "## 2. Entry, Eligibility, and Deadlines",
        "- You must join the official Discord server, complete verification, and submit the registration form.\n"
        "- Entry is confirmed only once a Referee registers you via the bot.\n"
        "- Entry fees are paid in Habbo credits and are strictly non-refundable once paid.\n"
        "- Entry closes at 23:59 UTC on the announced date.\n"
        "- No late entries or new team assignments occur after tournament kick-off, except to correct Referee errors.\n"
        "- A single Discord user may hold multiple teams only if each entry is paid and registered separately."
    ),

    (
        "## 3. Team Assignment and Ownership",
        "- Teams are assigned randomly by the bot after entry closes.\n"
        "- Draw results may be published publicly, including JSON files, for transparency.\n"
        "- Team assignments are final and cannot be swapped, sold, traded, or transferred except through bot-approved systems.\n"
        "- The #players-and-teams channel is the authoritative ownership record."
    ),

    (
        "## 4. Split Ownership",
        "- Only the current main owner may approve a split.\n"
        "- No user may pressure or coerce another user into splitting a team.\n"
        "- All splits must be initiated through the bot.\n"
        "- Default splits are equal between co-owners; any remainder goes to the main owner.\n"
        "- Custom ratios require approval from all parties and a Referee.\n"
        "- Referees may veto, modify, or reverse splits to protect fairness."
    ),

    (
        "## 5. Channels and Match Discussion",
        "- World Cup discussion must stay within World Cup channels.\n"
        "- Match channels and voice channels must remain on-topic.\n"
        "- Official match results are determined by FIFA. Bot standings reflect public match data.\n"
        "- Temporary outages or delays do not change official outcomes."
    ),

    (
        "## 6. Conduct and Behaviour",
        "- Discord Terms of Service and server rules apply at all times.\n"
        "- Prohibited behaviour includes harassment, hate speech, racism, threats, trolling, spam, mic abuse, or impersonation.\n"
        "- No doxxing or sharing personal information.\n"
        "- Behaviour in DMs may still be enforced if related to the sweepstake or server."
    ),

    (
        "## 7. Betting Rules",
        "- No real-money gambling is allowed.\n"
        "- Bets may only involve virtual items such as Habbo credits.\n"
        "- Bets must be created and accepted through the bot.\n"
        "- Once active, bets are locked unless a Referee approves cancellation.\n"
        "- Bets involving politics, discrimination, or illegal activity are forbidden."
    ),

    (
        "## 8. Enforcement and Disputes",
        "- Penalties may include warnings, mutes, team forfeiture, or removal.\n"
        "- Severe misconduct may result in immediate removal.\n"
        "- Disputes must be submitted via DM to a Referee within 24 hours.\n"
        "- Referee decisions are final and not appealable."
    ),

    (
        "## 9. Bugs and Exploits",
        "- Do not exploit or abuse bugs or automation.\n"
        "- Report bugs as soon as possible.\n"
        "- Deliberate exploitation results in removal and forfeiture."
    ),

    (
        "## 10. Leaving and Wait-List",
        "- If a Player leaves before the Final, their teams are forfeited.\n"
        "- Teams may be offered to wait-listed users who have 24 hours to accept and pay.\n"
        "- Leaving does not entitle a user to any refund."
    ),

    (
        "## 11. Amendments",
        "- Rules and Terms may be updated by Referees.\n"
        "- Updates are announced in #bot-updates.\n"
        "- Continued participation constitutes acceptance of updated rules."
    ),
]


# =========================
# Cog
# =========================

class RulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _post_rules(self, channel: discord.abc.Messageable):
        for title, body in RULES_SECTIONS:
            message = f"{title}\n{body}"
            await channel.send(message)
            await asyncio.sleep(1)  # gentle rate-limit protection

    @commands.command(name="rules", help="Post the official World Cup rules (Referee only).")
    async def rules(self, ctx: commands.Context):
        if ctx.guild and not is_referee(ctx.author):
            await ctx.send("Only Referees may post the rules.")
            return

        await self._post_rules(ctx.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))
