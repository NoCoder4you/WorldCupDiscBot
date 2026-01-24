import asyncio
from typing import List, Tuple

import discord
from discord.ext import commands



RULES_SECTIONS: List[Tuple[str, str]] = [
    ("# World Cup 2026 Discord Server Rules", ""),

    (
        "## 1. Authority, Scope, and Definitions",
        "- **Scope:** These rules apply to all members in all server channels and any DMs that relate to the Event.\n"
        "- **Authority:** Referees and designated staff have final authority on registration, eligibility, disputes, enforcement, and payouts.\n"
        "- **Definitions:**\n"
        "  - **Event:** The World Cup 2026 sweepstake and all related server activities.\n"
        "  - **Referee/Staff:** Users explicitly assigned moderation authority for the Event.\n"
        "  - **Player:** A registered, verified participant eligible to hold teams and win prizes.\n"
        "  - **Spectator:** A non-player. Spectators cannot hold teams or receive prizes from team ownership.\n"
        "  - **Team Ownership Record:** Bot data and the #players-and-teams record are the source of truth.\n"
        "  - **UTC:** All official times, deadlines, and announcements use UTC unless explicitly stated otherwise.\n"
        "- **Interpretation:** Where wording is unclear, Referees decide the meaning and outcome.\n"
        "- **Severability:** If any part is unenforceable, the rest still applies."
    ),

    (
        "## 2. Respect and Conduct",
        "- Harassment, discrimination, hate speech, racism, bigotry, threats, bullying, stalking, and targeted abuse are forbidden.\n"
        "- No personal attacks, flaming, baiting, dogpiling, or intimidation. Critique ideas, not people.\n"
        "- No spam, flooding, excessive reactions, or repeated pings. Do not disrupt channels or voice.\n"
        "- No mic abuse: screaming, soundboards, disruptive noise, or deliberate interference.\n"
        "- If a Referee or staff member instructs you to stop, you must stop immediately.\n"
        "- Attempts to argue enforcement in public channels may result in additional action."
    ),

    (
        "## 3. Server Etiquette and Content Rules",
        "- Use channels only for their intended purpose. Match and team channels must stay on-topic.\n"
        "- No NSFW content, sexual content, nudity, gore, shock content, or extreme violence, even as jokes.\n"
        "- No advertising, self-promotion, referral links, affiliate links, or external server invites without staff approval.\n"
        "- Do not mass-mention roles or staff. Do not repeatedly ping any individual.\n"
        "- English is the default language for Event administration and disputes unless staff state otherwise.\n"
        "- Staff may remove content that creates risk, drama, or disruption, even if not listed verbatim."
    ),

    (
        "## 4. Accounts, Identity, and Integrity",
        "- **One account rule:** One Discord account per person for participation. No alts for entry, ownership, betting, voting, or influence.\n"
        "- **Identity:** Impersonation of staff, Referees, or other users is forbidden.\n"
        "- **Integrity:** Cheating, scripting, automation abuse, exploit use, or bypassing safeguards is disqualifying.\n"
        "- **Manipulation:** Collusion, match-fixing, coordinated manipulation, bribery, or outcome interference is prohibited.\n"
        "- Do not share, request, or discuss instructions for breaking rules or exploiting systems.\n"
        "- Referees may require reasonable verification to confirm a single-user identity."
    ),

    (
        "## 5. Entry, Eligibility, and Refunds",
        "- Entry requires: server join + verification + registration + entry fee payment, unless a Referee grants a waiver.\n"
        "- Entry fees are a one-time Habbo credits payment per entry and are non-refundable once paid.\n"
        "- Entry closes at **23:59 UTC** on the announced date. Late entries are not guaranteed.\n"
        "- Multiple entries are allowed only if each entry fee is paid and each entry is registered separately.\n"
        "- Leaving the Event, being removed, or being disqualified does not create any right to a refund.\n"
        "- Referees may refuse or revoke entry at any time to protect fairness or safety."
    ),

    (
        "## 6. Team Assignment, Ownership, and Records",
        "- Teams are assigned randomly after entry closes. The draw is automated and intended to be impartial.\n"
        "- Team assignments are final. No swaps, sales, trades, transfers, or reassignment except via approved mechanisms in the Terms.\n"
        "- The bot record and the #players-and-teams tracking record are the authoritative source of ownership.\n"
        "- Referees may correct administrative errors, data mismatches, or record issues at any time.\n"
        "- If the tournament is postponed or cancelled (force majeure), assigned teams and status remain until it resumes or is closed."
    ),

    (
        "## 7. Split Ownership",
        "- Only the current main owner may offer a split. Pressuring, coercing, or harassing someone to split is forbidden.\n"
        "- Splits must be processed through the official bot workflow. Off-platform agreements do not override the record.\n"
        "- Default splits are equal between registered co-owners. If equal division is impossible, the main owner receives the extra share.\n"
        "- Custom split ratios require written approval from all co-owners and a Referee before becoming valid.\n"
        "- Referees may veto, modify, pause, or reverse a split to protect fairness, safety, or compliance.\n"
        "- Split owners accept that payout timing and handling follows the Referee decision and the recorded split."
    ),

    (
        "## 8. Match Results, Standings, and Source of Truth",
        "- Official match results are determined by FIFA.\n"
        "- Bot updates reflect official results and are used for administration and leaderboards.\n"
        "- Downtime, API issues, or delays do not change outcomes. Referees may enter results manually.\n"
        "- Attempting to interfere with standings, results, records, or leaderboard integrity is disqualifying.\n"
        "- Referees may correct calculation or display errors without creating a right to compensation."
    ),

    (
        "## 9. Betting Rules",
        "- No real-money gambling. No cash, crypto, gift cards, or real-world goods or services.\n"
        "- Bets may only involve virtual items with no real-world value, including Habbo credits and permitted in-server perks.\n"
        "- Bets are binding once both parties accept or claim in the official workflow.\n"
        "- A bet may be cancelled only before the outcome is decided, only with both parties requesting, and only via a Referee.\n"
        "- Forbidden bets include: politics, discrimination, hate-based themes, illegal activity, or any external transactions.\n"
        "- Attempts to evade these rules by wording, proxies, or side-deals are treated as violations."
    ),

    (
        "## 10. Privacy and Safety",
        "- Do not share personal or sensitive information (yours or anyone else's).\n"
        "- Doxxing, threats, blackmail, extortion, stalking, or sharing private content is strictly forbidden.\n"
        "- Discord Terms of Service and Community Guidelines apply at all times.\n"
        "- Staff may act on behaviour in DMs if it relates to the Event, impacts safety, or affects the community.\n"
        "- Report safety concerns to Referees promptly. False or bad-faith reports may be sanctioned."
    ),

    (
        "## 11. Bot and Automation",
        "- Do not exploit, crash, reverse-engineer, probe, or interfere with bot operation or services.\n"
        "- Do not spam bot interactions, brute-force inputs, or attempt unauthorised usage or bypass safeguards.\n"
        "- Bugs must be reported promptly. Deliberate exploitation results in forfeiture and removal.\n"
        "- The bot and services are provided as-is and as-available. Uptime is not guaranteed."
    ),

    (
        "## 12. Disputes, Evidence, and Enforcement",
        "- Disputes must be raised in writing via DM to a Referee within **24 hours** of the incident or discovery.\n"
        "- Provide evidence where possible: message links, screenshots, timestamps, and relevant context.\n"
        "- Referees may request additional evidence or statements and may set deadlines for responses.\n"
        "- Enforcement may escalate at Referee discretion: Warning - Mute - Team Forfeiture - Disqualification - Removal.\n"
        "- Severe offences (hate speech, doxxing, cheating, deliberate exploitation, threats) may result in immediate removal.\n"
        "- Referee decisions are final, including decisions about credibility, evidence, and remedies."
    ),

    (
        "## 13. Leaving, Removal, Wait-List, and Reserves",
        "- If a Player leaves or is removed before the Final, their teams and eligibility are forfeited.\n"
        "- A forfeited team may be offered to the next wait-listed eligible user, who has **24 hours** to accept and pay.\n"
        "- If not claimed within 24 hours, the team and any associated points may revert to the prize pool.\n"
        "- Reserve teams, if used, may be assigned to eligible late entrants before kick-off. Unclaimed reserves dissolve into the prize pool.\n"
        "- Active bets involving a departing or removed user may be voided unless a Referee rules otherwise."
    ),

    (
        "## 14. Amendments and Acceptance",
        "- Rules and Terms may be updated by Referees and staff. Updates are announced in official channels.\n"
        "- Continued participation after an update constitutes acceptance of the updated Rules and Terms.\n"
        "- If anything here conflicts with the full Terms, the Terms take precedence.\n"
        "- Referees may apply urgent changes immediately to address safety, abuse, or fairness issues."
    ),

    (
        "## 15. Enjoy the Football",
        "- Compete hard, stay respectful, and remember this is a community event."
    ),
]


class RulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="rules", help="Post the World Cup 2026 rules in this channel.")
    async def rules(self, ctx: commands.Context):
        for heading, body in RULES_SECTIONS:
            msg = f"{heading}\n{body}".strip()
            await ctx.send(msg)
            await asyncio.sleep(1)  # gentle rate-limit protection

        thumbnail_url = None
        if self.bot.user and self.bot.user.display_avatar:
            thumbnail_url = self.bot.user.display_avatar.url

        embed = discord.Embed(
            title="Server Rules",
            description=(
                "By reacting to this message with the green tick, you confirm that you agree to all of "
                "the rules outlined above and acknowledge that these rules may be subject to change."
            ),
            color=discord.Color.blue(),
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        embed.set_footer(text="World Cup 2026 - Server Rules")

        rules_message = await ctx.send(embed=embed)
        try:
            await rules_message.add_reaction("✅")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))
