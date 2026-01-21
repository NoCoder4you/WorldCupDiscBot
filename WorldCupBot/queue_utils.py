import json
import os
from typing import Iterable


def compact_command_queue(queue_path: str, state_paths: Iterable[str], *, min_bytes: int = 4096) -> None:
    if not os.path.isfile(queue_path):
        return

    try:
        size = os.path.getsize(queue_path)
    except Exception:
        return

    if size <= 0:
        return

    offsets = {}
    for path in state_paths:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            offsets[path] = int(data.get("offset") or 0)
        except Exception:
            continue

    if not offsets:
        return

    min_offset = min(offsets.values())
    if min_offset <= 0:
        return

    if min_offset < size and min_offset < min_bytes:
        return

    if min_offset > size:
        min_offset = size

    try:
        with open(queue_path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(min_offset)
            remaining = f.read()
    except Exception:
        return

    tmp_path = f"{queue_path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            if remaining:
                f.write(remaining)
        os.replace(tmp_path, queue_path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return

    for path, offset in offsets.items():
        new_offset = max(0, int(offset) - min_offset)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"offset": new_offset}, f)
        except Exception:
            continue
