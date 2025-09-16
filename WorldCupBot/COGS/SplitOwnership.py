import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

JSON_DIR = Path("/home/pi/WorldCupDiscBot/WorldCupBot/JSON")
TEAMS_LIST_FILE = JSON_DIR / "teams.json"
ISO_FILE = JSON_DIR / "team_iso.json"
PLAYERS_FILE = JSON_DIR / "players.json"
REQUESTS_FILE = JSON_DIR / "split_requests.json"
SPLIT_REQUESTS_LOG_FILE = JSON_DIR / "split_requests_log.json"

def load_json(path):
    if not path.exists():
        return {} if str(path).endswith('.json') else []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def append_log(log_item):
    """Append an entry to split_requests_log.json as a list."""
    try:
        if not SPLIT_REQUESTS_LOG_FILE.exists():
            with open(SPLIT_REQUESTS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        with open(SPLIT_REQUESTS_LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
        logs.append(log_item)
        with open(SPLIT_REQUESTS_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4)
    except Exception as e:
        print(f"Failed to log split request: {e}")

def get_flag_url(team_name):
    iso_map = load_json(ISO_FILE)
    iso = iso_map.get(team_name, None)
    if not iso:
        return None
    return f"https://flagcdn.com/w320/{iso.lower()}.png"

def load_teams():
    return load_json(TEAMS_LIST_FILE)

def build_team_case_map(teams):
    return {t.lower(): t for t in teams}

def find_team_main_owner(players, team):
    for uid, pdata in players.items():
        for t in pdata.get("teams", []):
            if t["team"] == team and t["ownership"]["main_owner"] == int(uid):
                return int(uid), t
    return None, None

def user_has_any_team(players, user_id):
    return any(players.get(str(user_id), {}).get("teams", []))

async def update_public_embed(bot, guild, team, players):
    main_owner_id, main_team_obj = find_team_main_owner(players, team)
    if not main_team_obj or "public_message_id" not in main_team_obj:
        return

    split_owners = main_team_obj["ownership"].get("split_with", [])
    split_mentions = [f"<@{oid}>" for oid in split_owners] if split_owners else []

    public_channel = None
    for category in guild.categories:
        if category.name.lower() == "world cup":
            for channel in category.text_channels:
                if channel.name.lower() == "players-and-teams":
                    public_channel = channel
                    break
            if public_channel:
                break
    if not public_channel:
        return

    msg_id = main_team_obj["public_message_id"]
    try:
        msg = await public_channel.fetch_message(msg_id)
        main_owner_user = bot.get_user(main_owner_id) or await bot.fetch_user(main_owner_id)
        flag = get_flag_url(team)
        embed = discord.Embed(
            title=team,
            colour=discord.Colour.blue()
        )
        embed.add_field(name="Main User", value=main_owner_user.mention if main_owner_user else str(main_owner_id), inline=False)
        embed.add_field(name="Split With", value=", ".join(split_mentions) if split_mentions else "N/A", inline=False)
        if main_owner_user and main_owner_user.display_avatar:
            embed.set_thumbnail(url=main_owner_user.display_avatar.url)
        if flag:
            embed.set_image(url=flag)
        await msg.edit(embed=embed)
    except Exception as e:
        print(f"Failed to update public embed for {team}: {e}")
        
class ConfirmChoiceView(discord.ui.View):
    def __init__(self, main_owner, team, requester, callback, request_id, accepted, bot):
        super().__init__(timeout=300)
        self.main_owner = main_owner
        self.team = team
        self.requester = requester
        self.callback = callback
        self.request_id = request_id
        self.accepted = accepted
        self.bot = bot

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.main_owner:
            embed = discord.Embed(
                title="Not allowed",
                description="Only the main owner can confirm.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · Confirmation required")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    
        await self.callback(self.accepted, self.team, self.requester, self.request_id, declined=not self.accepted)
        flag_url = get_flag_url(self.team)
        
        if self.accepted:
            players = load_json(PLAYERS_FILE)
            main_owner_id, _ = find_team_main_owner(players, self.team)
            split_mentions = []
            for uid, pdata in players.items():
                for t in pdata.get("teams", []):
                    if t["team"] == self.team:
                        split_mentions += [f"<@{oid}>" for oid in t["ownership"].get("split_with", []) if oid != main_owner_id]
            split_mentions = list(set(split_mentions))
            msg = (
                f"✅ The split for **{self.team}** has been **accepted**.\n"
                f"Main owner: <@{main_owner_id}>\n"
                f"Split with: {', '.join(split_mentions) if split_mentions else 'N/A'}\n"
                f"Any winnings will be divided equally between all owners."
            )
            embed = discord.Embed(
                title=f"Choice Confirmed - {self.team}",
                description=msg,
                colour=discord.Colour.green()
            )
        else:
            embed = discord.Embed(
                title=f"Choice Confirmed - {self.team}",
                description=f"❌ The split request for **{self.team}** was **declined** by the main owner.",
                colour=discord.Colour.red()
            )
        
        embed.set_footer(text="World Cup 2026 · Split request complete")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        if flag_url:
            embed.set_image(url=flag_url)
    
        # Update public embeds if split was accepted
        if self.accepted:
            players = load_json(PLAYERS_FILE)
            for guild in self.bot.guilds:
                await update_public_embed(self.bot, guild, self.team, players)
                break
    
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()




    @discord.ui.button(label="Go Back", style=discord.ButtonStyle.blurple)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.main_owner:
            embed = discord.Embed(
                title="Not allowed",
                description="Only the main owner can use this.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · Permission required")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        flag_url = get_flag_url(team)
        embed = discord.Embed(
            title=f"Split Request - {team}",
            description=(
                f"{interaction.user.mention} has requested to split ownership of **{team}** with you.\n"
                f"*You have 48 hours to accept or decline this request before it expires.*\n"
                "**This action cannot be undone and your decision is final.**\n\n"
                "**Any winnings will be divided equally between all owners of the team.**"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="World Cup 2026 · Awaiting response")
        if flag_url:
            embed.set_image(url=flag_url)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.edit_message(embed=embed, view=SplitRequestView(self.main_owner, self.team, self.requester, self.callback, self.request_id, bot=self.bot))
        self.stop()

class SplitRequestView(discord.ui.View):
    def __init__(self, main_owner, team, requester, callback, request_id, bot):
        super().__init__(timeout=48*3600)
        self.main_owner = main_owner
        self.team = team
        self.requester = requester
        self.callback = callback
        self.request_id = request_id
        self.bot = bot

    async def on_timeout(self):
        await self.callback(None, self.team, self.requester, self.request_id, timeout=True)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.main_owner:
            embed = discord.Embed(
                title="Not allowed",
                description="Only the main owner can respond to this request.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · Action required")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = discord.Embed(
            title="Split Request",
            description=(
                f"Are you sure you want to **accept** this split?\n"
                "**This action cannot be undone and your decision is final.**\n\n"
                "**Any winnings will be divided equally between all owners of the team.**"
            ),
            colour=discord.Colour.green()
        )
        embed.set_footer(text="World Cup 2026 · Confirm your decision")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.edit_message(
            embed=embed,
            view=ConfirmChoiceView(self.main_owner, self.team, self.requester, self.callback, self.request_id, accepted=True, bot=self.bot)
        )
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.main_owner:
            embed = discord.Embed(
                title="Not allowed",
                description="Only the main owner can respond to this request.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · Action required")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = discord.Embed(
            title="Split Request",
            description=(
                f"Are you sure you want to **decline** this split?\n"
                "**This action cannot be undone and your decision is final.**\n\n"
                "**Any winnings will be divided equally between all owners of the team.**"
            ),
            colour=discord.Colour.orange()
        )
        embed.set_footer(text="World Cup 2026 · Confirm your decision")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.edit_message(
            embed=embed,
            view=ConfirmChoiceView(self.main_owner, self.team, self.requester, self.callback, self.request_id, accepted=False, bot=self.bot)
        )
        self.stop()

class SplitOwnership(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_requests.start()

    @tasks.loop(minutes=15)
    async def cleanup_requests(self):
        requests = load_json(REQUESTS_FILE)
        now = datetime.now(timezone.utc).timestamp()
        updated = False
        for req_id in list(requests.keys()):
            req = requests[req_id]
            if req["expires_at"] < now:
                # Log expiration
                append_log({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "expired",
                    "request_id": req_id,
                    "team": req["team"],
                    "main_owner_id": req["main_owner_id"],
                    "requester_id": req["requester_id"],
                    "expires_at": req["expires_at"]
                })
                main_owner = self.bot.get_user(req["main_owner_id"])
                requester = self.bot.get_user(int(req["requester_id"]))
                embed = discord.Embed(
                    title=f"Split Request Expired - {req['team']}",
                    description=f"Your split request for **{req['team']}** expired after 48 hours without a response from the main owner.",
                    colour=discord.Colour.orange()
                )
                embed.set_footer(text="World Cup 2026 · Split request expired")
                flag_url = get_flag_url(req["team"])
                if flag_url:
                    embed.set_image(url=flag_url)
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
                if main_owner:
                    try:
                        await main_owner.send(embed=embed)
                    except Exception:
                        pass
                if requester:
                    try:
                        await requester.send(embed=embed)
                    except Exception:
                        pass
                del requests[req_id]
                updated = True
        if updated:
            save_json(REQUESTS_FILE, requests)

    async def split_callback(self, accepted, team, requester, request_id, declined=False, timeout=False):
        requests = load_json(REQUESTS_FILE)
        req = requests.get(request_id, None)
        if not req:
            return

        players = load_json(PLAYERS_FILE)
        main_owner_id, main_team_obj = find_team_main_owner(players, team)
        uid = str(requester.id)

        # Log the result
        status = (
            "timeout" if timeout else
            "declined" if declined else
            "accepted" if accepted else
            "unknown"
        )
        log_item = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "request_id": request_id,
            "team": team,
            "main_owner_id": req.get("main_owner_id"),
            "requester_id": req.get("requester_id"),
            "resolved_by": str(main_owner_id) if not timeout else None,
            "expires_at": req.get("expires_at")
        }
        append_log(log_item)

        del requests[request_id]
        save_json(REQUESTS_FILE, requests)

        if timeout:
            return

        if declined:
            embed = discord.Embed(
                title=f"Split Declined - {team}",
                description=(
                    f"Your split request for **{team}** was declined by the main owner.\n"
                    "You may request to split ownership again or try again with a different team owner"
                ),
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · Split request declined")
            flag_url = get_flag_url(team)
            if flag_url:
                embed.set_image(url=flag_url)
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            try:
                await requester.send(embed=embed)
            except Exception:
                pass
            return

        if accepted and main_team_obj:
            if requester.id not in main_team_obj["ownership"]["split_with"]:
                main_team_obj["ownership"]["split_with"].append(requester.id)

            requester_teams = players.setdefault(uid, {}).setdefault("teams", [])
            found = False
            for t in requester_teams:
                if t["team"] == team:
                    found = True
                    break
            if not found:
                requester_teams.append({
                    "team": team,
                    "ownership": {
                        "main_owner": main_owner_id,
                        "split_with": []
                    },
                    "public_message_id": main_team_obj.get("public_message_id")
                })
            save_json(PLAYERS_FILE, players)

            for guild in self.bot.guilds:
                await update_public_embed(self.bot, guild, team, players)

            embed = discord.Embed(
                title=f"Split Accepted - {team}",
                description=(
                    f"You are now a co-owner of **{team}** with <@{main_owner_id}> as the main owner.\n"
                    "Any winnings will be divided equally between all owners."
                ),
                colour=discord.Colour.green()
            )
            embed.set_footer(text="World Cup 2026 · Team ownership updated")
            flag_url = get_flag_url(team)
            if flag_url:
                embed.set_image(url=flag_url)
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            try:
                await requester.send(embed=embed)
            except Exception:
                pass


    @app_commands.command(name="split", description="Request to split ownership of a team")
    @app_commands.describe(team="The team to split ownership of")
    async def split(self, interaction: discord.Interaction, team: str):
        
        await interaction.response.defer(ephemeral=True)
        
        players = load_json(PLAYERS_FILE)
        teams = load_teams()
        team_case_map = build_team_case_map(teams)
        team_input = team.strip().lower()
        requester_id = str(interaction.user.id)

        if not user_has_any_team(players, requester_id):
            embed = discord.Embed(
                title="You must own a team!",
                description="You cannot request to split ownership unless you already own at least one team.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · Eligibility check")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if team_input not in team_case_map:
            embed = discord.Embed(
                title="Invalid Team",
                description="That team does not exist. Please check your spelling.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · Invalid team")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        team = team_case_map[team_input]
        main_owner_id, main_team_obj = find_team_main_owner(players, team)
        if not main_team_obj:
            embed = discord.Embed(
                title="No Owner",
                description="No owner is assigned to this team.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · No main owner")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if int(requester_id) == main_owner_id or int(requester_id) in main_team_obj["ownership"]["split_with"]:
            embed = discord.Embed(
                title="Already Co-Owner",
                description="You are already an owner of this team.",
                colour=discord.Colour.orange()
            )
            embed.set_footer(text="World Cup 2026 · Ownership unchanged")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        requests = load_json(REQUESTS_FILE)
        for req in requests.values():
            if (req["requester_id"] == requester_id and req["team"] == team):
                embed = discord.Embed(
                    title="Already Requested",
                    description="You already have a pending split request for this team.",
                    colour=discord.Colour.orange()
                )
                embed.set_footer(text="World Cup 2026 · Request pending")
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        main_owner = await self.bot.fetch_user(main_owner_id)
        request_id = f"{requester_id}_{team}_{int(datetime.now().timestamp())}"
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=48)).timestamp()

        requests[request_id] = {
            "requester_id": requester_id,
            "main_owner_id": main_owner_id,
            "team": team,
            "expires_at": expires_at
        }
        save_json(REQUESTS_FILE, requests)

        flag_url = get_flag_url(team)
        embed = discord.Embed(
            title=f"Split Request - {team}",
            description=(
                f"{interaction.user.mention} has requested to split ownership of **{team}** with you.\n"
                f"*You have 48 hours to accept or decline this request before it expires.*\n"
                "**This action cannot be undone and your decision is final.**\n\n"
                "**Any winnings will be divided equally between all owners of the team.**"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="World Cup 2026 · Awaiting response")
        if flag_url:
            embed.set_image(url=flag_url)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)


        view = SplitRequestView(main_owner, team, interaction.user, self.split_callback, request_id, bot=self.bot)
        try:
            await main_owner.send(embed=embed, view=view)
        except discord.Forbidden:
            embed = discord.Embed(
                title="DM Failed",
                description="Could not DM the main owner. \nThey may have DMs disabled.",
                colour=discord.Colour.red()
            )
            embed.set_footer(text="World Cup 2026 · DM failure")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            del requests[request_id]
            save_json(REQUESTS_FILE, requests)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="Request Sent",
            description=f"Request sent to the main owner of **{team}**. \nYou will be notified once they respond.",
            colour=discord.Colour.green()
        )
        embed.set_footer(text="World Cup 2026 · Split request sent")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SplitOwnership(bot))
