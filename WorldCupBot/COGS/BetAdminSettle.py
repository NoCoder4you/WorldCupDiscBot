import discord
from discord.ext import commands
import json
import os

BETS_JSON = "/home/pi/WorldCupDiscBot/WorldCupBot/JSON/bets.json"
ADMIN_CHANNEL_ID = 1401717405260058674

def load_bets():
    with open(BETS_JSON, "r") as f:
        bets = json.load(f)
    for b in bets:
        for key in ("bet_id", "message_id", "option1_user_id", "option2_user_id", "winner_user_id", "channel_id"):
            if key in b and b[key] is not None:
                b[key] = str(b[key])
    return bets

def save_bets(bets):
    for b in bets:
        for key in ("bet_id", "message_id", "option1_user_id", "option2_user_id", "winner_user_id", "channel_id"):
            if key in b and b[key] is not None:
                b[key] = str(b[key])
    with open(BETS_JSON, "w") as f:
        json.dump(bets, f, indent=2)

class BetAdminSettle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if str(message.author.id) == str(self.bot.user.id):
            return
        if message.channel.id != ADMIN_CHANNEL_ID:
            return
        if not message.content.startswith("!bet settle"):
            return

        parts = message.content.strip().split()
        if len(parts) != 4:
            await message.channel.send("Usage: !bet settle <bet_id> <winner_user_id>")
            return

        _, _, bet_id, winner_id = parts
        bet_id = str(bet_id)
        winner_id = str(winner_id)
        bets = load_bets()
        bet = next((b for b in bets if str(b.get("bet_id")) == bet_id), None)
        if not bet:
            await message.channel.send("Bet not found.")
            return

        bet["winner_user_id"] = winner_id
        # NEW: set 'winner' field to the user id, leave blank until settled
        bet["winner"] = winner_id
        # if 'settled' key existed from older data, we can ignore/remove it gracefully
        if "settled" in bet:
            try:
                del bet["settled"]
            except Exception:
                pass
        save_bets(bets)

        msg_id = bet.get("message_id")
        channel_id = bet.get("channel_id")
        if not channel_id:
            await message.channel.send("Bet channel not tracked. (Missing channel_id)")
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await message.channel.send("Could not find bet channel.")
            return

        TROPHY = "🏆"
        winner_is_option1 = (winner_id == str(bet.get("option1_user_id")))
        winner_name = bet["option1_user_name"] if winner_is_option1 else bet["option2_user_name"]
        winner_prediction = bet.get('option1', '') if winner_is_option1 else bet.get('option2', '')

        loser_prediction = bet.get('option2','') if winner_is_option1 else bet.get('option1','')
        loser_user_id = bet.get("option2_user_id") if winner_is_option1 else bet.get("option1_user_id")
        loser_user_name = bet.get("option2_user_name") if winner_is_option1 else bet.get("option1_user_name")
        loser_mention = f"<@{loser_user_id}>" if loser_user_id else (loser_user_name or "-")
        loser_field = f"~~{loser_prediction}~~"
        loser_value = f"~~Claimed by: {loser_mention}~~"

        winner_field = f"{TROPHY} Winner {TROPHY}"
        heading = f"{TROPHY} {bet.get('bet_title', 'Bet')} {TROPHY}"
        winner_value = f"{TROPHY} **{winner_prediction}** {TROPHY}\n{TROPHY} **Winner:** <@{winner_id}> {TROPHY}"

        embed = discord.Embed(
            title=heading,
            description=f"{TROPHY} **Wager:** {bet.get('wager', '-')} {TROPHY}",
            color=discord.Color.gold()
        )
        embed.add_field(name=winner_field, value=winner_value, inline=False)
        embed.add_field(name=loser_field, value=loser_value, inline=False)
        embed.set_footer(text="World Cup 2026 • Bet Settled")

        success = False

        if msg_id:
            try:
                bet_msg = await channel.fetch_message(int(msg_id))
                await bet_msg.edit(embed=embed)
                await message.channel.send(f"Bet `{bet.get('bet_title')}` settled for <@{winner_id}>!")
                success = True
            except Exception:
                await message.channel.send("Could not fetch/edit original bet embed. Reposting result below...")

        if not success:
            await channel.send(embed=embed)
            await message.channel.send(f"Bet `{bet.get('bet_title')}` winner reposted in channel.")

async def setup(bot):
    await bot.add_cog(BetAdminSettle(bot))
