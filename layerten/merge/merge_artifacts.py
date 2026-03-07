"""Merge PRs, issues, discussions, tags+releases, branches, labels, renames, file_tree."""

from __future__ import annotations

import logging

from layerten.merge.classify import classify_files_changed
from layerten.merge.references import collect_references

logger = logging.getLogger(__name__)


def _safe_login(author_dict: dict | None) -> str | None:
    if author_dict and isinstance(author_dict, dict):
        return author_dict.get("login")
    return None


def _flatten_label_nodes(labels: dict | None) -> list[str]:
    if not labels:
        return []
    return [n["name"] for n in (labels.get("nodes") or []) if n.get("name")]


def _flatten_assignee_nodes(assignees: dict | None) -> list[str]:
    if not assignees:
        return []
    return [n["login"] for n in (assignees.get("nodes") or []) if n.get("login")]


def _flatten_reviews(reviews_conn: dict | None) -> list[dict]:
    if not reviews_conn:
        return []
    out = []
    for r in reviews_conn.get("nodes") or []:
        inline_comments = []
        for c in (r.get("comments") or {}).get("nodes") or []:
            inline_comments.append({
                "body": c.get("body", ""),
                "path": c.get("path"),
                "line": c.get("line"),
                "created_at": c.get("createdAt"),
                "author_login": _safe_login(c.get("author")),
            })
        out.append({
            "id": r.get("id"),
            "state": r.get("state"),
            "body": r.get("body", ""),
            "created_at": r.get("createdAt"),
            "author_login": _safe_login(r.get("author")),
            "inline_comments": inline_comments,
        })
    return out


def _flatten_comments(comments_conn: dict | None) -> list[dict]:
    if not comments_conn:
        return []
    out = []
    for c in comments_conn.get("nodes") or []:
        out.append({
            "id": c.get("id"),
            "body": c.get("body", ""),
            "created_at": c.get("createdAt"),
            "author_login": _safe_login(c.get("author")),
        })
    return out


def _flatten_timeline(timeline_conn: dict | None) -> list[dict]:
    if not timeline_conn:
        return []
    out = []
    for node in timeline_conn.get("nodes") or []:
        typename = node.get("__typename", "")
        item = {"type": typename}
        if typename == "ClosedEvent":
            item["at"] = node.get("createdAt")
            item["actor"] = _safe_login(node.get("actor"))
        elif typename == "MergedEvent":
            item["at"] = node.get("createdAt")
            item["actor"] = _safe_login(node.get("actor"))
            item["commit_sha"] = (node.get("commit") or {}).get("oid")
        elif typename == "LabeledEvent":
            item["at"] = node.get("createdAt")
            item["label"] = (node.get("label") or {}).get("name")
            item["actor"] = _safe_login(node.get("actor"))
        elif typename == "UnlabeledEvent":
            item["at"] = node.get("createdAt")
            item["label"] = (node.get("label") or {}).get("name")
            item["actor"] = _safe_login(node.get("actor"))
        elif typename == "AssignedEvent":
            item["at"] = node.get("createdAt")
            item["assignee"] = _safe_login(node.get("assignee"))
            item["actor"] = _safe_login(node.get("actor"))
        elif typename == "CrossReferencedEvent":
            item["at"] = node.get("createdAt")
            item["actor"] = _safe_login(node.get("actor"))
            source = node.get("source") or {}
            item["source_number"] = source.get("number")
            item["source_title"] = source.get("title")
        elif typename == "RenamedTitleEvent":
            item["at"] = node.get("createdAt")
            item["previous_title"] = node.get("previousTitle")
            item["current_title"] = node.get("currentTitle")
            item["actor"] = _safe_login(node.get("actor"))
        else:
            item["raw"] = node
        out.append(item)
    return out


def _collect_pr_text_fields(pr: dict) -> list[str | None]:
    """Gather all text fields from a PR for cross-reference parsing."""
    texts: list[str | None] = [pr.get("body")]
    for c in pr.get("comments", []):
        texts.append(c.get("body"))
    for r in pr.get("reviews", []):
        texts.append(r.get("body"))
        for ic in r.get("inline_comments", []):
            texts.append(ic.get("body"))
    return texts


