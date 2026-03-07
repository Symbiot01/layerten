from __future__ import annotations

import logging

from layerten.process.bootstrap import ReferenceData

logger = logging.getLogger(__name__)


def get_event(key: str, ref_data: ReferenceData) -> dict:
    """Get a specific event by its natural_key from the timeline index."""
    event = ref_data.timeline_index.get(key)
    if event is None:
        return {"error": f"Event not found: {key}"}
    safe = {k: v for k, v in event.items() if k != "body" or len(str(v)) <= 5000}
    if "body" in event and len(str(event["body"])) > 5000:
        safe["body"] = str(event["body"])[:5000] + "... (truncated)"
    return safe


def get_related_events(
    key: str, types: list[str] | None, ref_data: ReferenceData
) -> dict:
    """Find events related to the given key by cross-references or shared attributes."""
    source = ref_data.timeline_index.get(key)
    if source is None:
        return {"error": f"Event not found: {key}"}

    related = []

    for xref in source.get("cross_references", []):
        target_key = xref.get("target")
        if target_key and target_key in ref_data.timeline_index:
            ev = ref_data.timeline_index[target_key]
            if types is None or ev.get("type") in types:
                related.append({
                    "natural_key": ev["natural_key"],
                    "type": ev["type"],
                    "timestamp": ev.get("timestamp"),
                    "title": ev.get("title", ev.get("message", ""))[:200],
                    "relation": xref.get("type"),
                })

    if source.get("type") == "commit":
        for parent_sha in source.get("parent_shas", []):
            parent_key = f"commit:{parent_sha}"
            if parent_key in ref_data.timeline_index:
                ev = ref_data.timeline_index[parent_key]
                if types is None or "commit" in types:
                    related.append({
                        "natural_key": parent_key,
                        "type": "commit",
                        "timestamp": ev.get("timestamp"),
                        "title": ev.get("message", "")[:200],
                        "relation": "parent_commit",
                    })

        pr_num = source.get("merge_commit_for_pr")
        if pr_num:
            pr_key = f"pr:{pr_num}"
            if pr_key in ref_data.timeline_index:
                ev = ref_data.timeline_index[pr_key]
                if types is None or "pr" in types:
                    related.append({
                        "natural_key": pr_key,
                        "type": "pr",
                        "timestamp": ev.get("timestamp"),
                        "title": ev.get("title", "")[:200],
                        "relation": "merge_commit_for",
                    })

    return {"related": related, "count": len(related)}
