import asyncio
from discord.ext import commands

# World Cup 2026 Rules
# Content aligned with the Terms & Conditions (terms.html).
# Each section is posted as a separate message for clarity.

RULES_SECTIONS = [
    (
        "# World Cup 2026 - Server Rules",
        """This sweepstake is for entertainment only and involves no real-world financial stakes.

By joining the server or interacting with the bot, you agree to comply with the Terms and Conditions, the server rules, and Habbo's community code of conduct (The Habbo Way).""",
    ),
    (
        "## 1. Roles and Authority",
        """- Referees are the final authority for registration, disputes, rules, and payouts.
- Players hold one or more teams and are eligible for winnings.
- Spectators may participate in betting but are not eligible to win, inherit, or be assigned teams.""",
    ),
    (
        "## 2. Entry, Eligibility, and Joining",
        """- Players must pay a one-time entry fee (Habbo credits) before the stated entry deadline.
- The entry fee amount is disclosed via the official Google registration form and a pinned server message. If there is any discrepancy, the pinned server message prevails.
- Entry fees are strictly non-refundable once paid, regardless of withdrawal, disqualification, inactivity, or event outcome.
- Entry closes at 23:59 UTC on the published entry close date. No new Players are accepted and no teams are newly assigned after tournament kick-off.
- Eligibility requirements (including Habbo account requirements) are set and published by Referees before entry.
- A single Discord user may register a maximum of five (5) entries (teams) at any time.
- Joining requires: join the server and verify, submit the Google registration form, pay the entry fee, and await confirmation by a Referee who registers you via /addplayer.""",
    ),
    (
        "## 3. Team Draw and Reveal",
        """- Teams are assigned randomly by the bot after the entry period closes.
- Assignment is impartial and automated. No manual bias, weighting, preference, or selective treatment is applied.
- Team assignments are final upon publication and may not be swapped, transferred, or reassigned except through explicitly bot-sanctioned mechanisms.
- Draw results may be published in a dedicated channel for transparency, including machine-readable files (for example JSON) showing assignments.
- Teams are revealed via a Referee announcement embed no later than one (1) week before kick-off.
- Nicknames, roles, and DMs may be used for convenience, but the Referee announcement and published records take precedence. DM delivery failures do not invalidate assignment.""",
    ),
    (
        "## 4. Time Zone and Deadlines",
        """- All official dates and times are stated in Coordinated Universal Time (UTC).
- Players are responsible for converting UTC times into their local time zone. Missed deadlines due to time-zone mistakes are not excused.""",
    ),
    (
        "## 5. Conduct and Platform Rules",
        """- You must comply with Discord's Terms of Service, Discord Community Guidelines, and the specific rules of this server.
- Prohibited conduct includes: foul or abusive language, harassment, racism, bigotry, hate speech, discrimination, trolling, spamming, mic abuse, threats, or any behaviour that is disruptive, unsafe, or undermines the integrity of the sweepstake.
- Conduct in DMs or external interactions may still be enforced where it has a demonstrable connection to the server or sweepstake.
- The Habbo Way applies at all times to sweepstake-related behaviour and communications.""",
    ),
    (
        "## 6. Splitting Ownership",
        """- Only the current primary owner of a team may initiate or approve a split.
- No Player, Spectator, or Referee may compel, coerce, pressure, or otherwise require a team owner to split.
- Splits are bot-managed using /split. Requests and outcomes may be logged publicly for transparency.
- Default split is equal shares between registered co-owners. If an equal split is not possible, the remaining share goes to the primary owner.
- Custom split ratios require explicit consent from all co-owners and approval by a Referee.
- Referees may review, veto, modify, or reverse a split at any time to protect fairness and rule compliance.""",
    ),
    (
        "## 7. Betting Rules",
        """- Bets must be made via /makebet. A bet becomes active only when a second user accepts and claims the opposing outcome.
- Bets may involve only virtual items with no real-world monetary value (including Habbo credits). No cash, cryptocurrency, gift cards, subscriptions, or real-world goods or services.
- Cancellation: an active bet may be cancelled only with the consent of all involved parties and before the outcome is decided. Cancellation requests must be submitted by DM to a Referee. The Referee's decision is final.

Forbidden bets:
- Any bet involving real money, external transactions, cash equivalents, or items/services with real-world monetary value.
- Any bet involving politics, discrimination, hate-based themes, or illegal activity.

Settlement and disputes:
- Bet outcomes are determined solely by the official result of the relevant FIFA World Cup 2026 match or event.
- Settlement occurs once the official result is confirmed and processed by the bot. Bot-posted outcomes are the authoritative determination.
- Postponed, abandoned, suspended, or voided matches remain unresolved until an official FIFA decision is issued. If no official resolution is provided, Referees may determine a reasonable outcome, including cancellation.
- Settled bets are final and are not reopened, except where Referees identify a clear administrative or technical error.

Non-payment:
- Bets must be settled promptly once outcome is confirmed.
- Failure or refusal to pay within a reasonable timeframe (as determined by Referees) is a breach and may result in restrictions from betting, loss of eligibility, removal of teams, or removal from the server.
- Restrictions do not remove any existing obligation to settle previously determined bets.

Clarity and scope:
- Bets must clearly specify the event, outcome conditions, and wagered items at creation.
- Ambiguous bets are interpreted by Referees (final).
- Bets must relate directly to FIFA World Cup 2026 matches, teams, or tournament outcomes.""",
    ),
    (
        "## 8. Winnings and Payouts",
        """- Habbo marketplace tax: payouts in Habbo credits are subject to the standard marketplace tax (approximately 1%), applied automatically at transfer.
- Administration deduction: a fixed percentage (Y%) is deducted from the total prize pool to cover operational and event costs. This percentage is set and disclosed by Referees before the draw.
- Prize distribution: New Total = (Number of teams x Entry Fee) minus administration deduction. 1st: 70% - 2nd: 20% - 3rd: 10%.
- Split teams: where a team is split, prizes are divided according to the approved split arrangement.
- Timing: prizes are distributed within 72 hours after the World Cup Final, subject to verification and platform availability.
- Claims: winners must claim prizes within 72 hours of notification. Unclaimed or forfeited prizes revert to the prize pool or are otherwise disposed of at Referees' discretion.""",
    ),
    (
        "## 9. Technical Issues, Bugs, and Liability",
        """- The bot is provided on a best-efforts basis and may experience downtime, delays, or errors.
- If needed, Referees may manually record or correct scores, results, or standings using official FIFA World Cup data to maintain continuity.
- Report suspected bugs, errors, or inconsistencies to a Referee within 24 hours of discovery.
- Deliberate exploitation or manipulation of bot behaviour, server mechanics, or technical faults is a serious breach and may result in immediate enforcement, including team forfeiture and removal from the server.
- Services are provided on an as-is and as-available basis. No warranty is provided regarding uptime, uninterrupted access, or error-free operation.
- To the maximum extent permitted, the bot owner, Referees, and server administrators are not liable for indirect loss, loss of opportunity, loss of virtual items, or disruption caused by technical failures, platform outages, or third-party issues.""",
    ),
    (
        "## 10. Disputes, Enforcement, and Amendments",
        """Enforcement:
- Referees may take enforcement action at their discretion, which may include: warning, mute, team forfeiture, and removal from the server, depending on severity and intent.
- For serious misconduct (including hate speech, doxxing, cheating, or deliberate exploitation), Referees may apply immediate penalties without escalation.

Disputes:
- Any dispute must be submitted in writing via DM to a Referee within 24 hours of the incident or decision. Late disputes may be disregarded.
- Referee decisions are final and binding. Match results and tournament data posted by the bot (based on official FIFA information) are not subject to appeal.

Amendments:
- Terms and rules may be amended, updated, or clarified by Referees or authorised staff.
- Changes are announced in #bot-updates and take effect immediately unless stated otherwise.
- Continued participation after changes are published constitutes acceptance. If you disagree, your remedy is to cease participation.""",
    ),
    (
        "## 11. Contact",
        """- For gameplay, rules, enforcement, and sweepstake issues: DM any Referee.
- For bot or technical issues: contact the user with Discord ID 298121351871594497.""",
    ),
]


class RulesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="rules", help="Post each World Cup 2026 rules section in a new message.")
    async def rules(self, ctx):
        for heading, body in RULES_SECTIONS:
            msg = f"{heading}\n{body}".strip()
            await ctx.send(msg)
            await asyncio.sleep(1)  # prevent rate limits


async def setup(bot):
    await bot.add_cog(RulesCog(bot))