def merge_all_prs(
    groups: dict[str, list[dict]],
    commits_by_sha: dict[str, dict],
) -> list[dict]:
    """Merge PR events, enriching with files_changed from merge commits."""
    merged = []
    for key, events in groups.items():
        if not key.startswith("pr:"):
            continue
        p = events[0]["payload"]

        merge_sha = None
        mc = p.get("mergeCommit")
        if mc:
            merge_sha = mc.get("oid")

        files_changed: list[dict] = []
        if merge_sha and merge_sha in commits_by_sha:
            files_changed = list(commits_by_sha[merge_sha].get("files_changed", []))

        reviews = _flatten_reviews(p.get("reviews"))
        comments = _flatten_comments(p.get("comments"))
        timeline_events = _flatten_timeline(p.get("timelineItems"))

        pr: dict = {
            "type": "pr",
            "natural_key": f"pr:{p['number']}",
            "number": p["number"],
            "title": p.get("title", ""),
            "body": p.get("body", ""),
            "state": p.get("state", ""),
            "author_login": _safe_login(p.get("author")),
            "created_at": p.get("createdAt"),
            "merged_at": p.get("mergedAt"),
            "closed_at": p.get("closedAt"),
            "base_branch": p.get("baseRefName"),
            "head_branch": p.get("headRefName"),
            "merge_commit_sha": merge_sha,
            "additions": p.get("additions", 0),
            "deletions": p.get("deletions", 0),
            "changed_files_count": p.get("changedFiles", 0),
            "files_changed": files_changed,
            "labels": _flatten_label_nodes(p.get("labels")),
            "assignees": _flatten_assignee_nodes(p.get("assignees")),
            "reviews": reviews,
            "comments": comments,
            "timeline_events": timeline_events,
            "timestamp": p.get("createdAt"),
            "sources": ["github_api"] + (["git_clone"] if files_changed else []),
        }

        pr["cross_references"] = collect_references(*_collect_pr_text_fields(pr))
        merged.append(pr)

    logger.info("Merged %d PRs", len(merged))
    return merged


def merge_all_issues(groups: dict[str, list[dict]]) -> list[dict]:
    """Merge issue events."""
    merged = []
    for key, events in groups.items():
        if not key.startswith("issue:"):
            continue
        p = events[0]["payload"]
        comments = _flatten_comments(p.get("comments"))
        timeline_events = _flatten_timeline(p.get("timelineItems"))

        text_fields = [p.get("body")]
        for c in comments:
            text_fields.append(c.get("body"))

        issue = {
            "type": "issue",
            "natural_key": f"issue:{p['number']}",
            "number": p["number"],
            "title": p.get("title", ""),
            "body": p.get("body", ""),
            "state": p.get("state", ""),
            "author_login": _safe_login(p.get("author")),
            "created_at": p.get("createdAt"),
            "closed_at": p.get("closedAt"),
            "labels": _flatten_label_nodes(p.get("labels")),
            "assignees": _flatten_assignee_nodes(p.get("assignees")),
            "comments": comments,
            "timeline_events": timeline_events,
            "cross_references": collect_references(*text_fields),
            "timestamp": p.get("createdAt"),
            "sources": ["github_api"],
        }
        merged.append(issue)

    logger.info("Merged %d issues", len(merged))
    return merged


def merge_all_discussions(groups: dict[str, list[dict]]) -> list[dict]:
    """Merge discussion events."""
    merged = []
    for key, events in groups.items():
        if not key.startswith("discussion:"):
            continue
        p = events[0]["payload"]

        comments = []
        text_fields: list[str | None] = [p.get("body")]
        for c in (p.get("comments") or {}).get("nodes") or []:
            replies = []
            for r in (c.get("replies") or {}).get("nodes") or []:
                replies.append({
                    "id": r.get("id"),
                    "body": r.get("body", ""),
                    "created_at": r.get("createdAt"),
                    "author_login": _safe_login(r.get("author")),
                })
                text_fields.append(r.get("body"))

            comments.append({
                "id": c.get("id"),
                "body": c.get("body", ""),
                "created_at": c.get("createdAt"),
                "author_login": _safe_login(c.get("author")),
                "replies": replies,
            })
            text_fields.append(c.get("body"))

        discussion = {
            "type": "discussion",
            "natural_key": f"discussion:{p['number']}",
            "number": p["number"],
            "title": p.get("title", ""),
            "body": p.get("body", ""),
            "author_login": _safe_login(p.get("author")),
            "category": (p.get("category") or {}).get("name"),
            "created_at": p.get("createdAt"),
            "labels": _flatten_label_nodes(p.get("labels")),
            "comments": comments,
            "cross_references": collect_references(*text_fields),
            "timestamp": p.get("createdAt"),
            "sources": ["github_api"],
        }
        merged.append(discussion)

    logger.info("Merged %d discussions", len(merged))
    return merged


