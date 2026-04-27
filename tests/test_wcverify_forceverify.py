from types import SimpleNamespace

from COGS.WCVerify import SpectatorVerify


class _FakeAvatar:
    def __init__(self, key: str):
        self.key = key


class _FakeMember:
    def __init__(self, member_id: int, name: str, display_name: str, global_name: str | None = None):
        self.id = member_id
        self.name = name
        self.display_name = display_name
        self.global_name = global_name
        self.avatar = None

    def __str__(self):
        return f"{self.name}#0001"


def _build_member(member_id: int, name: str, display_name: str, global_name: str | None = None):
    """
    Build a lightweight member-like object for username resolution tests.

    The cog only reads these attributes, so a SimpleNamespace keeps tests
    fast and independent of Discord gateway internals.
    """
    return _FakeMember(member_id=member_id, name=name, display_name=display_name, global_name=global_name)


def test_find_member_by_username_matches_exact_display_name():
    bot = SimpleNamespace()
    cog = SpectatorVerify(bot)
    guild = SimpleNamespace(members=[_build_member(1, "runner", "Noah")])

    found = cog._find_member_by_username(guild, "Noah")

    assert found is not None
    assert found.id == 1


def test_find_member_by_username_supports_partial_match():
    bot = SimpleNamespace()
    cog = SpectatorVerify(bot)
    guild = SimpleNamespace(
        members=[
            _build_member(1, "runner", "Noah"),
            _build_member(2, "speedster", "Speed Queen"),
        ]
    )

    found = cog._find_member_by_username(guild, "queen")

    assert found is not None
    assert found.id == 2


def test_build_avatar_url_uses_default_when_avatar_missing():
    bot = SimpleNamespace()
    cog = SpectatorVerify(bot)
    member = _build_member(8, "runner", "Noah")

    avatar_url = cog._build_avatar_url(member)

    assert avatar_url == "https://cdn.discordapp.com/embed/avatars/3.png"


def test_build_avatar_url_uses_custom_avatar_when_present():
    bot = SimpleNamespace()
    cog = SpectatorVerify(bot)
    member = _build_member(42, "runner", "Noah")
    member.avatar = _FakeAvatar("abc123")

    avatar_url = cog._build_avatar_url(member)

    assert avatar_url == "https://cdn.discordapp.com/avatars/42/abc123.png?size=256"
