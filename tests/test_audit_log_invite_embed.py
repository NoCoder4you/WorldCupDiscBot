import asyncio
from types import SimpleNamespace

from COGS.audit_log import AuditLogCog


class _FakeChannel:
    def __init__(self):
        self.name = "bot-audit-log"
        self.sent_embed = None

    def permissions_for(self, _member):
        return SimpleNamespace(send_messages=True)

    async def send(self, embed):
        self.sent_embed = embed


class _FakeGuild:
    def __init__(self, channel):
        self.text_channels = [channel]
        self.me = SimpleNamespace()


def test_invite_embed_includes_link_and_creator_fields():
    """Invite audit entries should include direct invite link and creator metadata for moderators."""
    cog = AuditLogCog(SimpleNamespace())
    channel = _FakeChannel()
    guild = _FakeGuild(channel)

    entry = {
        "action": "invite_created",
        "actor": {"display_name": "Noah", "id": "111"},
        "target": {"display_name": "Unknown", "id": "unknown"},
        "details": {
            "invite_url": "https://discord.gg/abc123",
            "inviter_name": "Noah",
            "inviter_id": "111",
            "channel_id": "222",
        },
    }

    asyncio.run(cog._post_to_audit_channel(guild, entry))

    assert channel.sent_embed is not None
    fields = {field.name: field.value for field in channel.sent_embed.fields}
    assert fields["Invite Link"] == "https://discord.gg/abc123"
    assert fields["Invite Created By"] == "Noah (`111`)"
