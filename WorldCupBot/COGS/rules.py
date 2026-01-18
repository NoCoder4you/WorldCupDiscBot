import asyncio
from typing import List, Tuple

import discord
from discord.ext import commands


RULES_SECTIONS: List[Tuple[str, str]] = [
    ("# World Cup 2026 Discord Server Rules", ""),

    (
        "## 1. Authority, Scope, and Definitions",
        "- These rules apply to all members in all server channels and any DMs relating to the event.\n"
        "- Referees and designated staff are the final authority for registration, disputes, enforcement, and payouts.\n"
        "- Players can hold one or more teams and may be eligible for winnings. Spectators cannot hold or inherit teams.\n"
        "- Official dates, deadlines, and announcements use UTC unless explicitly stated otherwise."
    ),

    (
        "## 2. Respect and Conduct (Zero Ambiguity)",
        "- Harassment, discrimination, hate speech, racism, bigotry, threats, bullying, and targeted abuse are forbidden.\n"
        "- No flaming, baiting, dogpiling, or personal attacks - keep criticism about ideas, not people.\n"
        "- No spamming (messages, emojis, images, GIFs, reactions, or repeated pings).\n"
        "- No mic abuse in voice: screaming, soundboards, disruptive noise, or intentional disruption.\n"
        "- If a Referee or staff member tells you to stop, you stop - immediately."
    ),

    (
        "## 3. Server Etiquette and Content Rules",
        "- Use channels only for their intended purpose (match and team channels stay on-topic).\n"
        "- No NSFW content, gore, or otherwise inappropriate content - even as jokes.\n"
        "- No advertising, self-promotion, referral links, or external server invites without staff permission.\n"
        "- Do not mass-mention roles or staff. Do not ping individuals repeatedly.\n"
        "- English is the primary language for event administration and disputes unless staff state otherwise."
    ),

    (
        "## 4. Accounts, Identity, and Integrity",
        "- One Discord account per person for participation. Alt accounts are not allowed for entry, ownership, betting, or influence.\n"
        "- Impersonation of staff, Referees, or other users is forbidden.\n"
        "- Cheating, scripting, automation abuse, or exploit use is grounds for immediate removal and forfeiture.\n"
        "- Collusion, match-fixing, coordinated manipulation, or outcome interference is prohibited.\n"
        "- Do not share, request, or discuss methods to break rules or exploit systems."
    ),

    (
        "## 5. Entry, Eligibility, and Refunds",
        "- Entry requires: server join + verification + registration + entry fee payment (unless a waiver is granted by Referees).\n"
        "- Entry fees are a one-time Habbo credits payment per entry and are strictly non-refundable once paid.\n"
        "- Entry closes at 23:59 UTC on the announced date - late entries are not guaranteed.\n"
        "- Multiple entries are allowed only when each entry fee is paid and each entry is registered separately.\n"
        "- Leaving the event (or being removed) does not create any right to a refund."
    ),

    (
        "## 6. Team Assignment, Ownership, and Records",
        "- Teams are assigned randomly after entry closes. The draw is automated and impartial.\n"
        "- Team assignments are final: no swaps, sales, trades, transfers, or reassignment except via approved mechanisms in the Terms.\n"
        "- The bot record and the #players-and-teams tracking record are the authoritative source of ownership.\n"
        "- Referees may correct administrative errors where necessary.\n"
        "- If the tournament is postponed/cancelled (force majeure), assigned teams and status remain until it resumes."
    ),

    (
        "## 7. Split Ownership (Strict)",
        "- Only the current main owner may choose to share ownership. Nobody may pressure, coerce, or demand a split.\n"
        "- Splits must be processed through the official bot workflow and are logged for transparency.\n"
        "- Default splits are equal between registered co-owners. If equal split is not possible, the main owner receives the extra share.\n"
        "- Custom split ratios require approval from all co-owners and a Referee.\n"
        "- Referees may veto, modify, or reverse a split to protect fairness and rule compliance."
    ),

    (
        "## 8. Match Results, Standings, and Source of Truth",
        "- Official match results are determined by FIFA.\n"
        "- Bot updates reflect official results and are used for administration and leaderboards.\n"
        "- Temporary downtime does not change official outcomes - Referees may enter results manually to maintain continuity.\n"
        "- Attempting to interfere with standings, results, or leaderboard integrity is a disqualifying offence."
    ),

    (
        "## 9. Betting Rules (Virtual Items Only)",
        "- No real-money gambling - ever. No cash, crypto, gift cards, or real-world goods/services.\n"
        "- Bets may only involve virtual items with no real-world value (including Habbo credits and permitted in-server perks).\n"
        "- Bets are binding once both parties accept/claim and are public for audit.\n"
        "- Cancelling a bet must be handled via a Referee before the outcome is decided, and both parties must request cancellation.\n"
        "- Forbidden bets: politics, discrimination, hate-based themes, illegal activity, or external transactions."
    ),

    (
        "## 10. Privacy and Safety",
        "- Do not share personal or sensitive information (yours or anyone else's).\n"
        "- Doxxing, threats, blackmail, or sharing private content is strictly forbidden.\n"
        "- Discord Terms of Service and Community Guidelines apply at all times.\n"
        "- Staff may act on behaviour in DMs if it relates to the event or impacts member safety."
    ),

    (
        "## 11. Bot and Automation (Hands Off)",
        "- Do not attempt to exploit, crash, reverse-engineer, or interfere with bot operation.\n"
        "- Do not spam bot interactions or attempt unauthorised usage or bypass safeguards.\n"
        "- Bug discovery must be reported promptly. Deliberate exploitation results in forfeiture and removal.\n"
        "- The bot and services are provided as-is and as-available."
    ),

    (
        "## 12. Disputes, Evidence, and Enforcement",
        "- Disputes must be raised in writing via DM to a Referee within 24 hours of the incident.\n"
        "- Provide evidence (screenshots, message links, timestamps) where possible.\n"
        "- Penalties may escalate at Referee discretion: Warning - Mute - Team Forfeiture - Removal.\n"
        "- Severe offences (hate speech, doxxing, cheating, deliberate exploitation) may result in immediate removal.\n"
        "- Referee decisions are final."
    ),

    (
        "## 13. Leaving, Removal, Wait-List, and Reserves",
        "- If a Player leaves or is removed before the Final, their teams and eligibility are forfeited.\n"
        "- A forfeited team may be offered to the next wait-listed user, who has 24 hours to accept and pay.\n"
        "- If a wait-listed user does not claim within 24 hours, the team and any associated points may revert to the prize pool.\n"
        "- Reserve teams (if used) may be assigned to eligible late entrants before kick-off; unclaimed reserves may dissolve into the prize pool.\n"
        "- Active bets by a departing Player may be voided unless a Referee rules otherwise."
    ),

    (
        "## 14. Amendments and Acceptance",
        "- Rules and Terms may be updated by Referees and staff. Updates are announced in official channels.\n"
        "- Continued participation after an update constitutes acceptance of the updated Rules/Terms.\n"
        "- If anything here conflicts with the full Terms, the Terms take precedence."
    ),

    (
        "## 15. Enjoy the Football",
        "- Compete hard, stay respectful, and remember - it's a community event."
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


async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))
