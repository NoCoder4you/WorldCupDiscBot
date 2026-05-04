import asyncio
import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import discord
from discord.ext import commands

MAX_AUDIT_LOG_ENTRIES = 10000
MESSAGE_CONTENT_LIMIT = 500
AUDIT_CHANNEL_NAME = "bot-audit-log"


class AuditLogCog(commands.Cog):
    """Centralized JSON-based audit logger for Discord + app-specific events."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._write_lock = asyncio.Lock()
        self._logger = logging.getLogger(__name__)
        self._channel_update_pending: dict[int, dict[str, Any]] = {}
        self._channel_update_tasks: dict[int, asyncio.Task] = {}
        base_dir = Path(__file__).resolve().parent.parent
        self._audit_file = base_dir / "JSON" / "audit_log.json"
        self._backup_file = base_dir / "JSON" / "audit_log.backup.json"

    async def cog_load(self) -> None:
        await self._ensure_store()
        await self.log_system_event("cog_loaded", details={"cog": self.__class__.__name__})

    async def cog_unload(self) -> None:
        await self.log_system_event("cog_unloaded", details={"cog": self.__class__.__name__})

    async def _ensure_store(self) -> None:
        self._audit_file.parent.mkdir(parents=True, exist_ok=True)
        if not self._audit_file.exists():
            await self._write_entries([])

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _safe_content(content: Optional[str]) -> str:
        if not content:
            return ""
        return content[:MESSAGE_CONTENT_LIMIT]

    @staticmethod
    def _member_payload(member: Any) -> dict[str, str]:
        if member is None:
            return {"id": "unknown", "name": "Unknown", "display_name": "Unknown"}
        member_id = getattr(member, "id", "unknown")
        member_name = getattr(member, "name", str(member))
        display_name = getattr(member, "display_name", member_name)
        return {
            "id": str(member_id),
            "name": str(member_name),
            "display_name": str(display_name),
        }


    @staticmethod
    def _format_reason(reason: Any) -> str:
        """Return a user-friendly reason for audit embed descriptions."""
        if isinstance(reason, str):
            cleaned_reason = reason.strip()
            if cleaned_reason:
                return cleaned_reason[:500]

    async def _read_entries(self) -> list[dict[str, Any]]:
        try:
            raw = self._audit_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        return []

    async def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        payload = entries[-MAX_AUDIT_LOG_ENTRIES:]
        self._audit_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    async def _backup_entries(self, entries: list[dict[str, Any]]) -> None:
        try:
            self._backup_file.write_text(
                json.dumps(entries, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            await self.log_system_event("json_backup_created")
        except OSError:
            await self.log_system_event("json_write_failed", details={"file": str(self._backup_file)})

    async def log_action(
        self,
        action: str,
        category: str,
        actor: Optional[Any],
        target: Optional[Any],
        guild: Optional[discord.Guild],
        result: str = "success",
        reason: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Reusable logger helper other cogs should call for app-level events."""
        details = deepcopy(details or {})

        # Privacy: never store token-like values or full webhook URLs.
        for key, value in list(details.items()):
            if isinstance(value, str) and "token" in key.lower():
                details[key] = "[REDACTED]"
            if isinstance(value, str) and value.startswith("https://discord.com/api/webhooks/"):
                details[key] = "[WEBHOOK_REDACTED]"

        entry = {
            "id": str(uuid4()),
            "timestamp": self._utc_now_iso(),
            "guild_id": str(guild.id) if guild else "unknown",
            "action": action,
            "category": category,
            "actor": self._member_payload(actor),
            "target": self._member_payload(target),
            "result": result,
            "reason": reason,
            "details": details,
        }

        async with self._write_lock:
            try:
                entries = await self._read_entries()
                entries.append(entry)
                await self._write_entries(entries)
            except OSError:
                self._logger.exception("Failed to write audit log entry")
                await self.log_system_event("json_write_failed", details={"file": str(self._audit_file)})
                return

        # Post a concise copy to Discord for server-local visibility.
        await self._post_to_audit_channel(guild, entry)



    @staticmethod
    def _flatten_command_options(options: list[dict[str, Any]] | None, prefix: str = "") -> list[str]:
        """Flatten nested slash-command options into key=value strings for readable audit embeds."""
        if not isinstance(options, list):
            return []

        flattened: list[str] = []
        for option in options:
            if not isinstance(option, dict):
                continue
            option_name = str(option.get("name", "")).strip()
            option_path = f"{prefix}.{option_name}" if prefix and option_name else (option_name or prefix)
            if "value" in option:
                value = option.get("value")
                flattened.append(f"{option_path}={value!r}")
            nested_options = option.get("options")
            if isinstance(nested_options, list) and nested_options:
                flattened.extend(AuditLogCog._flatten_command_options(nested_options, option_path))
        return flattened

    async def _post_to_audit_channel(self, guild: Optional[discord.Guild], entry: dict[str, Any]) -> None:
        """Post a concise summary to #bot-audit-log when the channel exists."""
        if guild is None:
            return

        channel = discord.utils.get(guild.text_channels, name=AUDIT_CHANNEL_NAME)
        if channel is None:
            return

        me = guild.me
        if me is None:
            return

        perms = channel.permissions_for(me)
        if not perms.send_messages:
            await self.log_system_event("webhook_failed", details={"reason": "missing_send_messages", "channel": AUDIT_CHANNEL_NAME})
            return

        try:
            actor_name = entry["actor"].get("display_name", "Unknown")
            target_name = entry["target"].get("display_name", "Unknown")

            # Use embeds for readability in the bot-audit-log channel.
            embed = discord.Embed(
                title=f"Audit: {entry['action']}",
                description=self._format_reason(entry.get("reason")),
                color=discord.Color.blurple(),
                timestamp=datetime.now(timezone.utc),
            )
            # Keep header minimal: do not show category/result/guild-id fields.
            # Use a clearer label than "Actor" for audit readability.
            embed.add_field(name="Performed By", value=f"{actor_name} (`{entry['actor'].get('id', 'unknown')}`)", inline=False)
            embed.add_field(name="Target", value=f"{target_name} (`{entry['target'].get('id', 'unknown')}`)", inline=False)

            # Channel appears in its own field, and channel mentions are clickable in Discord.
            details = entry.get("details", {})
            channel_id = str(details.get("channel_id", "")).strip()
            if channel_id.isdigit():
                embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)

            invite_url = str(details.get("invite_url", "")).strip()
            if invite_url:
                embed.add_field(name="Invite Link", value=invite_url, inline=False)

            inviter_name = str(details.get("inviter_name", "")).strip()
            inviter_id = str(details.get("inviter_id", "")).strip()
            if inviter_name or inviter_id:
                embed.add_field(
                    name="Invite Created By",
                    value=f"{inviter_name or 'Unknown'} (`{inviter_id or 'unknown'}`)",
                    inline=False,
                )

            category_name = str(details.get("category_name", "")).strip()
            category_id = str(details.get("category_id", "")).strip()
            if category_name or category_id:
                category_value = f"<#{category_id}>" if category_id.isdigit() else (category_name or "No Category")
                embed.add_field(name="Category", value=category_value, inline=True)

            # Message-specific rendering:
            # - message_edit: show both before + after content
            # - message_delete: show deleted message content
            if entry.get("action") == "message_edit":
                before_text = details.get("before")
                after_text = details.get("after")
                if isinstance(before_text, str) and before_text:
                    embed.add_field(name="Before", value=before_text[:1000], inline=False)
                if isinstance(after_text, str) and after_text:
                    embed.add_field(name="After", value=after_text[:1000], inline=False)
            elif entry.get("action") == "message_delete":
                detail_content = details.get("content")
                if isinstance(detail_content, str) and detail_content:
                    embed.add_field(name="Deleted Content", value=detail_content[:1000], inline=False)
            elif entry.get("action") in {"role_added", "role_removed", "role_created", "role_deleted"}:
                # Show which role changed and mention it directly for role/member events.
                role_name = str(details.get("role_name", "unknown"))
                role_id = str(details.get("role_id", "unknown"))
                role_mention = f"<@&{role_id}>" if role_id.isdigit() else role_name
                embed.add_field(name="Role", value=f"{role_mention} (`{role_id}`)", inline=False)
            elif entry.get("action") == "role_updated":
                # Show the specific rename delta so these entries are meaningful at a glance.
                role_id = str(details.get("role_id", "unknown"))
                role_mention = f"<@&{role_id}>" if role_id.isdigit() else "Unknown role"
                before_name = str(details.get("before_name", ""))
                after_name = str(details.get("after_name", ""))
                embed.add_field(name="Role", value=f"{role_mention} (`{role_id}`)", inline=False)
                if before_name or after_name:
                    embed.add_field(
                        name="Name Change",
                        value=f"{before_name or 'unknown'} → {after_name or 'unknown'}",
                        inline=False,
                    )
            elif entry.get("action") == "slash_command_used":
                command_path = str(details.get("command_path", "")).strip()
                if command_path:
                    embed.add_field(name="Command", value=f"`/{command_path}`", inline=False)
                flattened_arguments = self._flatten_command_options(details.get("arguments"))
                if flattened_arguments:
                    embed.add_field(
                        name="Arguments",
                        value="\n".join(f"• `{item[:180]}`" for item in flattened_arguments[:12]),
                        inline=False,
                    )
                else:
                    embed.add_field(name="Arguments", value="No arguments provided.", inline=False)
            elif entry.get("action") == "channel_updated":
                before_name = str(details.get("before_name", "")).strip()
                after_name = str(details.get("after_name", "")).strip()
                # Only show a name-change field when the channel name actually changed.
                if before_name != after_name and (before_name or after_name):
                    embed.add_field(
                        name="Name Change",
                        value=f"{before_name or 'unknown'} → {after_name or 'unknown'}",
                        inline=False,
                    )
                created = int(details.get("permission_overwrite_created", 0) or 0)
                deleted = int(details.get("permission_overwrite_deleted", 0) or 0)
                updated = int(details.get("permission_overwrite_updated", 0) or 0)
                if created or deleted or updated:
                    embed.add_field(
                        name="Permission Overwrites",
                        value=f"➕ Added: `{created}`\n➖ Removed: `{deleted}`\n🔁 Updated: `{updated}`",
                        inline=False,
                    )
                added_targets = details.get("permission_overwrite_added_targets", [])
                if isinstance(added_targets, list) and added_targets:
                    embed.add_field(name="Added For", value="\n".join(str(item) for item in added_targets[:6]), inline=False)
                removed_targets = details.get("permission_overwrite_removed_targets", [])
                if isinstance(removed_targets, list) and removed_targets:
                    embed.add_field(name="Removed From", value="\n".join(str(item) for item in removed_targets[:6]), inline=False)
                changed_permissions = details.get("permission_overwrite_changed_permissions", [])
                if isinstance(changed_permissions, list) and changed_permissions:
                    embed.add_field(
                        name="Permissions Changed",
                        value="\n".join(str(item) for item in changed_permissions[:6]),
                        inline=False,
                    )

            await channel.send(embed=embed)
        except discord.Forbidden:
            await self.log_system_event("webhook_failed", details={"reason": "forbidden", "channel": AUDIT_CHANNEL_NAME})
        except discord.HTTPException as exc:
            # Rate-limit (429) and other API delivery issues are logged as system events.
            if getattr(exc, "status", None) == 429:
                await self.log_system_event("discord_rate_limit_warning", details={"channel": AUDIT_CHANNEL_NAME})
            await self.log_system_event("api_error", details={"error": str(exc), "channel": AUDIT_CHANNEL_NAME})

    async def _try_get_audit_entry(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
        seconds: int = 20,
    ) -> Optional[discord.AuditLogEntry]:
        perms = guild.me.guild_permissions if guild.me else None
        if not perms or not perms.view_audit_log:
            return None
        after_ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                if entry.created_at < after_ts:
                    continue
                if entry.target and getattr(entry.target, "id", None) == target_id:
                    return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _try_get_channel_update_entry(
        self,
        guild: discord.Guild,
        channel_id: int,
        seconds: int = 20,
    ) -> Optional[discord.AuditLogEntry]:
        """Best-effort resolver for channel update actor, including overwrite updates."""
        perms = guild.me.guild_permissions if guild.me else None
        if not perms or not perms.view_audit_log:
            return None
        after_ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        try:
            async for entry in guild.audit_logs(limit=12, action=discord.AuditLogAction.channel_update):
                if entry.created_at < after_ts:
                    continue
                # For rename/move updates, target is often the channel itself.
                if entry.target and getattr(entry.target, "id", None) == channel_id:
                    return entry
                # For overwrite-specific updates, Discord often sets `extra.channel`.
                extra_channel = getattr(getattr(entry, "extra", None), "channel", None)
                if extra_channel and getattr(extra_channel, "id", None) == channel_id:
                    return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _try_get_invite_delete_entry(
        self,
        guild: discord.Guild,
        invite_code: str,
        seconds: int = 20,
    ) -> Optional[discord.AuditLogEntry]:
        """Best-effort resolver for invite_delete actor by matching the invite code."""
        perms = guild.me.guild_permissions if guild.me else None
        if not perms or not perms.view_audit_log:
            return None

        after_ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        try:
            async for entry in guild.audit_logs(limit=8, action=discord.AuditLogAction.invite_delete):
                if entry.created_at < after_ts:
                    continue
                target_code = getattr(entry.target, "code", None)
                if str(target_code or "").strip() == invite_code:
                    return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    @staticmethod
    def _channel_parent_payload(channel: discord.abc.GuildChannel) -> dict[str, str]:
        """Build a consistent category payload for channel audit events."""
        category = getattr(channel, "category", None)
        if category is None:
            return {"category_id": "", "category_name": "No Category"}
        return {"category_id": str(category.id), "category_name": category.name}

    @staticmethod
    def _channel_permission_delta(
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> dict[str, int]:
        """Return overwrite-level add/remove/update counts for channel permission changes."""
        before_overwrites = getattr(before, "overwrites", {}) or {}
        after_overwrites = getattr(after, "overwrites", {}) or {}

        before_map = {getattr(target, "id", None): overwrite for target, overwrite in before_overwrites.items()}
        after_map = {getattr(target, "id", None): overwrite for target, overwrite in after_overwrites.items()}
        all_target_ids = set(before_map) | set(after_map)

        created = 0
        deleted = 0
        updated = 0
        for target_id in all_target_ids:
            before_overwrite = before_map.get(target_id)
            after_overwrite = after_map.get(target_id)
            if before_overwrite is None and after_overwrite is not None:
                created += 1
                continue
            if before_overwrite is not None and after_overwrite is None:
                deleted += 1
                continue
            if before_overwrite is not None and after_overwrite is not None and before_overwrite.pair() != after_overwrite.pair():
                updated += 1

        return {
            "permission_overwrite_created": created,
            "permission_overwrite_deleted": deleted,
            "permission_overwrite_updated": updated,
        }

    @staticmethod
    def _channel_overwrite_details(
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> dict[str, Any]:
        before_overwrites = getattr(before, "overwrites", {}) or {}
        after_overwrites = getattr(after, "overwrites", {}) or {}
        before_map = {getattr(target, "id", None): (target, overwrite) for target, overwrite in before_overwrites.items()}
        after_map = {getattr(target, "id", None): (target, overwrite) for target, overwrite in after_overwrites.items()}

        added_targets: list[str] = []
        removed_targets: list[str] = []
        changed_permissions: list[str] = []

        for target_id in sorted(set(before_map) | set(after_map), key=lambda t: str(t)):
            before_item = before_map.get(target_id)
            after_item = after_map.get(target_id)
            if before_item is None and after_item is not None:
                after_target, _ = after_item
                added_targets.append(AuditLogCog._format_overwrite_target(after_target))
                continue
            if before_item is not None and after_item is None:
                before_target, _ = before_item
                removed_targets.append(AuditLogCog._format_overwrite_target(before_target))
                continue
            if before_item is None or after_item is None:
                continue
            before_target, before_overwrite = before_item
            _, after_overwrite = after_item
            before_perms = dict(before_overwrite)
            after_perms = dict(after_overwrite)
            perm_names = sorted(set(before_perms) | set(after_perms))
            changed_perm_entries = []
            for name in perm_names:
                before_value = before_perms.get(name)
                after_value = after_perms.get(name)
                if before_value == after_value:
                    continue
                changed_perm_entries.append(
                    f"{name}: {AuditLogCog._permission_state_label(before_value)} → {AuditLogCog._permission_state_label(after_value)}"
                )
            if changed_perm_entries:
                changed_permissions.append(
                    f"{AuditLogCog._format_overwrite_target(before_target)}\n" + "\n".join(changed_perm_entries[:8])
                )

        return {
            "permission_overwrite_added_targets": added_targets,
            "permission_overwrite_removed_targets": removed_targets,
            "permission_overwrite_changed_permissions": changed_permissions,
        }

    @staticmethod
    def _format_overwrite_target(target: Any) -> str:
        """Format overwrite target as role/member mention + id for audit readability."""
        target_id = str(getattr(target, "id", "unknown"))
        target_name = str(getattr(target, "name", getattr(target, "display_name", "Unknown")))
        is_role = hasattr(target, "permissions")
        mention = f"<@&{target_id}>" if is_role and target_id.isdigit() else (f"<@{target_id}>" if target_id.isdigit() else target_name)
        return f"{mention} ({target_name}, `{target_id}`)"

    @staticmethod
    def _permission_state_label(value: Any) -> str:
        """Map Discord overwrite tri-state values to human-readable labels."""
        if value is True:
            return "✅ allowed"
        if value is False:
            return "❌ denied"
        return "⚪ neutral"

    async def log_system_event(self, action: str, details: Optional[dict[str, Any]] = None) -> None:
        await self.log_action(
            action=action,
            category="system",
            actor=None,
            target=None,
            guild=None,
            details=details or {},
        )

    async def _flush_channel_update_event(self, channel_id: int) -> None:
        """Flush a coalesced channel update event so multiple rapid updates appear in one embed."""
        try:
            await asyncio.sleep(1.5)
            payload = self._channel_update_pending.pop(channel_id, None)
            if not payload:
                return
            await self.log_action(
                "channel_updated",
                "server",
                payload.get("actor"),
                payload.get("target"),
                payload.get("guild"),
                reason=payload.get("reason"),
                details=payload.get("details", {}),
            )
        finally:
            self._channel_update_tasks.pop(channel_id, None)

    # --- World Cup helper methods (call these from other cogs/services) ---
    async def log_bet_placed(self, actor, guild, bet_id, fixture_id, team, amount):
        await self.log_action("bet_placed", "betting", actor, actor, guild, details={"bet_id": bet_id, "fixture_id": fixture_id, "team": team, "amount": amount})

    async def log_bet_settled(self, actor, guild, bet_id, winner, losers):
        await self.log_action("bet_settled", "betting", actor, actor, guild, details={"bet_id": bet_id, "winner": winner, "losers": losers})

    async def log_team_reassigned(self, actor, guild, team, old_owner_id, new_owner_id):
        await self.log_action("team_reassigned", "ownership", actor, None, guild, details={"team": team, "old_owner": str(old_owner_id), "new_owner": str(new_owner_id)})

    async def log_split_request(self, actor, guild, team, request_id, status):
        await self.log_action("split_request", "ownership", actor, None, guild, details={"team": team, "request_id": request_id, "status": status})

    async def log_fanzone_vote(self, actor, guild, fixture_id, voted_team):
        await self.log_action("fanzone_vote", "fanzone", actor, actor, guild, details={"fixture_id": fixture_id, "voted_team": voted_team})

    async def log_fanzone_winner_declared(self, actor, guild, fixture_id, winner):
        await self.log_action("fanzone_winner_declared", "fanzone", actor, None, guild, details={"fixture_id": fixture_id, "winner": winner})

    async def log_terms_accepted(self, actor, guild, version):
        await self.log_action("terms_accepted", "compliance", actor, actor, guild, details={"version": version})

    async def log_masquerade_started(self, actor, guild, target_user_id):
        await self.log_action("masquerade_started", "admin", actor, None, guild, details={"target_user_id": str(target_user_id)})

    async def log_masquerade_stopped(self, actor, guild):
        await self.log_action("masquerade_stopped", "admin", actor, None, guild)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.log_system_event("bot_ready")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.log_action("member_join", "member", member, member, member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.log_action("member_leave", "member", None, member, member.guild)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        entry = await self._try_get_audit_entry(guild, discord.AuditLogAction.ban, user.id)
        await self.log_action("member_ban", "moderation", entry.user if entry else None, user, guild, reason=entry.reason if entry else None)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        entry = await self._try_get_audit_entry(guild, discord.AuditLogAction.unban, user.id)
        await self.log_action("member_unban", "moderation", entry.user if entry else None, user, guild, reason=entry.reason if entry else None)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or (message.author and message.author.bot):
            return
        await self.log_action(
            "message_delete",
            "message",
            message.author,
            message.author,
            message.guild,
            details={"channel_id": str(message.channel.id), "content": self._safe_content(message.content)},
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        await self.log_action(
            "bulk_message_delete",
            "message",
            None,
            None,
            guild,
            details={"count": len(messages), "channel_id": str(messages[0].channel.id)},
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or (after.author and after.author.bot) or before.content == after.content:
            return
        await self.log_action(
            "message_edit",
            "message",
            after.author,
            after.author,
            after.guild,
            details={"channel_id": str(after.channel.id), "before": self._safe_content(before.content), "after": self._safe_content(after.content)},
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Log slash command usage with resolved arguments for moderation visibility."""
        if interaction.type != discord.InteractionType.application_command:
            return
        if interaction.guild is None:
            return

        command_name = ""
        command_path = ""
        if getattr(interaction, "command", None) is not None:
            command_name = getattr(interaction.command, "name", "") or ""
            command_path = getattr(interaction.command, "qualified_name", "") or command_name

        data = interaction.data or {}
        if not command_name:
            command_name = str(data.get("name", "unknown"))
        if not command_path:
            command_path = command_name

        options_payload = data.get("options", [])
        await self.log_action(
            "Slash Command",
            "command",
            interaction.user,
            interaction.user,
            interaction.guild,
            details={
                "command_name": command_name,
                "command_path": command_path,
                "arguments": options_payload if isinstance(options_payload, list) else [],
                "channel_id": str(interaction.channel_id) if interaction.channel_id else "unknown",
            },
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_roles = {r.id for r in before.roles}
        after_roles = {r.id for r in after.roles}
        added = after_roles - before_roles
        removed = before_roles - after_roles
        # Try to resolve who changed roles from Discord audit logs so "Performed By" is populated.
        audit_entry = await self._try_get_audit_entry(after.guild, discord.AuditLogAction.member_role_update, after.id)
        performed_by = audit_entry.user if audit_entry and audit_entry.user else after
        for role_id in added:
            role = after.guild.get_role(role_id)
            await self.log_action("role_added", "moderation", performed_by, after, after.guild, reason=audit_entry.reason if audit_entry else None, details={"role_id": str(role_id), "role_name": role.name if role else "unknown"})
        for role_id in removed:
            role = after.guild.get_role(role_id)
            await self.log_action("role_removed", "moderation", performed_by, after, after.guild, reason=audit_entry.reason if audit_entry else None, details={"role_id": str(role_id), "role_name": role.name if role else "unknown"})

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        entry = await self._try_get_audit_entry(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        details = {"channel_id": str(channel.id), "name": channel.name, **self._channel_parent_payload(channel)}
        await self.log_action(
            "channel_created",
            "server",
            entry.user if entry else None,
            channel,
            channel.guild,
            reason=entry.reason if entry else None,
            details=details,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        entry = await self._try_get_audit_entry(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        details = {"channel_id": str(channel.id), "name": channel.name, **self._channel_parent_payload(channel)}
        await self.log_action(
            "channel_deleted",
            "server",
            entry.user if entry else None,
            channel,
            channel.guild,
            reason=entry.reason if entry else None,
            details=details,
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        entry = await self._try_get_channel_update_entry(after.guild, after.id)
        permission_delta = self._channel_permission_delta(before, after)
        overwrite_details = self._channel_overwrite_details(before, after)
        details = {
            "channel_id": str(after.id),
            "before_name": before.name,
            "after_name": after.name,
            **permission_delta,
            **overwrite_details,
        }
        channel_id = after.id
        pending = self._channel_update_pending.get(channel_id)
        if pending is None:
            self._channel_update_pending[channel_id] = {
                "actor": entry.user if entry else None,
                "target": after,
                "guild": after.guild,
                "reason": entry.reason if entry else None,
                "details": details,
            }
        else:
            # Merge rapid update bursts into a single payload to avoid split embeds.
            merged = pending["details"]
            merged["permission_overwrite_created"] = int(merged.get("permission_overwrite_created", 0)) + int(details.get("permission_overwrite_created", 0))
            merged["permission_overwrite_deleted"] = int(merged.get("permission_overwrite_deleted", 0)) + int(details.get("permission_overwrite_deleted", 0))
            merged["permission_overwrite_updated"] = int(merged.get("permission_overwrite_updated", 0)) + int(details.get("permission_overwrite_updated", 0))
            for key in ("permission_overwrite_added_targets", "permission_overwrite_removed_targets", "permission_overwrite_changed_permissions"):
                existing = list(merged.get(key, []))
                for item in details.get(key, []):
                    if item not in existing:
                        existing.append(item)
                merged[key] = existing
            pending["actor"] = pending.get("actor") or (entry.user if entry else None)
            pending["reason"] = pending.get("reason") or (entry.reason if entry else None)
            pending["target"] = after
            pending["guild"] = after.guild

        if channel_id not in self._channel_update_tasks:
            self._channel_update_tasks[channel_id] = asyncio.create_task(self._flush_channel_update_event(channel_id))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        # Resolve the creator from the audit log so creation events mirror role update attribution.
        entry = await self._try_get_audit_entry(role.guild, discord.AuditLogAction.role_create, role.id)
        await self.log_action(
            "role_created",
            "server",
            entry.user if entry else None,
            role,
            role.guild,
            reason=entry.reason if entry else None,
            details={"role_id": str(role.id), "role_name": role.name},
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        # Resolve the deleter from the audit log so deletion events mirror role update attribution.
        entry = await self._try_get_audit_entry(role.guild, discord.AuditLogAction.role_delete, role.id)
        await self.log_action(
            "role_deleted",
            "server",
            entry.user if entry else None,
            role,
            role.guild,
            reason=entry.reason if entry else None,
            details={"role_id": str(role.id), "role_name": role.name},
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        # Resolve the responsible moderator/admin from the Discord audit log whenever possible.
        # This prevents "Performed By: Unknown" for role rename/permission edits.
        entry = await self._try_get_audit_entry(after.guild, discord.AuditLogAction.role_update, after.id)
        await self.log_action(
            "role_updated",
            "server",
            entry.user if entry else None,
            after,
            after.guild,
            reason=entry.reason if entry else None,
            details={"role_id": str(after.id), "before_name": before.name, "after_name": after.name},
        )

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        # Include invite URL and creator metadata so moderators can audit exactly what was shared.
        await self.log_action(
            "invite_created",
            "server",
            invite.inviter,
            None,
            invite.guild,
            details={
                "code": invite.code,
                "invite_url": f"https://discord.gg/{invite.code}",
                "inviter_id": str(invite.inviter.id) if invite.inviter else "unknown",
                "inviter_name": str(invite.inviter) if invite.inviter else "Unknown",
                "channel_id": str(invite.channel.id) if invite.channel else "unknown",
            },
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        # Invite delete events do not always include an actor; resolve from audit logs when possible.
        entry = await self._try_get_invite_delete_entry(invite.guild, invite.code)
        await self.log_action(
            "invite_deleted",
            "server",
            entry.user if entry else None,
            None,
            invite.guild,
            reason=entry.reason if entry else None,
            details={
                "code": invite.code,
                "invite_url": f"https://discord.gg/{invite.code}",
                "channel_id": str(invite.channel.id) if invite.channel else "unknown",
            },
        )

    @commands.group(name="auditlog", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def auditlog_group(self, ctx: commands.Context):
        await ctx.send("Use: recent, user, action, export, clear")

    @auditlog_group.command(name="recent")
    async def auditlog_recent(self, ctx: commands.Context, amount: int = 25):
        entries = await self._read_entries()
        sliced = entries[-max(1, min(amount, 100)):]
        lines = [f"{e['timestamp']} | {e['action']} | actor={e['actor']['display_name']}" for e in sliced]
        await ctx.send("\n".join(lines) if lines else "No logs found.")

    @auditlog_group.command(name="user")
    async def auditlog_user(self, ctx: commands.Context, member: discord.Member, amount: int = 25):
        entries = await self._read_entries()
        filtered = [e for e in entries if e.get("actor", {}).get("id") == str(member.id) or e.get("target", {}).get("id") == str(member.id)]
        sliced = filtered[-max(1, min(amount, 100)):]
        lines = [f"{e['timestamp']} | {e['action']} | result={e['result']}" for e in sliced]
        await ctx.send("\n".join(lines) if lines else "No logs for that user.")

    @auditlog_group.command(name="action")
    async def auditlog_action(self, ctx: commands.Context, action_name: str, amount: int = 25):
        entries = await self._read_entries()
        filtered = [e for e in entries if e.get("action") == action_name]
        sliced = filtered[-max(1, min(amount, 100)):]
        lines = [f"{e['timestamp']} | actor={e['actor']['display_name']} | target={e['target']['display_name']}" for e in sliced]
        await ctx.send("\n".join(lines) if lines else "No logs for that action.")

    @auditlog_group.command(name="export")
    async def auditlog_export(self, ctx: commands.Context):
        entries = await self._read_entries()
        await self._backup_entries(entries)
        await ctx.send(file=discord.File(self._audit_file))

    @auditlog_group.command(name="clear")
    async def auditlog_clear(self, ctx: commands.Context, confirm: str):
        if confirm != "CONFIRM":
            await ctx.send("You must pass exactly: CONFIRM")
            return
        async with self._write_lock:
            await self._write_entries([])
        await self.log_action("auditlog_cleared", "admin", ctx.author, None, ctx.guild)
        await ctx.send("Audit log cleared.")

    @auditlog_group.error
    async def auditlog_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Administrator permission required.")
            return
        await self.log_system_event("api_error", details={"error": str(error)})


async def setup(bot):
    await bot.add_cog(AuditLogCog(bot))
