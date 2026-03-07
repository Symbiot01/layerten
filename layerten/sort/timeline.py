"""Topological sort for commits + chronological interleave into timeline."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from pathlib import Path

from dateutil.parser import isoparse

from layerten.config import UNIFIED_EVENTS_PATH, UNIFIED_TIMELINE_PATH

logger = logging.getLogger(__name__)


def _parse_ts(ts_str: str | None) -> float:
    """Parse an ISO 8601 timestamp to a float for sorting. Returns 0.0 on failure."""
    if not ts_str:
        return 0.0
    try:
        return isoparse(ts_str).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _topo_sort_commits(commits: list[dict]) -> list[dict]:
    """Topological sort commits by parent_shas using Kahn's algorithm.

    Breaks ties by committed_at (oldest first).
    Handles missing parents gracefully (parents not in our commit set).
    """
    sha_to_commit: dict[str, dict] = {c["sha"]: c for c in commits}
    children: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {c["sha"]: 0 for c in commits}

    for c in commits:
        for parent_sha in c.get("parent_shas", []):
            if parent_sha in sha_to_commit:
                children[parent_sha].append(c["sha"])
                in_degree[c["sha"]] += 1

    queue: list[tuple[float, str]] = []
    for sha, deg in in_degree.items():
        if deg == 0:
            ts = _parse_ts(sha_to_commit[sha].get("timestamp"))
            queue.append((ts, sha))
    queue.sort()

    sorted_commits: list[dict] = []
    while queue:
        _, sha = queue.pop(0)
        sorted_commits.append(sha_to_commit[sha])

        for child_sha in children.get(sha, []):
            in_degree[child_sha] -= 1
            if in_degree[child_sha] == 0:
                ts = _parse_ts(sha_to_commit[child_sha].get("timestamp"))
                queue.append((ts, child_sha))
                queue.sort()

    if len(sorted_commits) < len(commits):
        processed = {c["sha"] for c in sorted_commits}
        remaining = [c for c in commits if c["sha"] not in processed]
        remaining.sort(key=lambda c: _parse_ts(c.get("timestamp")))
        sorted_commits.extend(remaining)
        logger.warning(
            "Topo sort: %d commits in cycles, appended by timestamp",
            len(remaining),
        )

    return sorted_commits


def _interleave(
    sorted_commits: list[dict],
    sorted_others: list[dict],
) -> list[dict]:
    """Merge two sorted lists by timestamp. Commits win ties."""
    result: list[dict] = []
    ci, oi = 0, 0

    while ci < len(sorted_commits) and oi < len(sorted_others):
        ct = _parse_ts(sorted_commits[ci].get("timestamp"))
        ot = _parse_ts(sorted_others[oi].get("timestamp"))

        if ct <= ot:
            result.append(sorted_commits[ci])
            ci += 1
        else:
            result.append(sorted_others[oi])
            oi += 1

    result.extend(sorted_commits[ci:])
    result.extend(sorted_others[oi:])
    return result


def run_sort() -> None:
    start = time.time()
    logger.info("=== SORT PHASE START ===")

    logger.info("Loading events from %s", UNIFIED_EVENTS_PATH)
    commits: list[dict] = []
    others: list[dict] = []

    with open(UNIFIED_EVENTS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event["type"] == "commit":
                commits.append(event)
            else:
                others.append(event)

    logger.info("Loaded %d commits + %d others = %d total",
                len(commits), len(others), len(commits) + len(others))

    # Topological sort commits
    logger.info("Topologically sorting %d commits...", len(commits))
    sorted_commits = _topo_sort_commits(commits)

    # Chronological sort non-commit events
    logger.info("Chronologically sorting %d non-commit events...", len(others))
    sorted_others = sorted(others, key=lambda e: _parse_ts(e.get("timestamp")))

    # Interleave
    logger.info("Interleaving into final timeline...")
    timeline = _interleave(sorted_commits, sorted_others)

    # Assign timeline_index
    for i, event in enumerate(timeline):
        event["timeline_index"] = i

    # Write output
    logger.info("Writing %d events to %s", len(timeline), UNIFIED_TIMELINE_PATH)
    UNIFIED_TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(UNIFIED_TIMELINE_PATH, "w") as f:
        for event in timeline:
            f.write(json.dumps(event, default=str) + "\n")

    elapsed = time.time() - start

    type_counts: dict[str, int] = {}
    for e in timeline:
        t = e["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\n" + "=" * 60)
    print("SORT PHASE COMPLETE")
    print("=" * 60)
    print(f"  Time elapsed:     {elapsed:.1f}s")
    print(f"  Timeline events:  {len(timeline)}")
    for t, count in sorted(type_counts.items()):
        print(f"    {t:20s} {count:>6}")
    if timeline:
        print(f"  First event:      {timeline[0].get('timestamp', 'N/A')}")
        print(f"  Last event:       {timeline[-1].get('timestamp', 'N/A')}")
    print("=" * 60)
