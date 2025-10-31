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

# ---------- Claim helpers ----------
def _is_claimed(bet: Dict[str, Any]) -> bool:
    """Consider bet claimed if 'claimed' true, or both side user IDs set,
       or claims list has 2 entries, or both side-claimed flags are true.
    """
    if isinstance(bet.get("claimed"), bool):
        return bet.get("claimed") is True
    o1 = str(bet.get("option1_user_id") or "").strip()
    o2 = str(bet.get("option2_user_id") or "").strip()
    if o1 and o2:
        return True
    claims = bet.get("claims")
    if isinstance(claims, list) and len(claims) >= 2:
        return True
    if bet.get("option1_claimed") and bet.get("option2_claimed"):
        return True
    return False

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

def _mention_or_name(uid: Optional[str], name: Optional[str]) -> str:
    if uid and str(uid).isdigit():
        return f"<@{uid}>"
    return name or "Unknown"

# ---------- Winner-state embed (preserve original structure, add flair) ----------
def _format_result_embed_preserve_layout(bet: Dict[str, Any]) -> discord.Embed:
    bet_id = bet.get("bet_id") or "Unknown"
    title = bet.get("bet_title") or f"📝 Bet: {bet_id}"
    wager = str(bet.get("wager") or "-")

    opt1_text = bet.get("option1") or "Option 1"
    opt2_text = bet.get("option2") or "Option 2"
    winner = bet.get("winner")

    # Claimer names/mentions if present
    o1_uid = str(bet.get("option1_user_id") or "") or None
    o2_uid = str(bet.get("option2_user_id") or "") or None
    o1_name = bet.get("option1_user_name") or bet.get("option1_display_name") or ""
    o2_name = bet.get("option2_user_name") or bet.get("option2_display_name") or ""

    o1_who = _mention_or_name(o1_uid, o1_name) if (o1_uid or o1_name) else "Unclaimed"
    o2_who = _mention_or_name(o2_uid, o2_name) if (o2_uid or o2_name) else "Unclaimed"
    lines = [f"**Wager:** {wager}"]
    lines.append("")  # blank

    if winner == "option1":
        # Winner block first, loser second (preserves clarity)
        lines.append(f"**{opt1_text}**")
        lines.append(f"Claimed by: {o1_who}")
        lines.append("")
        lines.append(f"~~{opt2_text}~~")
        # If loser was claimed, still show the claimer, just minimised
        if o2_who != "Unclaimed":
            lines.append(f"-# Loser • Claimed by: {o2_who}")
        else:
            lines.append(f"-# Loser • Unclaimed")
    elif winner == "option2":
        lines.append(f"**{opt2_text}**")
        lines.append(f"Claimed by: {o2_who}")
        lines.append("")
        lines.append(f"~~{opt1_text}~~")
        if o1_who != "Unclaimed":
            lines.append(f"-# Loser • Claimed by: {o1_who}")
        else:
            lines.append(f"-# Loser • Unclaimed")
    else:
        # Should not be used unless someone accidentally calls for TBD
        lines.append(f"**{opt1_text}**")
        lines.append(f"Claimed by: {o1_who}")
        lines.append("")
        lines.append(f"**{opt2_text}**")
        lines.append(f"Claimed by: {o2_who}")

    desc = "\n".join(lines)

    emb = discord.Embed(
        title=title,
        description=desc,
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )

    # Optional thumbnail carry-over if your Betting.py sets one
    thumb = bet.get("thumbnail")
    if isinstance(thumb, str) and thumb:
        emb.set_thumbnail(url=thumb)

    emb.set_footer(text="World Cup 2026 • All bets claimed are final.")
    return emb

# ---------- Admin embed ----------
def _build_admin_embed(bet: Dict[str, Any], msg_url: Optional[str]) -> Optional[discord.Embed]:
    """Admin alert: 'Bet 12345' with winner and jump link."""
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

async def _resolve_log_channel(bot: commands.Bot, pref: Any, admin_category: str) -> Optional[discord.TextChannel]:
    # ID
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
    # Name
    if isinstance(pref, str) and pref.strip():
        for guild in bot.guilds:
            chan = discord.utils.get(guild.text_channels, name=pref)
            if isinstance(chan, discord.TextChannel):
                return chan
    # Fallback bets-winner in admin category
    for guild in bot.guilds:
        cat = discord.utils.get(guild.categories, name=admin_category)
        if not cat:
            continue
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

    @tasks.loop(seconds=30.0)
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
            # Only edit the original message when a winner is decided AND the bet is claimed
            if winner in ("option1", "option2") and _is_claimed(bet) and chan_id and msg_id:
                msg = await _fetch_message(self.bot, chan_id, msg_id)
                if msg is not None:
                    try:
                        await msg.edit(embed=_format_result_embed_preserve_layout(bet))
                        msg_url = msg.jump_url
                    except Exception as e:
                        print(f"[WinnerWatcher] edit failed for bet {bet_id}: {e}")
                else:
                    print(f"[WinnerWatcher] could not fetch message for bet {bet_id} (chan {chan_id}, msg {msg_id})")
            # If winner not decided, DO NOT edit - keep Betting.py embed intact

            # Post admin embed when winner changes to an option
            if changed_now and winner in ("option1", "option2"):
                embed = _build_admin_embed(bet, msg_url)
                if embed:
                    chan = await _resolve_log_channel(self.bot, self._admin_bet_channel, self._admin_category)
                    if not chan:
                        print(f"[WinnerWatcher] admin channel not found. ADMIN_BET_CHANNEL='{self._admin_bet_channel}'")
                    else:
                        try:
                            await chan.send(embed=embed)
                            print(f"[WinnerWatcher] announced winner for bet {bet_id} in '{chan.name}'")
                        except Exception as e:
                            print(f"[WinnerWatcher] failed to send admin embed for bet {bet_id}: {e}")

            # track last seen
            self._last_winner[bet_id] = winner

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WinnerWatcher(bot))
