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
    # Prefer /JSON/config.json; fall back to root config.json
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
    """Build an embed for the original bet message when the winner changes."""
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

def _winner_side_to_user_fields(bet: Dict[str, Any]) -> Dict[str, Any]:
    side = bet.get("winner")
    opt1 = bet.get("option1") or "Option 1"
    opt2 = bet.get("option2") or "Option 2"
    o1_uid = str(bet.get("option1_user_id") or "") or None
    o2_uid = str(bet.get("option2_user_id") or "") or None
    o1_name = bet.get("option1_user_name") or (o1_uid or "")
    o2_name = bet.get("option2_user_name") or (o2_uid or "")

    if side == "option1":
        return {
            "winner_side": "option1",
            "winner_option_text": opt1,
            "winner_user_id": o1_uid,
            "winner_user_name": o1_name,
            "loser_option_text": opt2,
            "loser_user_id": o2_uid,
            "loser_user_name": o2_name,
        }
    if side == "option2":
        return {
            "winner_side": "option2",
            "winner_option_text": opt2,
            "winner_user_id": o2_uid,
            "winner_user_name": o2_name,
            "loser_option_text": opt1,
            "loser_user_id": o1_uid,
            "loser_user_name": o1_name,
        }
    return {
        "winner_side": None,
        "winner_option_text": None,
        "winner_user_id": None,
        "winner_user_name": None,
        "loser_option_text": None,
        "loser_user_id": None,
        "loser_user_name": None,
    }

def _mention_or_name(uid: Optional[str], fallback: str) -> str:
    if uid and str(uid).isdigit():
        return f"<@{uid}>"
    return fallback or (uid or "")

def _build_admin_embed(bet: Dict[str, Any], msg_url: Optional[str]) -> Optional[discord.Embed]:
    fields = _winner_side_to_user_fields(bet)
    if not fields["winner_side"]:
        return None  # only announce when set to option1/option2

    title = bet.get("bet_title") or "Bet"
    wager = bet.get("wager") or "-"

    winner_display = _mention_or_name(fields["winner_user_id"], fields["winner_user_name"])
    loser_display  = _mention_or_name(fields["loser_user_id"], fields["loser_user_name"])

    emb = discord.Embed(
        title=f"🏆 Bet Settled — {title}",
        description=(
            f"**Winner:** {winner_display}\n"
            f"**Winning pick:** **{fields['winner_option_text']}**\n"
            f"**Loser:** {loser_display if loser_display else '—'}"
        ),
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),  # when they won it
    )
    emb.add_field(name="What they won", value=str(wager), inline=True)
    if msg_url:
        emb.add_field(name="Bet message", value=f"[Jump to message]({msg_url})", inline=True)
    emb.set_footer(text="World Cup 2026 • Winner declared")
    return emb

# ---------- Cog ----------
class WinnerWatcher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_winner: Dict[str, Optional[str]] = {}
        self._announced: Dict[str, Optional[str]] = {}  # bet_id -> winner announced
        self._config = _read_config()
        self._admin_category = self._config.get("ADMIN_CATEGORY_NAME", "World Cup Admin")
        # Explicit configurable channel id or name. If missing, we will try "_admin_bet_channel".
        self._admin_bet_channel = self._config.get("ADMIN_BET_CHANNEL") or "_admin_bet_channel"
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    # ------------- Log/resolve channel -------------
    async def _resolve_log_channel(self) -> Optional[discord.TextChannel]:
        """Find the channel where winner updates should be posted."""
        # 1) If _admin_bet_channel is an ID
        if isinstance(self._admin_bet_channel, (int, float, str)) and str(self._admin_bet_channel).isdigit():
            chan = self.bot.get_channel(int(self._admin_bet_channel))
            if isinstance(chan, discord.TextChannel):
                return chan

        # 2) If _admin_bet_channel is a name
        if isinstance(self._admin_bet_channel, str):
            for guild in self.bot.guilds:
                chan = discord.utils.get(guild.text_channels, name=str(self._admin_bet_channel))
                if isinstance(chan, discord.TextChannel):
                    return chan

        # 3) Fallback - bets-winner inside admin category
        for guild in self.bot.guilds:
            cat = discord.utils.get(guild.categories, name=self._admin_category)
            if not cat:
                continue
            chan = discord.utils.get(cat.text_channels, name="bets-winner")
            if isinstance(chan, discord.TextChannel):
                return chan

        return None

    async def _log_update_text(self, content: str):
        """Console + plain text in admin channel (legacy)."""
        print(f"[WinnerWatcher] {content}")
        try:
            chan = await self._resolve_log_channel()
            if chan:
                await chan.send(content)
        except Exception:
            pass

    async def _post_admin_embed(self, embed: discord.Embed):
        try:
            chan = await self._resolve_log_channel()
            if chan and embed:
                await chan.send(embed=embed)
        except Exception:
            pass

    # ------------- Poll loop -------------
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

            # Update the original bet card if we can
            if chan_id and msg_id:
                msg = await _fetch_message(self.bot, chan_id, msg_id)
                if msg is not None:
                    try:
                        await msg.edit(embed=_format_embed_for_bet_card(bet))
                    except Exception:
                        pass
                    # If winner turned into option1/option2 now, post admin embed once
                    if winner in ("option1", "option2") and self._announced.get(bet_id) != winner:
                        admin_embed = _build_admin_embed(bet, msg.jump_url)
                        if admin_embed is not None:
                            await self._post_admin_embed(admin_embed)
                        self._announced[bet_id] = winner

                    # Always log text when the winner value changes (including cleared)
                    if prev_winner != winner:
                        if winner == "option1":
                            human = f'Option 1 - "{bet.get("option1") or "Option 1"}"'
                        elif winner == "option2":
                            human = f'Option 2 - "{bet.get("option2") or "Option 2"}"'
                        else:
                            human = "TBD (cleared)"
                        await self._log_update_text(f'Bet {bet_id} winner set to {human} | Jump: {msg.jump_url}')

            # Remember state to detect changes
            self._last_winner[bet_id] = winner

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WinnerWatcher(bot))
