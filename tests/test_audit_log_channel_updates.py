from types import SimpleNamespace

from COGS.audit_log import AuditLogCog
import asyncio
from datetime import datetime, timezone


class _Overwrite:
    def __init__(self, allow: int, deny: int):
        self._allow = allow
        self._deny = deny

    def pair(self):
        return (self._allow, self._deny)

    def __iter__(self):
        # Mimic discord.PermissionOverwrite iteration output.
        for name, bit in (("view_channel", 1), ("send_messages", 2), ("manage_messages", 4)):
            if self._allow & bit:
                value = True
            elif self._deny & bit:
                value = False
            else:
                value = None
            yield name, value


class _Target:
    def __init__(self, target_id: int, name: str, is_role: bool = True):
        self.id = target_id
        self.name = name
        if is_role:
            # Presence of `permissions` is used by audit logger to detect role targets.
            self.permissions = 0


def test_channel_permission_delta_counts_created_deleted_and_updated():
    """Channel update audit details should include overwrite add/remove/update counts."""
    cog = AuditLogCog(SimpleNamespace())
    before = SimpleNamespace(
        overwrites={
            _Target(100, "Everyone"): _Overwrite(1, 0),
            _Target(200, "Moderators"): _Overwrite(2, 0),
        }
    )
    after = SimpleNamespace(
        overwrites={
            _Target(100, "Everyone"): _Overwrite(1, 0),  # unchanged
            _Target(200, "Moderators"): _Overwrite(4, 0),  # updated
            _Target(300, "Helpers"): _Overwrite(0, 2),  # created
        }
    )

    details = cog._channel_permission_delta(before, after)

    assert details["permission_overwrite_created"] == 1
    assert details["permission_overwrite_deleted"] == 0
    assert details["permission_overwrite_updated"] == 1


def test_channel_overwrite_details_lists_targets_and_permissions():
    """Channel update details should show which targets changed and exact permission keys."""
    cog = AuditLogCog(SimpleNamespace())
    before = SimpleNamespace(
        overwrites={
            _Target(200, "Moderators"): _Overwrite(2, 0),
            _Target(400, "Legacy"): _Overwrite(1, 0),
        }
    )
    after = SimpleNamespace(
        overwrites={
            _Target(200, "Moderators"): _Overwrite(4, 0),  # permission change
            _Target(300, "Helpers"): _Overwrite(0, 2),  # added target
        }
    )

    details = cog._channel_overwrite_details(before, after)

    assert len(details["permission_overwrite_added_targets"]) == 1
    assert "Helpers" in details["permission_overwrite_added_targets"][0]
    assert len(details["permission_overwrite_removed_targets"]) == 1
    assert "Legacy" in details["permission_overwrite_removed_targets"][0]
    assert len(details["permission_overwrite_changed_permissions"]) == 1
    assert "Moderators" in details["permission_overwrite_changed_permissions"][0]
    assert "send_messages: ✅ allowed → ⚪ neutral" in details["permission_overwrite_changed_permissions"][0]
    assert "manage_messages: ⚪ neutral → ✅ allowed" in details["permission_overwrite_changed_permissions"][0]


def test_channel_update_embed_omits_name_change_when_name_is_unchanged():
    """Name Change should not be shown when before/after channel names are identical."""
    cog = AuditLogCog(SimpleNamespace())

    class _FakeChannel:
        def __init__(self):
            self.name = "bot-audit-log"
            self.sent_embed = None

        def permissions_for(self, _member):
            return SimpleNamespace(send_messages=True)

        async def send(self, embed):
            self.sent_embed = embed

    fake_channel = _FakeChannel()
    guild = SimpleNamespace(text_channels=[fake_channel], me=SimpleNamespace())
    entry = {
        "action": "channel_updated",
        "actor": {"display_name": "Unknown", "id": "unknown"},
        "target": {"display_name": "admin-general", "id": "123"},
        "details": {
            "channel_id": "123",
            "before_name": "admin-general",
            "after_name": "admin-general",
            "permission_overwrite_updated": 1,
            "permission_overwrite_changed_permissions": ["@Role: manage_channels"],
        },
    }

    asyncio.run(cog._post_to_audit_channel(guild, entry))

    assert fake_channel.sent_embed is not None
    field_names = [field.name for field in fake_channel.sent_embed.fields]
    assert "Name Change" not in field_names


def test_try_get_channel_update_entry_matches_extra_channel_for_overwrite_events():
    """Resolver should use audit entry extra.channel when target is not the channel object."""
    cog = AuditLogCog(SimpleNamespace())
    now = datetime.now(timezone.utc)
    expected_entry = SimpleNamespace(
        created_at=now,
        target=SimpleNamespace(id=999),  # not matching channel id
        extra=SimpleNamespace(channel=SimpleNamespace(id=123)),
    )

    class _FakeGuild:
        def __init__(self):
            self.me = SimpleNamespace(guild_permissions=SimpleNamespace(view_audit_log=True))

        def audit_logs(self, limit, action):
            async def _iter():
                yield expected_entry
            return _iter()

    resolved = asyncio.run(cog._try_get_channel_update_entry(_FakeGuild(), 123))
    assert resolved is expected_entry


def test_permission_state_label_maps_to_allowed_neutral_denied():
    """Permission state labels should match Discord overwrite tri-state semantics."""
    assert AuditLogCog._permission_state_label(True) == "✅ allowed"
    assert AuditLogCog._permission_state_label(None) == "⚪ neutral"
    assert AuditLogCog._permission_state_label(False) == "❌ denied"


def test_channel_update_events_are_coalesced_into_single_log_action():
    """Rapid channel update events should be merged so only one embed/log entry is emitted."""
    cog = AuditLogCog(SimpleNamespace())
    captured = []

    async def _fake_try_get_channel_update_entry(guild, channel_id):
        return None

    async def _fake_log_action(action, category, actor, target, guild, result="success", reason=None, details=None):
        captured.append((action, details or {}))

    cog._try_get_channel_update_entry = _fake_try_get_channel_update_entry
    cog.log_action = _fake_log_action

    guild = SimpleNamespace()
    before_a = SimpleNamespace(id=123, name="bot-audit-log", guild=guild, overwrites={_Target(1, "R1"): _Overwrite(1, 0)})
    after_a = SimpleNamespace(id=123, name="bot-audit-log", guild=guild, overwrites={_Target(1, "R1"): _Overwrite(1, 0), _Target(2, "R2"): _Overwrite(0, 2)})
    before_b = after_a
    after_b = SimpleNamespace(id=123, name="bot-audit-log", guild=guild, overwrites={_Target(1, "R1"): _Overwrite(4, 0), _Target(2, "R2"): _Overwrite(0, 2)})

    async def _run():
        await cog.on_guild_channel_update(before_a, after_a)
        await cog.on_guild_channel_update(before_b, after_b)
        await asyncio.sleep(1.7)

    asyncio.run(_run())

    assert len(captured) == 1
    assert captured[0][0] == "channel_updated"
    assert captured[0][1]["permission_overwrite_created"] == 1
    assert captured[0][1]["permission_overwrite_updated"] == 1
