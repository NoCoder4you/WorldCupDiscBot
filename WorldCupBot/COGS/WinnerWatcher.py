import os
import json
import time
from typing import List, Dict, Any, Optional
import logging
import discord
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

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

def _bet_results_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, "..", "JSON", "bet_results.json"))

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

async def _message_url(bot: commands.Bot, channel_id: int, message_id: int) -> Optional[str]:
    if not channel_id or not message_id:
        return None
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return None
    if getattr(channel, "guild", None):
        return f"https://discord.com/channels/{channel.guild.id}/{channel_id}/{message_id}"
    return None

# ---------- Betting.py layout ----------
def _rebuild_bet_embed(bet: Dict[str, Any], bot_user: Optional[discord.User]) -> discord.Embed:
    title = f"📝 Bet: {bet.get('bet_title', 'Unknown')}"
    wager = bet.get("wager") or "-"
    option1 = bet.get("option1") or "Option 1"
    option2 = bet.get("option2") or "Option 2"
    winner = str(bet.get("winner") or "").strip().lower()

    opt1_user = f"<@{bet['option1_user_id']}>" if bet.get("option1_user_id") else (bet.get("option1_user_name") or "Unclaimed")
    opt2_user = f"<@{bet['option2_user_id']}>" if bet.get("option2_user_id") else (bet.get("option2_user_name") or "Unclaimed")

    embed = discord.Embed(
        title=title,
        description=f"### Wager: {wager}",
        color=discord.Color.gold()
    )

    opt1_name = option1
    opt2_name = option2
    if winner == "option1":
        opt1_name = f"🏆 {option1} 🏆"
        opt2_name = f"~~{option2}~~"
    elif winner == "option2":
        opt1_name = f"~~{option1}~~"
        opt2_name = f"🏆 {option2} 🏆"

    embed.add_field(name=opt1_name, value=f"Claimed by: {opt1_user}", inline=False)
    embed.add_field(name=opt2_name, value=f"Claimed by: {opt2_user}", inline=False)

    if bot_user:
        avatar = bot_user.avatar.url if bot_user.avatar else bot_user.default_avatar.url
        embed.set_thumbnail(url=avatar)
        embed.set_footer(text=f"{bot_user.display_name} • All bets claimed are final.")
    return embed

