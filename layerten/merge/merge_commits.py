"""Join commit_clone + commit_api events by SHA into unified commit events."""

from __future__ import annotations

import logging

from layerten.merge.classify import classify_files_changed
from layerten.merge.references import collect_references

logger = logging.getLogger(__name__)


def merge_all_commits(
    groups: dict[str, list[dict]],
) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Merge commit_clone and commit_api events into unified commits.

    Returns:
        (merged_commits, alias_pairs) where alias_pairs is a list of
        (email, login, name) tuples for building the person map.
    """
    merged: list[dict] = []
    alias_pairs: list[tuple[str, str, str]] = []
    clone_only = 0
    both_sources = 0

    for key, events in groups.items():
        if not key.startswith("commit:"):
            continue

        clone_evt = None
        api_evt = None
        for e in events:
            if e["event_type"] == "commit_clone":
                clone_evt = e
            elif e["event_type"] == "commit_api":
                api_evt = e

        if clone_evt is None:
            continue

        cp = clone_evt["payload"]

        author_login = None
        committer_login = None
        verified = False
        html_url = None
        sources = ["git_clone"]

        if api_evt:
            ap = api_evt["payload"]
            author_login = ap.get("author_login")
            committer_login = ap.get("committer_login")
            verified = ap.get("verified", False)
            html_url = ap.get("html_url")
            sources.append("github_api")
            both_sources += 1

            if author_login and cp.get("author_email"):
                alias_pairs.append((
                    cp["author_email"],
                    author_login,
                    cp.get("author_name", ""),
                ))
            if committer_login and cp.get("committer_email"):
                alias_pairs.append((
                    cp["committer_email"],
                    committer_login,
                    cp.get("committer_name", ""),
                ))
        else:
            clone_only += 1

        files_changed = classify_files_changed(cp.get("files_changed", []))
        cross_refs = collect_references(cp.get("message"))

        commit = {
            "type": "commit",
            "natural_key": f"commit:{cp['sha']}",
            "sha": cp["sha"],
            "parent_shas": cp.get("parent_shas", []),
            "message": cp.get("message", ""),
            "committed_at": cp["committed_at"],
            "timestamp": cp["committed_at"],
            "author": {
                "login": author_login,
                "email": cp.get("author_email", ""),
                "name": cp.get("author_name", ""),
            },
            "committer": {
                "login": committer_login,
                "email": cp.get("committer_email", ""),
                "name": cp.get("committer_name", ""),
            },
            "verified": verified,
            "html_url": html_url,
            "merge_commit_for_pr": None,
            "diff_available": True,
            "files_changed": files_changed,
            "cross_references": cross_refs,
            "sources": sources,
        }
        merged.append(commit)

    logger.info(
        "Merged %d commits (%d with API data, %d clone-only)",
        len(merged),
        both_sources,
        clone_only,
    )
    return merged, alias_pairs


def apply_pr_reverse_map(
    merged_commits: list[dict],
    merged_prs: list[dict],
) -> int:
    """Stamp merge_commit_for_pr on commits that are merge commits for PRs.

    Returns the number of commits updated.
    """
    sha_to_pr: dict[str, int] = {}
    for pr in merged_prs:
        sha = pr.get("merge_commit_sha")
        if sha:
            sha_to_pr[sha] = pr["number"]

    updated = 0
    for commit in merged_commits:
        pr_num = sha_to_pr.get(commit["sha"])
        if pr_num is not None:
            commit["merge_commit_for_pr"] = pr_num
            updated += 1

    logger.info("Stamped merge_commit_for_pr on %d commits", updated)
    return updated
