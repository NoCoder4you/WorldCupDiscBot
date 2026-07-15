STAGE_ORDER = [
    "Eliminated",
    "Group Stage",
    "Round of 32",
    "Round of 16",
    "Quarter-finals",
    "Semi-finals",
    "Third Place Play-off",
    "Final",
    "2nd Place",
    "3rd Place",
    "Winner",
]

STAGE_ALLOWED = set(STAGE_ORDER)

STAGE_ALIASES = {
    "Quarter Final": "Quarter-finals",
    "Quarter Finals": "Quarter-finals",
    "Semi Final": "Semi-finals",
    "Semi Finals": "Semi-finals",
    # Keep legacy imported fixture labels such as "Third Place" mapped to
    # the play-off round; final-placement outcomes must use explicit labels
    # like "3rd Place" so bracket fixtures do not disappear.
    "Third Place Play": "Third Place Play-off",
    "Third Place Playoff": "Third Place Play-off",
    "Third Place": "Third Place Play-off",
    "3rd Place Play-off": "Third Place Play-off",
    "Third Place Match": "Third Place Play-off",
    "Second Place": "2nd Place",
    "Runner-up": "2nd Place",
    "Runner Up": "2nd Place",
}

STAGE_CHANNEL_SLUGS = {
    "Round of 32": "round-of-32",
    "Round of 16": "round-of-16",
    "Quarter-finals": "quarter-finals",
    "Semi-finals": "semi-finals",
    "Third Place Play-off": "third-place-play",
    "Final": "final",
    "2nd Place": "final",
    "3rd Place": "third-place-play",
    "Winner": "final",
}

STAGE_CHANNEL_MAP = STAGE_CHANNEL_SLUGS


def normalize_stage(stage: str) -> str:
    raw = str(stage or "").strip()
    if not raw:
        return ""
    return STAGE_ALIASES.get(raw, raw)


def stage_rank(stage: str) -> int:
    stage = normalize_stage(stage)
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return -1