# ---------- DM embed ----------
def _build_dm_embed(bet: Dict[str, Any], msg_url: Optional[str]) -> Optional[discord.Embed]:
    winner = bet.get("winner")
    if winner not in ("option1", "option2"):
        return None
    bet_id = bet.get("bet_id") or "Unknown"
    bet_title = bet.get("bet_title") or "Bet"
    option1 = bet.get("option1") or "Option 1"
    option2 = bet.get("option2") or "Option 2"
    opt1_user = f"<@{bet['option1_user_id']}>" if bet.get("option1_user_id") else (bet.get("option1_user_name") or "Unclaimed")
    opt2_user = f"<@{bet['option2_user_id']}>" if bet.get("option2_user_id") else (bet.get("option2_user_name") or "Unclaimed")
    emb = discord.Embed(
        title=f"Bet {bet_id}: {bet_title}",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    emb.add_field(name=option1, value=f"Claimed by: {opt1_user}", inline=False)
    emb.add_field(name=option2, value=f"Claimed by: {opt2_user}", inline=False)
    if msg_url:
        emb.add_field(name="Jump to bet", value=f"[Open message]({msg_url})", inline=False)
    emb.set_footer(text="World Cup 2026")
    return emb

def _build_bet_result_embed(bet: Dict[str, Any], msg_url: Optional[str]) -> discord.Embed:
    bet_title = bet.get("bet_title", "Bet Update")

    desc = f"[Open bet message]({msg_url})" if msg_url else "Bet result available."
    embed = discord.Embed(title=f"Bet Update: {bet_title}", description=desc, color=discord.Color.gold())
    embed.set_footer(text="World Cup 2026")
    embed.timestamp = discord.utils.utcnow()
    return embed

def _append_bet_results(bet: Dict[str, Any]):
    winner = str((bet or {}).get("winner") or "").strip().lower()
    if winner not in ("option1", "option2"):
        return
    bet_id = str((bet or {}).get("bet_id") or "").strip()
    if not bet_id:
        return
    opt1_id = str((bet or {}).get("option1_user_id") or "").strip()
    opt2_id = str((bet or {}).get("option2_user_id") or "").strip()
    if not (opt1_id or opt2_id):
        return

    path = _bet_results_path()
    data = _read_json(path) or {}
    if not isinstance(data, dict):
        data = {}
    events = data.get("events")
    if not isinstance(events, list):
        events = []

    existing = {str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id")}
    now = int(time.time())

    bet_title = str((bet or {}).get("bet_title") or f"Bet {bet_id}")
    wager = str((bet or {}).get("wager") or "-")

    def add_event(uid: str, result: str):
        if not uid:
            return
        eid = f"bet:{bet_id}:{uid}"
        if eid in existing:
            return
        outcome = "Status: 🏆 Won 🏆" if result == "win" else "Lost"
        events.append({
            "id": eid,
            "discord_id": uid,
            "result": result,
            "title": "Bet settled",
            "body": f"Bet: {bet_title}\nWager: {wager}\n{outcome}",
            "bet_id": bet_id,
            "bet_title": bet_title,
            "wager": wager,
            "ts": now
        })
        existing.add(eid)

    def purge_existing(uid: str):
        if not uid:
            return
        prefix = f"bet:{bet_id}:{uid}"
        kept = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            if str(ev.get("id") or "") == prefix:
                continue
            kept.append(ev)
        events[:] = kept
        existing.discard(prefix)

    if winner == "option1":
        purge_existing(opt1_id)
        purge_existing(opt2_id)
        add_event(opt1_id, "win")
        add_event(opt2_id, "lose")
    elif winner == "option2":
        purge_existing(opt1_id)
        purge_existing(opt2_id)
        add_event(opt1_id, "lose")
        add_event(opt2_id, "win")

    events.sort(key=lambda x: int((x or {}).get("ts") or 0), reverse=True)
    data["events"] = events[:500]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        return

async def _dm_bet_result(bot: commands.Bot, user_id: str, bet: Dict[str, Any], msg_url: Optional[str]):
    try:
        uid = int(str(user_id))
    except Exception:
        return
    try:
        user = bot.get_user(uid) or await bot.fetch_user(uid)
        if not user:
            return
        await user.send(embed=_build_bet_result_embed(bet, msg_url))
    except Exception:
        return

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
        self._admin_bet_channel = self._config.get("ADMIN_BET_CHANNEL") or "bets-winner"
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    @tasks.loop(seconds=30)
    async def poll(self):
        await self.bot.wait_until_ready()
        bets = _read_bets()
        if not isinstance(bets, list):
            log.warning("bets.json malformed or empty")
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
                        log.warning("Bet message edit failed (bet_id=%s error=%s)", bet_id, e)
                elif not msg_url:
                    msg_url = await _message_url(self.bot, chan_id, msg_id)

            if changed_now and winner in ("option1", "option2"):
                log.info(
                    "Bet settled (bet_id=%s winner=%s option1_user_id=%s option2_user_id=%s)",
                    bet_id,
                    winner,
                    bet.get("option1_user_id"),
                    bet.get("option2_user_id"),
                )
                admin_embed = _build_dm_embed(bet, msg_url)
                if admin_embed:
                    admin_chan = await _resolve_admin_channel(self.bot, self._admin_bet_channel, self._admin_category)
                    if admin_chan:
                        try:
                            await admin_chan.send(embed=admin_embed)
                            log.info("Bet winner embed posted (bet_id=%s channel=%s)", bet_id, admin_chan.name)
                        except Exception as e:
                            log.warning("Bet winner embed send failed (bet_id=%s error=%s)", bet_id, e)
                    else:
                        log.warning("Admin bet channel not found (bet_id=%s)", bet_id)

                opt1_id = str(bet.get("option1_user_id") or "").strip()
                opt2_id = str(bet.get("option2_user_id") or "").strip()
                if winner == "option1":
                    await _dm_bet_result(self.bot, opt1_id, bet, msg_url)
                    await _dm_bet_result(self.bot, opt2_id, bet, msg_url)
                elif winner == "option2":
                    await _dm_bet_result(self.bot, opt1_id, bet, msg_url)
                    await _dm_bet_result(self.bot, opt2_id, bet, msg_url)

                _append_bet_results(bet)

                _append_bet_results(bet)

            self._last_winner[bet_id] = winner

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WinnerWatcher(bot))
