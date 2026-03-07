"""Load raw events from JSONL and group by natural key."""

import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


def _natural_key(event: dict) -> str:
    """Map a raw event to the natural key it should merge on."""
    et = event["event_type"]
    aid = event["artifact_id"]

    if et in ("commit_clone", "commit_api"):
        return f"commit:{aid}"
    if et == "release":
        return f"tag:{aid}"
    return f"{et}:{aid}"


def load_and_group(path: Path) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Stream events.jsonl, group raw events by natural key.

    Returns (groups, raw_counts) where:
      - groups: {natural_key: [raw_event, ...]}
      - raw_counts: {event_type: count}
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    raw_counts: dict[str, int] = defaultdict(int)

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSON at line %d", line_num)
                continue

            raw_counts[event["event_type"]] += 1
            key = _natural_key(event)
            groups[key].append(event)

    total = sum(raw_counts.values())
    logger.info(
        "Loaded %d raw events into %d groups from %s",
        total,
        len(groups),
        path,
    )
    for et, count in sorted(raw_counts.items()):
        logger.info("  %-20s %6d", et, count)

    return dict(groups), dict(raw_counts)
