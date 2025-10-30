# COGS/WinnerWatcher.py
# Watches JSON/bets.json for changes to the "winner" field and updates the original Discord embed.
# Logs to console and posts updates to the channel defined by ADMIN_BET_CHANNEL in JSON/config.json.
# Polls every 1 minute. Silent background cog - no slash commands.

import os, json
from typing import List, Dict, Any, Optional

import discord
from discord.ext import commands, tasks

# ---------- File helpers ----------
def _json_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "JSON"))

def _path_in_json(filename: str) -> str:
    return os.path.join(_json_dir(), filename)

def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _read_bets() -> List[Dict[str, Any]]:
    """Read bets.json safely."""
    data = _read_json(_path_in_json("bets.json"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("bets"), list):
        return data["bets"]
    return []

def _read_config() -> Dict[str, Any]:
    cfg = _read_json(_path_in_json("config.json"))
    return cfg if isinstance(cfg, dict) else {}

# ---------- Discord helpers ----------
async def _fetch_message(bot: commands.Bot, channel_id: int, message_id: int) -> Optional[discord.Message]:
    """Fetch message safely from cache or API."""
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return None
    try:
        return await channel.fetch_message(message_id)
    except Exception:
        return None

def _format_embed(bet: Dict[str, Any]) -> discord.Embed:
    """Build a themed embed based on the bet data."""
    title = bet.get("bet_title") or "Bet"
    wager = bet.get("wager") or "-"
    opt1 = bet.get("option1") or "Option 1"
    opt2 = bet.get("option2") or "Option 2"
    winner = bet.get("winner")

    desc_lines = []
    if winner == "option1":
        desc_lines.append(f"**Winner:** {opt1}")
        desc_lines.append(f"Loser: ~~{opt2}~~")
    elif winner == "option2":
        desc_lines.append(f"**Winner:** {opt2}")
        desc_lines.append(f"Loser: ~~{opt1}~~")
    else:
        desc_lines.append("Winner: **TBD**")
        desc_lines.append(f"Options: {opt1} vs {opt2}")

    emb = discord.Embed(
        title=title,
        description="\n".join(desc_lines),
        color=0x00C896
    )
    emb.add_field(name="Wager", value=wager, inline=True)
    return emb

# ---------- Cog ----------
class WinnerWatcher(commands.Cog):
    """Background watcher that updates bet embeds when the winner changes in bets.json."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_winner: Dict[str, Optional[str]] = {}
        self._config = _read_config()
        self._admin_category = self._config.get("ADMIN_CATEGORY_NAME", "World Cup Admin")
        self._admin_bet_channel = self._config.get("ADMIN_BET_CHANNEL")
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    # ------------- Logging -------------
    async def _resolve_log_channel(self) -> Optional[discord.TextChannel]:
        """Find the channel where winner updates should be posted."""
        # 1) If ADMIN_BET_CHANNEL is an ID
        if isinstance(self._admin_bet_channel, (int, float, str)) and str(self._admin_bet_channel).isdigit():
            chan = self.bot.get_channel(int(self._admin_bet_channel))
            if isinstance(chan, discord.TextChannel):
                return chan

        # 2) If ADMIN_BET_CHANNEL is a name
        if isinstance(self._admin_bet_channel, str):
            for guild in self.bot.guilds:
                chan = discord.utils.get(guild.text_channels, name=self._admin_bet_channel)
                if isinstance(chan, discord.TextChannel):
                    return chan

        # 3) Fallback - bets-winner inside World Cup Admin category
        for guild in self.bot.guilds:
            cat = discord.utils.get(guild.categories, name=self._admin_category)
            if not cat:
                continue
            chan = discord.utils.get(cat.text_channels, name="bets-winner")
            if isinstance(chan, discord.TextChannel):
                return chan

        return None

    async def _log_update(self, content: str):
        """Print to console and post to configured log channel."""
        print(f"[WinnerWatcher] {content}")
        try:
            chan = await self._resolve_log_channel()
            if chan:
                await chan.send(content)
        except Exception:
            pass

    # ------------- Poll loop -------------
    @tasks.loop(minutes=1.0)
    async def poll(self):
        """Runs every 1 minute and updates embeds when winners change."""
        await self.bot.wait_until_ready()
        bets = _read_bets()

        for bet in bets:
            bet_id = str(bet.get("bet_id"))
            if not bet_id:
                continue

            winner = bet.get("winner")
            if self._last_winner.get(bet_id) == winner:
                continue  # no change observed

            chan_id = int(bet.get("channel_id") or 0)
            msg_id = int(bet.get("message_id") or 0)
            if not (chan_id and msg_id):
                self._last_winner[bet_id] = winner
                continue

            msg = await _fetch_message(self.bot, chan_id, msg_id)
            if msg is None:
                self._last_winner[bet_id] = winner
                continue

            opt1 = bet.get("option1") or "Option 1"
            opt2 = bet.get("option2") or "Option 2"
            if winner == "option1":
                human = f'Option 1 - "{opt1}"'
            elif winner == "option2":
                human = f'Option 2 - "{opt2}"'
            else:
                human = "TBD (cleared)"

            try:
                await msg.edit(embed=_format_embed(bet))
                await self._log_update(
                    f'Bet {bet_id} winner set to {human} | Jump: {msg.jump_url}'
                )
            except Exception:
                pass

            self._last_winner[bet_id] = winner

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WinnerWatcher(bot))
