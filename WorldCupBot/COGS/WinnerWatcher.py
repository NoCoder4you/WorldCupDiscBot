import os
import json
from typing import List, Dict, Any, Optional, Tuple
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

def _build_admin_embed(bet: Dict[str, Any], msg_url: Optional[str]) -> Optional[discord.Embed]:
    winner = bet.get("winner")
    if winner not in ("option1", "option2"):
        return None

    bet_id = bet.get("bet_id") or "Unknown"
    winner_option = bet.get("option1") if winner == "option1" else bet.get("option2")
    winner_option = winner_option or "Unknown option"

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

async def _resolve_log_channel(bot: commands.Bot, pref: Any, admin_category: str) -> Tuple[Optional[discord.TextChannel], str]:
    # 1) If numeric ID
    if isinstance(pref, (int, float, str)) and str(pref).isdigit():
        chan = bot.get_channel(int(pref))
        if isinstance(chan, discord.TextChannel):
            return chan, "resolved by numeric channel ID"
        # try fetch
        try:
            fetched = await bot.fetch_channel(int(pref))
            if isinstance(fetched, discord.TextChannel):
                return fetched, "resolved by fetched numeric channel ID"
        except Exception:
            pass

    # 2) Name match across guilds
    if isinstance(pref, str) and pref.strip():
        for guild in bot.guilds:
            chan = discord.utils.get(guild.text_channels, name=pref)
            if isinstance(chan, discord.TextChannel):
                return chan, f"resolved by name '{pref}'"
    # 3) Fallback - bets-winner in admin category
    for guild in bot.guilds:
        cat = discord.utils.get(guild.categories, name=admin_category)
        if not cat:
            continue
        chan = discord.utils.get(cat.text_channels, name="bets-winner")
        if isinstance(chan, discord.TextChannel):
            return chan, "resolved fallback bets-winner in admin category"
    return None, "no matching channel found"

# ---------- Cog ----------
class WinnerWatcher(commands.Cog):
    """Updates original bet embeds and posts admin alert on winner declaration."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_winner: Dict[str, Optional[str]] = {}
        self._announced: Dict[str, Optional[str]] = {}
        self._config = _read_config()
        self._admin_category = self._config.get("ADMIN_CATEGORY_NAME", "World Cup Admin")
        # Accept either name or ID under ADMIN_BET_CHANNEL, default to '_admin_bet_channel'
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
            # Update original message if we can
            if chan_id and msg_id:
                msg = await _fetch_message(self.bot, chan_id, msg_id)
                if msg is not None:
                    try:
                        await msg.edit(embed=_format_embed_for_bet_card(bet))
                        msg_url = msg.jump_url
                    except Exception as e:
                        print(f"[WinnerWatcher] edit failed for bet {bet_id}: {e}")
                else:
                    print(f"[WinnerWatcher] could not fetch message for bet {bet_id} (chan {chan_id}, msg {msg_id})")

            # If winner just became option1/option2, announce to admin channel even if no msg/jump_url
            if changed_now and winner in ("option1", "option2"):
                embed = _build_admin_embed(bet, msg_url)
                if embed:
                    chan, why = await _resolve_log_channel(self.bot, self._admin_bet_channel, self._admin_category)
                    if not chan:
                        print(f"[WinnerWatcher] admin channel not found ({why}). ADMIN_BET_CHANNEL='{self._admin_bet_channel}'")
                    else:
                        try:
                            await chan.send(embed=embed)
                            print(f"[WinnerWatcher] announced winner for bet {bet_id} in '{chan.name}' ({why})")
                            self._announced[bet_id] = winner
                        except Exception as e:
                            print(f"[WinnerWatcher] failed to send admin embed for bet {bet_id}: {e}")

            # Track last seen value
            self._last_winner[bet_id] = winner

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WinnerWatcher(bot))
