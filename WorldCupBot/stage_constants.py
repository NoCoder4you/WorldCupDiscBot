STAGE_ORDER = [
    "Eliminated",
    "Group Stage",
    "Round of 32",
    "Round of 16",
    "Quarter-finals",
    "Semi-finals",
    "Third Place Play-off",
    "Final",
    "Winner",
]

STAGE_ALLOWED = set(STAGE_ORDER)

STAGE_ALIASES = {
    "Quarter Final": "Quarter-finals",
    "Quarter Finals": "Quarter-finals",
    "Semi Final": "Semi-finals",
    "Semi Finals": "Semi-finals",
    "Third Place Play": "Third Place Play-off",
    "Third Place Playoff": "Third Place Play-off",
    "Third Place": "Third Place Play-off",
    "3rd Place Play-off": "Third Place Play-off",
}

STAGE_CHANNEL_SLUGS = {
    "Round of 32": "round-of-32",
    "Round of 16": "round-of-16",
    "Quarter-finals": "quarter-finals",
    "Semi-finals": "semi-finals",
    "Third Place Play-off": "third-place-play",
    "Final": "final",
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
