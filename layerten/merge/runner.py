"""Orchestrate the full merge phase: load -> merge -> enrich -> write."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from layerten.config import (
    MERGE_LOG_PATH,
    RAW_EVENTS_PATH,
    UNIFIED_BRANCHES_PATH,
    UNIFIED_DIR,
    UNIFIED_EVENTS_PATH,
    UNIFIED_FILE_TREE_PATH,
    UNIFIED_INDEX_PATH,
    UNIFIED_LABELS_PATH,
    UNIFIED_PERSONS_PATH,
    UNIFIED_RENAMES_PATH,
)
from layerten.merge.classify import compute_processing_hints
from layerten.merge.loader import load_and_group
from layerten.merge.merge_artifacts import (
    build_renames_index,
    extract_file_tree,
    merge_all_branches,
    merge_all_discussions,
    merge_all_issues,
    merge_all_labels,
    merge_all_prs,
    merge_all_tags,
)
from layerten.merge.merge_commits import apply_pr_reverse_map, merge_all_commits
from layerten.merge.persons import build_person_map

logger = logging.getLogger(__name__)


class MergeLog:
    """Collects merge/dedup decisions for the audit log."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def log(self, dedup_type: str, artifact: str, **details: object) -> None:
        self.entries.append({
            "dedup_type": dedup_type,
            "artifact": artifact,
            **details,
        })


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for item in items:
            f.write(json.dumps(item, default=str) + "\n")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def run_merge() -> None:
    start = time.time()
    merge_log = MergeLog()

    logger.info("=== MERGE PHASE START ===")

    # 1. Load and group raw events
    logger.info("--- Step 1: Loading raw events ---")
    groups, raw_counts = load_and_group(RAW_EVENTS_PATH)

    # 2. Merge commits
    logger.info("--- Step 2: Merging commits ---")
    merged_commits, alias_pairs = merge_all_commits(groups)
    commits_by_sha = {c["sha"]: c for c in merged_commits}

    for c in merged_commits:
        if "github_api" in c["sources"]:
            merge_log.log("cross_source_merge", c["natural_key"])

    # 3. Build person alias map, resolve clone-only commits
    logger.info("--- Step 3: Building person alias map ---")
    persons, email_to_login = build_person_map(alias_pairs, merged_commits)

    for email, login in email_to_login.items():
        merge_log.log("person_alias_discovered", f"person:{login}", email=email)

    # 4. Merge PRs
    logger.info("--- Step 4: Merging PRs ---")
    merged_prs = merge_all_prs(groups, commits_by_sha)

    # 5. Build reverse map: merge_commit_sha -> pr_number
    logger.info("--- Step 5: Applying PR reverse map ---")
    apply_pr_reverse_map(merged_commits, merged_prs)

    # 6. Merge other timeline events
    logger.info("--- Step 6: Merging issues, discussions, tags ---")
    merged_issues = merge_all_issues(groups)
    merged_discussions = merge_all_discussions(groups)
    merged_tags = merge_all_tags(groups, commits_by_sha)

    for tag in merged_tags:
        if len(tag.get("sources", [])) > 1:
            merge_log.log("tag_release_joined", tag["natural_key"])

    # 7. Classify files + compute processing hints
    logger.info("--- Step 7: Computing processing hints ---")
    timeline_events = merged_commits + merged_prs + merged_issues + merged_discussions + merged_tags
    for event in timeline_events:
        event["processing_hints"] = compute_processing_hints(event)

    # 8. Build reference data
    logger.info("--- Step 8: Building reference data ---")
    branches = merge_all_branches(groups, merged_prs)
    labels = merge_all_labels(groups)
    renames = build_renames_index(groups)
    file_tree = extract_file_tree(groups)

    for b in branches:
        if b["status"] == "deleted":
            merge_log.log("ghost_branch_recovered", f"branch:{b['name']}",
                          discovered_from=b["discovered_from"])

    # 9. Write all outputs
    logger.info("--- Step 9: Writing outputs ---")
    UNIFIED_DIR.mkdir(parents=True, exist_ok=True)

    _write_jsonl(UNIFIED_EVENTS_PATH, timeline_events)
    _write_json(UNIFIED_PERSONS_PATH, persons)
    _write_json(UNIFIED_BRANCHES_PATH, branches)
    _write_json(UNIFIED_LABELS_PATH, labels)
    _write_json(UNIFIED_RENAMES_PATH, renames)
    _write_json(UNIFIED_FILE_TREE_PATH, file_tree)
    _write_jsonl(MERGE_LOG_PATH, merge_log.entries)

    # Build and write index
    type_counts: dict[str, int] = {}
    for e in timeline_events:
        t = e["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    merge_log_counts: dict[str, int] = {}
    for entry in merge_log.entries:
        dt = entry["dedup_type"]
        merge_log_counts[dt] = merge_log_counts.get(dt, 0) + 1

    index = {
        "raw_event_counts": raw_counts,
        "timeline_event_counts": type_counts,
        "timeline_total": len(timeline_events),
        "persons_count": len(persons),
        "branches_count": len(branches),
        "labels_count": len(labels),
        "renames_count": sum(len(v) for v in renames.values()),
        "renames_commits": len(renames),
        "file_tree_files": len(file_tree.get("files", [])),
        "merge_log_counts": merge_log_counts,
        "merge_log_total": len(merge_log.entries),
    }
    _write_json(UNIFIED_INDEX_PATH, index)

    elapsed = time.time() - start

    # Summary
    print("\n" + "=" * 60)
    print("MERGE PHASE COMPLETE")
    print("=" * 60)
    print(f"  Time elapsed:     {elapsed:.1f}s")
    print(f"  Timeline events:  {len(timeline_events)}")
    for t, count in sorted(type_counts.items()):
        print(f"    {t:20s} {count:>6}")
    print(f"  Persons:          {len(persons)}")
    print(f"  Branches:         {len(branches)}")
    print(f"  Labels:           {len(labels)}")
    print(f"  Renames:          {sum(len(v) for v in renames.values())} across {len(renames)} commits")
    print(f"  Merge log:        {len(merge_log.entries)} decisions")
    print("=" * 60)
