import os
import json
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
    data = _read_json(_path_in_json("bets.json"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("bets"), list):
        return data["bets"]
    return []

def _read_config() -> Dict[str, Any]:
    cfg = _read_json(_path_in_json("config.json"))
    if not isinstance(cfg, dict):
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            root_cfg = os.path.join(here, "..", "config.json")
            cfg = _read_json(os.path.normpath(root_cfg))
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception:
            cfg = {}
    return cfg

# ---------- Discord helpers ----------
async def _fetch_message(bot: commands.Bot, channel_id: int, message_id: int) -> Optional[discord.Message]:
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

# ---------- Fancy original embed ----------
def _format_embed_for_bet_card(bet: Dict[str, Any]) -> discord.Embed:
    bet_id = bet.get("bet_id") or "Unknown"
    title = bet.get("bet_title") or f"Bet {bet_id}"
    wager = bet.get("wager") or "-"
    opt1 = bet.get("option1") or "Option 1"
    opt2 = bet.get("option2") or "Option 2"
    winner = bet.get("winner")

    desc = f"⚔️ **{opt1}** vs **{opt2}**\n\n"

    if winner == "option1":
        desc += f"🏆 **Winner:** {opt1}\n"
        desc += f"-# ~~Loser: {opt2}~~\n"
    elif winner == "option2":
        desc += f"🏆 **Winner:** {opt2}\n"
        desc += f"-# ~~Loser: {opt1}~~\n"
    else:
        desc += "⏳ **Winner:** TBD\n"

    desc += f"\n💰 **Wager:** {wager}"

    color = 0x00C896 if winner not in ("option1", "option2") else 0xFFD700

    emb = discord.Embed(title=title, description=desc, color=color)
    footer_text = "World Cup 2026 • Winner Declared" if winner in ("option1", "option2") else "World Cup 2026 • Awaiting Result"
    emb.set_footer(text=footer_text)
    return emb

# ---------- Admin embed ----------
def _build_admin_embed(bet: Dict[str, Any], msg_url: Optional[str]) -> Optional[discord.Embed]:
    winner = bet.get("winner")
    if winner not in ("option1", "option2"):
        return None

    bet_id = bet.get("bet_id") or "Unknown"
    winner_option = bet.get("option1") if winner == "option1" else bet.get("option2")
    winner_option = winner_option or "Unknown option"

    desc = f"## Winner\n{winner_option}\n-# [Jump to bet]({msg_url})" if msg_url else f"## Winner\n{winner_option}"

    emb = discord.Embed(
        title=f"Bet {bet_id}",
        description=desc,
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    emb.set_footer(text="World Cup 2026 • Winner declared")
    return emb

# ---------- Cog ----------
class WinnerWatcher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_winner: Dict[str, Optional[str]] = {}
        self._announced: Dict[str, Optional[str]] = {}
        self._config = _read_config()
        self._admin_category = self._config.get("ADMIN_CATEGORY_NAME", "World Cup Admin")
        self._admin_bet_channel = self._config.get("ADMIN_BET_CHANNEL") or "_admin_bet_channel"
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    async def _resolve_log_channel(self) -> Optional[discord.TextChannel]:
        if isinstance(self._admin_bet_channel, (int, float, str)) and str(self._admin_bet_channel).isdigit():
            chan = self.bot.get_channel(int(self._admin_bet_channel))
            if isinstance(chan, discord.TextChannel):
                return chan

        if isinstance(self._admin_bet_channel, str):
            for guild in self.bot.guilds:
                chan = discord.utils.get(guild.text_channels, name=str(self._admin_bet_channel))
                if isinstance(chan, discord.TextChannel):
                    return chan

        for guild in self.bot.guilds:
            cat = discord.utils.get(guild.categories, name=self._admin_category)
            if not cat:
                continue
            chan = discord.utils.get(cat.text_channels, name="bets-winner")
            if isinstance(chan, discord.TextChannel):
                return chan
        return None

    async def _post_admin_embed(self, embed: discord.Embed):
        try:
            chan = await self._resolve_log_channel()
            if chan and embed:
                await chan.send(embed=embed)
        except Exception:
            pass

    @tasks.loop(minutes=1.0)
    async def poll(self):
        await self.bot.wait_until_ready()
        bets = _read_bets()

        for bet in bets:
            bet_id = str(bet.get("bet_id") or "").strip()
            if not bet_id:
                continue

            winner = bet.get("winner")
            prev_winner = self._last_winner.get(bet_id)

            chan_id = int(bet.get("channel_id") or 0)
            msg_id = int(bet.get("message_id") or 0)

            if chan_id and msg_id:
                msg = await _fetch_message(self.bot, chan_id, msg_id)
                if msg is not None:
                    try:
                        await msg.edit(embed=_format_embed_for_bet_card(bet))
                    except Exception:
                        pass

                    if winner in ("option1", "option2") and self._announced.get(bet_id) != winner:
                        admin_embed = _build_admin_embed(bet, msg.jump_url)
                        if admin_embed is not None:
                            await self._post_admin_embed(admin_embed)
                        self._announced[bet_id] = winner

            self._last_winner[bet_id] = winner

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WinnerWatcher(bot))
