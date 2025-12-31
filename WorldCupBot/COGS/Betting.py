import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
import tempfile
import shutil
import random

BETS_FILE = "/home/pi/WorldCupDiscBot/WorldCupBot/JSON/bets.json"

def ensure_bets_file():
    os.makedirs(os.path.dirname(BETS_FILE), exist_ok=True)
    try:
        if not os.path.isfile(BETS_FILE):
            with open(BETS_FILE, "w") as f:
                json.dump([], f)
        else:
            with open(BETS_FILE, "r") as f:
                data = json.load(f)
            if not isinstance(data, list):
                with open(BETS_FILE, "w") as f:
                    json.dump([], f)
    except Exception:
        with open(BETS_FILE, "w") as f:
            json.dump([], f)

async def read_bets():
    loop = asyncio.get_running_loop()
    def _read():
        try:
            with open(BETS_FILE, "r") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return []
                for b in data:
                    for key in ("bet_id", "message_id", "option1_user_id", "option2_user_id", "winner_user_id", "channel_id"):
                        if key in b and b[key] is not None:
                            b[key] = str(b[key])
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    return await loop.run_in_executor(None, _read)

async def write_bets(bets):
    for b in bets:
        for key in ("bet_id", "message_id", "option1_user_id", "option2_user_id", "winner_user_id", "channel_id"):
            if key in b and b[key] is not None:
                b[key] = str(b[key])
    loop = asyncio.get_running_loop()
    def _write():
        dir_name = os.path.dirname(BETS_FILE)
        with tempfile.NamedTemporaryFile('w', delete=False, dir=dir_name, encoding='utf-8') as tf:
            json.dump(list(bets), tf, indent=4)
            tempname = tf.name
        shutil.move(tempname, BETS_FILE)
    await loop.run_in_executor(None, _write)

def generate_bet_id(existing_bets):
    while True:
        bet_id = str(random.randint(0, 99999)).zfill(5)
        if all(str(b.get('bet_id')) != bet_id for b in existing_bets):
            return bet_id

class BetModal(discord.ui.Modal, title="Create a Bet"):
    bet_title = discord.ui.TextInput(
        label="Bet Title",
        style=discord.TextStyle.short,
        max_length=80,
        placeholder="e.g. Will Argentina win their next match?",
        required=True
    )
    wager = discord.ui.TextInput(
        label="Wager",
        style=discord.TextStyle.short,
        max_length=50,
        placeholder="What is at stake? (e.g. 100 coins, 1 month Nitro, etc.)",
        required=True
    )
    option1 = discord.ui.TextInput(
        label="Option 1",
        style=discord.TextStyle.short,
        max_length=60,
        placeholder="Your prediction (e.g. Argentina wins)",
        required=True
    )
    option2 = discord.ui.TextInput(
        label="Option 2",
        style=discord.TextStyle.short,
        max_length=60,
        placeholder="Other prediction (e.g. France wins or draws)",
        required=True
    )

    def __init__(self, author, callback):
        super().__init__()
        self.author = author
        self._callback = callback

    async def on_submit(self, interaction: discord.Interaction):
        await self._callback(interaction, self)

class ClaimBetButton(discord.ui.View):
    def __init__(self, bet_id, bet_creator_id, option2, wager):
        super().__init__(timeout=None)
        self.bet_id = str(bet_id)
        self.bet_creator_id = str(bet_creator_id)
        self.option2 = option2
        self.wager = wager
        self.claimed = False

    @discord.ui.button(label="Claim Bet", style=discord.ButtonStyle.success)
    async def claim_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        if user_id == self.bet_creator_id:
            await interaction.followup.send("You cannot claim your own bet!", ephemeral=True)
            return

        bets = await read_bets()
        bet = next((b for b in bets if str(b.get('bet_id')) == self.bet_id), None)
        if bet is None:
            await interaction.followup.send("Bet not found in records.", ephemeral=True)
            return
        if bet.get("option2_user_id"):
            await interaction.followup.send("This bet has already been claimed!", ephemeral=True)
            return

        bet["option2_user_id"] = user_id
        bet["option2_user_name"] = str(interaction.user)
        await write_bets(bets)

        button.disabled = True
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_field_at(1, name=bet['option2'], value=f"Claimed By: {interaction.user.mention}", inline=False)
        embed.set_footer(text=f"{interaction.client.user.display_name} • All bets claimed are final.")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send(f'You have claimed: **{bet["option2"]}**', ephemeral=True)

class BettingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ensure_bets_file()

    @app_commands.command(name="makebet", description="Create a new public bet for others to claim.")
    async def makebet(self, interaction: discord.Interaction):
        modal = BetModal(interaction.user, self.process_bet)
        await interaction.response.send_modal(modal)

    async def process_bet(self, interaction: discord.Interaction, modal: BetModal):
        bets = await read_bets()
        bet_id = generate_bet_id(bets)

        user_id = str(interaction.user.id)
        channel_id = str(interaction.channel_id)

        embed = discord.Embed(
            title=f"📝 Bet: {modal.bet_title.value}",
            description=f"### Wager: {modal.wager.value}",
            color=discord.Color.gold()
        )
        embed.add_field(
            name=modal.option1.value, 
            value=f"Claimed By: {interaction.user.mention}",
            inline=False
        )
        embed.add_field(
            name=modal.option2.value, 
            value="Claimed By: Unclaimed",
            inline=False
        )
        embed.set_footer(text=f"{interaction.client.user.display_name} • All bets claimed are final.")
        embed.set_thumbnail(url=interaction.client.user.avatar.url if interaction.client.user.avatar else interaction.client.user.default_avatar.url)

        view = ClaimBetButton(
            bet_id=bet_id,
            bet_creator_id=user_id,
            option2=modal.option2.value,
            wager=modal.wager.value
        )

        await interaction.response.send_message(embed=embed, view=view)
        sent_message = await interaction.original_response()
        message_id = str(sent_message.id)

        bet_data = {
            "bet_id": bet_id,
            "message_id": message_id,
            "bet_title": modal.bet_title.value,
            "wager": modal.wager.value,
            "option1": modal.option1.value,
            "option2": modal.option2.value,
            "option1_user_id": user_id,
            "option1_user_name": str(interaction.user),
            "option2_user_id": None,
            "option2_user_name": None,
            "channel_id": channel_id,
            "winner": ""
        }
        bets.append(bet_data)
        await write_bets(bets)

async def setup(bot):
    await bot.add_cog(BettingCog(bot))
