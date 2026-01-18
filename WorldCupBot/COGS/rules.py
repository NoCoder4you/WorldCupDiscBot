import asyncio
from typing import List, Tuple

import discord
from discord.ext import commands

import role_utils


# =========================================================
# Rules content (summary of terms.html)
# =========================================================
# - Sent as multiple embeds for readability.
# - Text command only: wc rules


def _make_embed(title: str, body: str) -> discord.Embed:
    return discord.Embed(title=title, description=body, color=discord.Color.green())


RULE_PAGES: List[Tuple[str, str]] = [
    (
        "World Cup 2026 - Rules (Summary)",
        "These rules summarise the server Terms and Conditions. Referees enforce both.\n"
        "All official times and deadlines are in UTC.\n"
        "This is a community-run, entertainment-only event with no real-world financial stakes."
    ),
    (
        "1. Roles and authority",
        "- Referees are the final authority on registration, team assignment, disputes, discipline, and payouts.\n"
        "- Players hold one or more national teams and can be eligible for winnings.\n"
        "- Spectators can take part in permitted betting, but cannot hold, inherit, or be assigned teams."
    ),
    (
        "2. Joining, eligibility, and entry",
        "- Join the official server and complete verification.\n"
        "- Submit the official registration form confirming you have read and accepted the Terms.\n"
        "- You are only entered once the bot sends an official confirmation.\n"
        "- Entry fee is a one-time Habbo credits fee per entry, payable in full before confirmation.\n"
        "- No discounts, waivers, substitutions, or alternative entry methods.\n"
        "- Entry fees are non-refundable once paid, even if you withdraw, are removed, or go inactive.\n"
        "- Max ownership: 5 teams per Discord user at any time.\n"
        "- Entry closes at 23:59 UTC on the announced date.\n"
        "- No new entries or new team assignments after tournament kick-off (except Referee-corrected admin errors)."
    ),
    (
        "3. Team draw, reveal, and ownership record",
        "- Teams are randomly assigned by the bot after entry closes. The process is automated and impartial.\n"
        "- Draw results may be published publicly for transparency (including JSON ownership data).\n"
        "- Team assignments are final once published and cannot be swapped, transferred, sold, traded, or reassigned (except bot-sanctioned mechanisms).\n"
        "- Nicknames and roles may be updated for visibility, but the published records take priority if anything conflicts.\n"
        "- The #players-and-teams channel record is the authoritative source of ownership throughout the tournament.\n"
        "- Match outcomes and progression are based on official FIFA results (bot-posted outcomes are not appealable)."
    ),
    (
        "4. Splitting ownership",
        "- Only the current primary owner can approve sharing ownership of their team.\n"
        "- No Player, Spectator, or Referee may pressure or coerce an owner into splitting.\n"
        "- All splits must be initiated and finalised through the bot using `wc split <TEAM>`.\n"
        "- Default winnings split is equal among co-owners; if it cannot divide evenly, any remainder goes to the primary owner.\n"
        "- Custom split ratios require all co-owners to consent and a Referee to approve.\n"
        "- Referees can veto, modify, or reverse splits to protect fairness and integrity."
    ),
    (
        "5. Betting terms (virtual items only)",
        "- No real-money gambling - ever.\n"
        "- Bets may only involve in-server virtual items with no real-world value (including Habbo credits).\n"
        "- Forbidden: cash, crypto, gift cards, subscriptions, or real-world goods or services.\n"
        "- Bets must be created through the bot using `wc makebet` and only become active once another user accepts and takes an outcome.\n"
        "- Active bets can only be cancelled with consent from all involved parties, before the outcome is decided, and only via a Referee.\n"
        "- Forbidden: bets involving politics, discrimination, hate-based themes, or illegal activity.\n"
        "- Bet outcomes are determined solely by the official FIFA result.\n"
        "- Non-payment or avoidance can lead to betting restrictions and further enforcement."
    ),
    (
        "6. Winnings and payouts",
        "- Habbo marketplace tax applies to credit transfers (approximately 1% and controlled by Habbo, not Referees).\n"
        "- A fixed Referee administration percentage (Y%) is deducted from the total prize pool and disclosed before the draw.\n"
        "- Prize pool calculation: Total Input = (Number of teams x Entry Fee). New Total = Total Input minus admin %.\n"
        "- Distribution (unless announced otherwise): 1st 70% - 2nd 20% - 3rd 10%.\n"
        "- Split teams share winnings according to the approved split arrangement.\n"
        "- Payouts are made within 72 hours after the World Cup Final (subject to verification and platform availability).\n"
        "- Winners must claim within 72 hours of being notified or the prize may be forfeited."
    ),
    (
        "7. Conduct, safety, and enforcement",
        "- Follow Discord Terms of Service, Discord Community Guidelines, and the server rules at all times.\n"
        "- The Habbo Way applies to all sweepstake-related conduct, including DMs and external interactions connected to the event.\n"
        "- Prohibited: harassment, racism, bigotry, hate speech, discrimination, threats, trolling, spamming, mic abuse, or disruptive behaviour.\n"
        "- Enforcement can escalate: Warning -> Mute -> Team forfeiture -> Removal.\n"
        "- Serious misconduct (hate speech, doxxing, cheating, deliberate exploitation) can result in immediate removal.\n"
        "- Disputes must be sent in writing via DM to a Referee within 24 hours.\n"
        "- Referee decisions are final and binding."
    ),
    (
        "8. Technical issues, force majeure, leaving, and wait-list",
        "- The bot runs on a best-efforts basis and may experience downtime or delays.\n"
        "- Report suspected bugs or data issues to a Referee within 24 hours of discovery.\n"
        "- Do not exploit or interfere with the bot, automation, or data - abuse can lead to removal and forfeiture.\n"
        "- If FIFA postpones, suspends, cancels, or materially disrupts the tournament, teams remain assigned unless Referees decide otherwise; no refunds are issued for force-majeure disruption.\n"
        "- If a Player leaves or is removed before the Final, their teams are forfeited and may be offered to the wait-list.\n"
        "- Wait-list users do not pay unless offered a team. If offered, they have 24 hours to accept and pay.\n"
        "- A wait-list takeover may inherit the team's points unless Referees decide otherwise."
    ),
    (
        "9. Amendments",
        "- Referees may update Terms and rules and will announce updates in the server.\n"
        "- Continuing to participate after an update means you accept the updated Terms."
    ),
]

def _is_authorised(member: discord.Member) -> bool:
    return role_utils.has_referee(member)


class RulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _post_rules(self, channel: discord.abc.Messageable) -> None:
        for title, body in RULE_PAGES:
            embed = _make_embed(title, body)
            await channel.send(embed=embed)
            await asyncio.sleep(0.7)

    @commands.command(name="rules", help="Post the rules summary (Referee only).")
    async def rules_prefix(self, ctx: commands.Context) -> None:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            await ctx.send("Use this command inside the server.")
            return

        if not _is_authorised(ctx.author):
            await ctx.send("Only Referees can post rules.")
            return

        await self._post_rules(ctx.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))
