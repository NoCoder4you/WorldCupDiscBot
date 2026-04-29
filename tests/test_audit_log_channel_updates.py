from types import SimpleNamespace

from COGS.audit_log import AuditLogCog


class _Overwrite:
    def __init__(self, allow: int, deny: int):
        self._allow = allow
        self._deny = deny

    def pair(self):
        return (self._allow, self._deny)

    def __iter__(self):
        # Mimic discord.PermissionOverwrite iteration output.
        yield "view_channel", bool(self._allow & 1)
        yield "send_messages", bool(self._allow & 2)
        yield "manage_messages", bool(self._allow & 4)


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
    assert "send_messages" in details["permission_overwrite_changed_permissions"][0]
