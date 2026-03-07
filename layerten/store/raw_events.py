import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from layerten.config import CHECKPOINT_PATH, RAW_EVENTS_PATH

logger = logging.getLogger(__name__)


def write_raw_event(
    event_type: str,
    artifact_id: str,
    payload: dict,
    source: str = "github_api",
) -> None:
    RAW_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "id": f"{event_type}:{artifact_id}",
        "event_type": event_type,
        "source": source,
        "artifact_id": artifact_id,
        "payload": payload,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(RAW_EVENTS_PATH, "a") as f:
        f.write(json.dumps(event, default=str) + "\n")


def get_fetched_ids(event_type: str | None = None) -> set[str]:
    """Return all event IDs already in the JSONL log, for dedup/resumability."""
    if not RAW_EVENTS_PATH.exists():
        return set()
    ids: set[str] = set()
    with open(RAW_EVENTS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if event_type is None or obj.get("event_type") == event_type:
                    ids.add(obj["id"])
            except json.JSONDecodeError:
                continue
    return ids


def count_events_by_type() -> dict[str, int]:
    """Count raw events grouped by event_type."""
    if not RAW_EVENTS_PATH.exists():
        return {}
    counts: dict[str, int] = {}
    with open(RAW_EVENTS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                et = obj.get("event_type", "unknown")
                counts[et] = counts.get(et, 0) + 1
            except json.JSONDecodeError:
                continue
    return counts


def save_checkpoint(source: str, cursor_data: dict) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    checkpoints = _load_all_checkpoints()
    checkpoints[source] = {
        **cursor_data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(checkpoints, f, indent=2)


def load_checkpoint(source: str) -> dict | None:
    checkpoints = _load_all_checkpoints()
    return checkpoints.get(source)


def clear_checkpoint(source: str) -> None:
    checkpoints = _load_all_checkpoints()
    checkpoints.pop(source, None)
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(checkpoints, f, indent=2)


def _load_all_checkpoints() -> dict:
    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        with open(CHECKPOINT_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
