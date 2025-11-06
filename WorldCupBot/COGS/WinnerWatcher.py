import os
import json
from typing import List, Dict, Any, Optional
import discord
from discord.ext import commands, tasks

# ---------- File helpers ----------
def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _read_bets() -> List[Dict[str, Any]]:
    base = os.path.dirname(os.path.abspath(__file__))
    bets_path = os.path.join(base, "..", "JSON", "bets.json")
    try:
        with open(os.path.normpath(bets_path), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _read_config() -> Dict[str, Any]:
    base = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base, "..", "config.json")
    cfg = _read_json(os.path.normpath(config_path))
    return cfg if isinstance(cfg, dict) else {}

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

# ---------- Betting.py layout ----------
def _rebuild_bet_embed(bet: Dict[str, Any], bot_user: Optional[discord.User]) -> discord.Embed:
    title = f"📝 Bet: {bet.get('bet_title', 'Unknown')}"
    wager = bet.get("wager") or "-"
    option1 = bet.get("option1") or "Option 1"
    option2 = bet.get("option2") or "Option 2"
    winner = bet.get("winner")

    opt1_user = f"<@{bet['option1_user_id']}>" if bet.get("option1_user_id") else (bet.get("option1_user_name") or "Unclaimed")
    opt2_user = f"<@{bet['option2_user_id']}>" if bet.get("option2_user_id") else (bet.get("option2_user_name") or "Unclaimed")

    embed = discord.Embed(
        title=title,
        color=discord.Color.gold(),
        description=f"**Wager:** {wager}"
    )

    if winner == "option1":
        embed.add_field(name=f"🏆 {option1}", value=f"**Claimed by:** {opt1_user}", inline=False)
        embed.add_field(name=f"~~{option2}~~", value=f"**Claimed by:** {opt2_user}", inline=False)
    elif winner == "option2":
        embed.add_field(name=f"~~{option1}~~", value=f"**Claimed by:** {opt1_user}", inline=False)
        embed.add_field(name=f"🏆 {option2}", value=f"**Claimed by:** {opt2_user}", inline=False)
    else:
        embed.add_field(name=option1, value=f"**Claimed by:** {opt1_user}", inline=False)
        embed.add_field(name=option2, value=f"**Claimed by:** {opt2_user}", inline=False)

    if bot_user:
        avatar = bot_user.avatar.url if bot_user.avatar else bot_user.default_avatar.url
        embed.set_thumbnail(url=avatar)
        embed.set_footer(text=f"{bot_user.display_name} • All bets claimed are final.")
    return embed

# ---------- Admin embed ----------
def _build_admin_embed(bet: Dict[str, Any], msg_url: Optional[str]) -> Optional[discord.Embed]:
    winner = bet.get("winner")
    if winner not in ("option1", "option2"):
        return None
    bet_id = bet.get("bet_id") or "Unknown"
    winner_option = bet.get("option1") if winner == "option1" else bet.get("option2")
    desc = f"## Winner\n{winner_option}"
    if msg_url:
        desc += f"\n-# [Jump to bet]({msg_url})"
    emb = discord.Embed(
        title=f"Bet {bet_id}",
        description=desc,
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    emb.set_footer(text="World Cup 2026 • Winner declared")
    return emb

# ---------- Channel resolver ----------
async def _resolve_admin_channel(bot: commands.Bot, pref: Any, admin_category: str) -> Optional[discord.TextChannel]:
    if isinstance(pref, (int, float, str)) and str(pref).isdigit():
        chan = bot.get_channel(int(pref))
        if isinstance(chan, discord.TextChannel):
            return chan
        try:
            fetched = await bot.fetch_channel(int(pref))
            if isinstance(fetched, discord.TextChannel):
                return fetched
        except Exception:
            pass
    if isinstance(pref, str):
        for guild in bot.guilds:
            chan = discord.utils.get(guild.text_channels, name=pref)
            if isinstance(chan, discord.TextChannel):
                return chan
    for guild in bot.guilds:
        cat = discord.utils.get(guild.categories, name=admin_category)
        if cat:
            chan = discord.utils.get(cat.text_channels, name="bets-winner")
            if isinstance(chan, discord.TextChannel):
                return chan
    return None

# ---------- Cog ----------
class WinnerWatcher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_winner: Dict[str, Optional[str]] = {}
        self._config = _read_config()
        self._admin_category = self._config.get("ADMIN_CATEGORY_NAME", "World Cup Admin")
        self._admin_bet_channel = self._config.get("ADMIN_BET_CHANNEL") or "_admin_bet_channel"
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    @tasks.loop(seconds=30)
    async def poll(self):
        await self.bot.wait_until_ready()
        bets = _read_bets()
        if not isinstance(bets, list):
            print("[WinnerWatcher] bets.json malformed or empty")
            return

        for bet in bets:
            bet_id = str(bet.get("bet_id") or "").strip()
            if not bet_id:
                continue

            winner = bet.get("winner")
            prev_winner = self._last_winner.get(bet_id)
            changed_now = (winner != prev_winner)

            chan_id = int(bet.get("channel_id") or 0)
            msg_id = int(bet.get("message_id") or 0)
            msg_url = None

            if winner in ("option1", "option2") and chan_id and msg_id:
                msg = await _fetch_message(self.bot, chan_id, msg_id)
                if msg is not None:
                    try:
                        await msg.edit(embed=_rebuild_bet_embed(bet, self.bot.user))
                        msg_url = msg.jump_url
                    except Exception as e:
                        print(f"[WinnerWatcher] edit failed for bet {bet_id}: {e}")

            if changed_now and winner in ("option1", "option2"):
                admin_embed = _build_admin_embed(bet, msg_url)
                if admin_embed:
                    admin_chan = await _resolve_admin_channel(self.bot, self._admin_bet_channel, self._admin_category)
                    if admin_chan:
                        try:
                            await admin_chan.send(embed=admin_embed)
                            print(f"[WinnerWatcher] Admin embed posted in #{admin_chan.name} for bet {bet_id}")
                        except Exception as e:
                            print(f"[WinnerWatcher] failed to send admin embed for bet {bet_id}: {e}")
                    else:
                        print("[WinnerWatcher] admin channel not found — check ADMIN_BET_CHANNEL in config.json")

            self._last_winner[bet_id] = winner

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WinnerWatcher(bot))
