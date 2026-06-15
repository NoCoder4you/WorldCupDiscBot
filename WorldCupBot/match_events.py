"""Helpers for presenting manually entered match events in match-clock order."""


def match_event_sort_key(event: dict) -> tuple[int, int, int]:
    """Return a sortable match-clock key, including stoppage and half time."""
    event_type = str(event.get("event_type") or "").strip().lower()
    match_time = str(event.get("match_time") or "").strip()

    if event_type == "half_time":
        # Half time occurs after all first-half stoppage-time incidents but
        # before minute 46, regardless of when the operator records it.
        return (45, 1_000_000, 1)

    base_text, _, stoppage_text = match_time.partition("+")
    if base_text.isdigit():
        return (
            int(base_text),
            int(stoppage_text) if stoppage_text.isdigit() else 0,
            0,
        )

    # Keep malformed legacy records visible at the end instead of dropping
    # them; new dashboard entries are validated before reaching this helper.
    return (1_000_000, 0, 0)


def sort_match_events(events: list) -> list:
    """Return valid event dictionaries in stable chronological order."""
    return sorted(
        (event for event in events if isinstance(event, dict)),
        key=match_event_sort_key,
    )