def merge_all_tags(
    groups: dict[str, list[dict]],
    commits_by_sha: dict[str, dict],
) -> list[dict]:
    """Merge tags with releases (joined by tag name), resolve timestamp from commit."""
    merged = []
    for key, events in groups.items():
        if not key.startswith("tag:"):
            continue

        tag_evt = None
        release_evt = None
        for e in events:
            if e["event_type"] == "tag":
                tag_evt = e
            elif e["event_type"] == "release":
                release_evt = e

        if tag_evt is None and release_evt is None:
            continue

        tag_payload = tag_evt["payload"] if tag_evt else {}
        release_payload = release_evt["payload"] if release_evt else {}

        name = tag_payload.get("name") or release_payload.get("tag_name", "")
        commit_sha = tag_payload.get("commit_sha", "")

        timestamp = release_payload.get("published_at")
        if not timestamp and commit_sha and commit_sha in commits_by_sha:
            timestamp = commits_by_sha[commit_sha].get("committed_at")

        sources = []
        if tag_evt:
            sources.append("git_clone")
        if release_evt:
            sources.append("github_api")

        tag = {
            "type": "tag",
            "natural_key": f"tag:{name}",
            "name": name,
            "commit_sha": commit_sha,
            "timestamp": timestamp,
            "release_name": release_payload.get("name"),
            "release_body": release_payload.get("body"),
            "author_login": release_payload.get("author_login"),
            "published_at": release_payload.get("published_at"),
            "html_url": release_payload.get("html_url"),
            "sources": sources,
        }
        merged.append(tag)

    logger.info("Merged %d tags (with release data where available)", len(merged))
    return merged


def merge_all_branches(
    groups: dict[str, list[dict]],
    merged_prs: list[dict],
) -> list[dict]:
    """Build branch catalog: active branches + ghost branches from PRs."""
    branches: dict[str, dict] = {}

    for key, events in groups.items():
        if not key.startswith("branch:"):
            continue
        p = events[0]["payload"]
        branches[p["name"]] = {
            "name": p["name"],
            "commit_sha": p.get("commit_sha"),
            "protected": p.get("protected", False),
            "status": "active",
            "discovered_from": None,
            "merged_into": None,
        }

    ghost_count = 0
    for pr in merged_prs:
        head = pr.get("head_branch")
        if head and head not in branches:
            branches[head] = {
                "name": head,
                "commit_sha": None,
                "protected": False,
                "status": "deleted",
                "discovered_from": f"pr:{pr['number']}",
                "merged_into": pr.get("base_branch") if pr.get("state") == "MERGED" else None,
            }
            ghost_count += 1

    logger.info(
        "Built branch catalog: %d active + %d ghost = %d total",
        len(branches) - ghost_count,
        ghost_count,
        len(branches),
    )
    return list(branches.values())


def merge_all_labels(groups: dict[str, list[dict]]) -> list[dict]:
    """Pass through label definitions."""
    labels = []
    for key, events in groups.items():
        if not key.startswith("label:"):
            continue
        p = events[0]["payload"]
        labels.append({
            "name": p["name"],
            "color": p.get("color", ""),
            "description": p.get("description"),
        })
    logger.info("Collected %d labels", len(labels))
    return labels


def build_renames_index(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Transform flat rename list into {commit_sha: [{old_path, new_path, committed_at}]}."""
    rename_events = groups.get("rename:all", [])
    if not rename_events:
        return {}

    renames_list = rename_events[0]["payload"].get("renames", [])
    index: dict[str, list[dict]] = {}
    for r in renames_list:
        sha = r["commit_sha"]
        index.setdefault(sha, []).append({
            "old_path": r["old_path"],
            "new_path": r["new_path"],
            "committed_at": r.get("committed_at"),
        })

    logger.info(
        "Indexed %d renames across %d commits",
        len(renames_list),
        len(index),
    )
    return index


def extract_file_tree(groups: dict[str, list[dict]]) -> dict:
    """Extract file tree at HEAD."""
    ft_events = groups.get("file_tree:HEAD", [])
    if not ft_events:
        return {"ref": "HEAD", "files": []}
    p = ft_events[0]["payload"]
    files = p.get("files", [])
    logger.info("File tree at HEAD: %d files", len(files))
    return {"ref": p.get("ref", "HEAD"), "files": files}
