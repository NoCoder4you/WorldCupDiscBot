import asyncio
from types import SimpleNamespace

from COGS.AuditLog import AuditLogCog


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


def test_flatten_command_options_supports_nested_subcommand_arguments():
    """Nested slash-command options should be flattened into readable key=value rows."""
    options = [
        {
            "name": "team",
            "options": [
                {"name": "set", "options": [{"name": "name", "value": "Brazil"}, {"name": "seed", "value": 5}]}
            ],
        }
    ]

    flattened = AuditLogCog._flatten_command_options(options)

    assert "team.set.name='Brazil'" in flattened
    assert "team.set.seed=5" in flattened


def test_slash_command_embed_includes_command_and_arguments_fields():
    """Slash command audit embeds should include command path and parsed argument values."""
    cog = AuditLogCog(SimpleNamespace())
    channel = _FakeChannel()
    guild = _FakeGuild(channel)

    entry = {
        "action": "slash_command_used",
        "actor": {"display_name": "Referee", "id": "123"},
        "target": {"display_name": "Referee", "id": "123"},
        "details": {
            "command_path": "team set",
            "arguments": [{"name": "name", "value": "Brazil"}, {"name": "seed", "value": 5}],
            "channel_id": "999",
        },
    }

    asyncio.run(cog._post_to_audit_channel(guild, entry))

    assert channel.sent_embed is not None
    fields = {field.name: field.value for field in channel.sent_embed.fields}
    assert fields["Command"] == "`/team set`"
    assert "name='Brazil'" in fields["Arguments"]
    assert "seed=5" in fields["Arguments"]
