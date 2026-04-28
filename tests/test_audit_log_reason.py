from COGS.audit_log import AuditLogCog


def test_format_reason_uses_fallback_when_reason_missing():
    """Missing reason should use the updated fallback copy for audit embeds."""
    assert AuditLogCog._format_reason(None) == "No information is provided and should be."


def test_format_reason_returns_trimmed_reason_when_present():
    """Non-empty reasons should be trimmed and preserved in audit embeds."""
    assert AuditLogCog._format_reason("  Reviewed by moderator  ") == "Reviewed by moderator"


def test_format_reason_truncates_long_reason_to_embed_limit():
    """Reason text should never exceed the embed description size we enforce."""
    long_reason = "x" * 700
    assert len(AuditLogCog._format_reason(long_reason)) == 500
