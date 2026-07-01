"""Helpers for presenting manually entered match events in match-clock order."""


def match_event_sort_key(event: dict) -> tuple[int, int, int]:
    """Return a sortable match-clock key, including stoppage and half time."""
    event_type = str(event.get("event_type") or "").strip().lower()
    match_time = str(event.get("match_time") or "").strip()

    # One-tap match-state controls intentionally do not require operators to
    # type a minute. Give those state markers their real football-clock
    # position so final summaries stay chronological instead of drifting to
    # the bottom as "missing time" events.
    state_event_keys = {
        # Half time occurs after all first-half stoppage-time incidents but
        # before minute 46, regardless of when the operator records it.
        "half_time": (45, 1_000_000, 1),
        # Extra time starts after all second-half stoppage-time incidents.
        "extra_time": (90, 1_000_000, 1),
        # The extra-time interval follows first extra-time stoppage time.
        "extra_time_half_time": (105, 1_000_000, 1),
        # Full time in extra time follows any 120+ stoppage-time incident.
        "extra_time_full_time": (120, 1_000_000, 1),
        # Penalties begin after extra-time full time; keep this after the
        # whistle when both markers are present with the same displayed clock.
        "extra_time_penalties": (120, 1_000_000, 2),
    }
    if event_type in state_event_keys:
        return state_event_keys[event_type]

    base_text, _, stoppage_text = match_time.partition("+")
    if base_text.isdigit():
        return (
            int(base_text),
            int(stoppage_text) if stoppage_text.isdigit() else 0,
            state_event_keys.get(event_type, (0, 0, 0))[2],
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
