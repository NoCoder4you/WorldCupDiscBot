import discord
from discord.ext import commands
import asyncio

RULES_SECTIONS = [
    ("# World Cup 2026 Discord Server Rules", ""),
    ("## 1. Respect & Conduct", 
"""- Treat all members with respect at all times.
- No harassment, discrimination, hate speech or bullying.
- Avoid toxic behaviour, flaming, baiting or personal attacks.
- No spamming or flooding channels with messages, emojis or memes.
- Respect decisions made by staff, referees and organisers."""),
    ("## 2. Server Etiquette",
"""- Use the correct channels for their intended purposes.
- Do not ping staff or other users excessively.
- NSFW, offensive or inappropriate content is strictly forbidden.
- English is the preferred language for communication unless otherwise stated.
- No self-promotion, advertising or sharing external server invites without permission."""),
    ("## 3. Tournament Integrity",
"""- One account per participant. Alternate, secondary or ‘alt’ accounts are not allowed.
- All participants must follow "The Habbo Way" and maintain sportsmanship throughout the tournament.
- Cheating, exploiting or scripting will result in immediate removal.
- Collusion, match-fixing or manipulating outcomes is strictly prohibited.
- Decisions from referees are final unless overturned by staff review."""),
    ("## 4. Team Ownership & Entries",
"""- Teams are assigned at random and may not be traded, sold or swapped without approval.
- Ownership splits are only valid through the `/split` command - only the main owner can accept.
- All winnings will be divided according to current split ownership as recorded.
- Only users with the “Referee” role may use commands like `/addplayer` and `/reveal`.
- Attempts to manipulate team ownership or assignment will result in disqualification."""),
    ("## 5. Betting System",
"""- Bets may only be placed via the official `/makebet` command.
- All bets are public and final once claimed.
- Do not attempt to exploit, manipulate or falsify betting outcomes.
- Any abuse of the betting system will result in a ban from all betting activities."""),
    ("## 6. Channel Usage",
"""- Do not clutter team or match channels with off-topic discussion.
- Use voice channels respectfully – no excessive background noise or music.
- Spectators must not interfere with matches or team strategies.
- Use /report or alert referees if you see any rule violations."""),
    ("## 7. Privacy & Security",
"""- Do not share personal information (yours or others’) in public channels.
- No doxing, threatening or sharing sensitive/private content.
- All Discord Terms of Service and Community Guidelines apply at all times."""),
    ("## 8. Bot & Automation Rules",
"""- Do not attempt to exploit, crash or interfere with the bot’s operation.
- Only authorised commands may be used; refrain from command spam.
- Attempts to add the bot to unauthorised servers will be reported and denied automatically."""),
    ("## 9. Tournament Decisions & Disputes",
"""- Any disputes must be submitted via DM to the staff or through designated commands.
- The organisers reserve the right to update rules and make final decisions on disputes.
- Please abide by any schedule or announcement changes promptly."""),
    ("## 10. General Prohibited Behaviour",
"""- No impersonation of staff, referees or other players.
- No sharing or discussing cheats, exploits or methods to break rules.
- No backseat moderating – use the proper channels to report rule breaking."""),
    ("## 11. Miscellaneous",
"""- The staff may enforce penalties or bans at their discretion for behaviour that undermines the community or event, even if not explicitly listed.
- “The Habbo Way” must be followed throughout the server and tournament."""),
    ("## 12. Enjoy the Football!",
"""- Remember to enjoy the football, have fun and keep things in perspective – it’s just a game!"""),
]

class RulesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="rules", help="Post each World Cup 2026 rules section in a new message.")
    async def rules(self, ctx):
        for heading, body in RULES_SECTIONS:
            msg = f"{heading}\n{body}".strip()
            await ctx.send(msg)
            await asyncio.sleep(1)  # Prevent rate limit

async def setup(bot):
    await bot.add_cog(RulesCog(bot))
