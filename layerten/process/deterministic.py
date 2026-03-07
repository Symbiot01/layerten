from __future__ import annotations

import logging
import os

from layerten.process.bootstrap import ReferenceData
from layerten.process.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

_HANDLER_MAP: dict = {}


def _person_key(person_dict: dict | None) -> str | None:
    """Resolve person natural key: prefer login, fall back to email."""
    if not person_dict:
        return None
    login = person_dict.get("login")
    if login:
        return f"person:{login}"
    email = person_dict.get("email")
    if email:
        return f"person:{email}"
    return None


def _person_props(person_dict: dict, ref_data: ReferenceData) -> dict:
    """Build person node properties, enriched from persons.json if available."""
    login = person_dict.get("login")
    if login and login in ref_data.persons:
        meta = ref_data.persons[login]
        return {
            "display_name": meta.get("display_name", person_dict.get("name", "")),
            "aliases": meta.get("aliases", []),
        }
    return {
        "display_name": person_dict.get("name", person_dict.get("email", "")),
        "aliases": [a for a in [person_dict.get("email"), person_dict.get("name")] if a],
    }


def _ensure_person(neo4j: Neo4jClient, ref_data: ReferenceData, login: str):
    """UPSERT a Person node by login, enriched from persons.json."""
    meta = ref_data.persons.get(login, {})
    neo4j.upsert_node(
        "Person",
        f"person:{login}",
        {
            "display_name": meta.get("display_name", login),
            "aliases": meta.get("aliases", [login]),
        },
    )


def _infer_language(path: str) -> str:
    ext_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".tsx": "TypeScript", ".jsx": "JavaScript", ".json": "JSON",
        ".md": "Markdown", ".yml": "YAML", ".yaml": "YAML",
        ".toml": "TOML", ".cfg": "Config", ".ini": "Config",
        ".sh": "Shell", ".bash": "Shell", ".html": "HTML",
        ".css": "CSS", ".sql": "SQL", ".rs": "Rust", ".go": "Go",
        ".rb": "Ruby", ".java": "Java", ".c": "C", ".cpp": "C++",
        ".h": "C", ".hpp": "C++",
    }
    _, ext = os.path.splitext(path)
    return ext_map.get(ext.lower(), "")


def _find_branch(branches: list, name: str) -> dict:
    for b in branches:
        if b.get("name") == name:
            return b
    return {}


def _find_label(labels: list, name: str) -> dict:
    for lb in labels:
        if lb.get("name") == name:
            return lb
    return {}


def _resolve_number(num: int | str, timeline_index: dict) -> str | None:
    """Resolve #N to pr:N or issue:N by checking which exists in timeline."""
    num_str = str(num)
    if f"issue:{num_str}" in timeline_index:
        return f"issue:{num_str}"
    if f"pr:{num_str}" in timeline_index:
        return f"pr:{num_str}"
    return None


def _process_cross_references(
    source_key: str, event: dict, ref_data: ReferenceData, neo4j: Neo4jClient
):
    """Process cross_references, resolving ambiguous #N to pr or issue."""
    for ref in event.get("cross_references", []):
        ref_type = ref.get("type")

        if ref_type == "closes":
            target = ref.get("target")
            if target:
                neo4j.upsert_relationship(
                    source_key, "CLOSES", target,
                    {"event_time_from": event.get("timestamp"), "confidence": 1.0},
                )

        elif ref_type == "mentions":
            num = ref.get("target_number")
            if num is not None:
                target_key = _resolve_number(num, ref_data.timeline_index)
                if target_key:
                    neo4j.upsert_relationship(
                        source_key, "REFERENCES", target_key,
                        {"event_time_from": event.get("timestamp"), "confidence": 0.9},
                    )

        elif ref_type == "mentions_person":
            person_key = ref.get("target")
            if person_key and neo4j.node_exists(person_key):
                neo4j.upsert_relationship(
                    source_key, "REFERENCES", person_key,
                    {"event_time_from": event.get("timestamp"), "confidence": 0.8},
                )


def process_commit(event: dict, ref_data: ReferenceData, neo4j: Neo4jClient):
    sha = event["sha"]
    nk = f"commit:{sha}"

    neo4j.upsert_node("Commit", nk, {
        "sha": sha,
        "message": event.get("message", ""),
        "parent_shas": event.get("parent_shas", []),
        "committed_at": event.get("committed_at"),
        "merge_commit_for_pr": event.get("merge_commit_for_pr"),
    })

    author = event.get("author")
    author_key = _person_key(author)
    if author_key:
        person_props = _person_props(author, ref_data)
        neo4j.upsert_node("Person", author_key, person_props)
        neo4j.upsert_relationship(
            nk, "AUTHORED_BY", author_key,
            {"event_time_from": event.get("committed_at"), "confidence": 1.0},
        )

    for fc in event.get("files_changed", []):
        path = fc.get("path")
        if not path:
            continue
        status = "active" if fc.get("status") != "D" else "deleted"
        neo4j.upsert_node("FileNode", f"file:{path}", {
            "path": path,
            "language": _infer_language(path),
            "status": status,
        })
        neo4j.upsert_relationship(
            nk, "MODIFIES", f"file:{path}",
            {
                "event_time_from": event.get("committed_at"),
                "confidence": 1.0,
                "change_type": fc.get("status"),
            },
        )

    for r in ref_data.renames.get(sha, []):
        old_path = r.get("old_path")
        new_path = r.get("new_path")
        if old_path and new_path:
            neo4j.upsert_node("FileNode", f"file:{old_path}", {
                "path": old_path, "status": "renamed",
            })
            neo4j.upsert_node("FileNode", f"file:{new_path}", {
                "path": new_path, "status": "active",
            })
            neo4j.upsert_relationship(
                f"file:{old_path}", "RENAMES", f"file:{new_path}",
                {"event_time_from": event.get("committed_at"), "confidence": 1.0},
            )

    _process_cross_references(nk, event, ref_data, neo4j)


def process_pr(event: dict, ref_data: ReferenceData, neo4j: Neo4jClient):
    num = event["number"]
    nk = f"pr:{num}"

    neo4j.upsert_node("PullRequest", nk, {
        "number": num,
        "title": event.get("title", ""),
        "body": event.get("body", ""),
        "state": event.get("state"),
        "created_at": event.get("created_at"),
        "merged_at": event.get("merged_at"),
        "closed_at": event.get("closed_at"),
        "merge_commit_sha": event.get("merge_commit_sha"),
        "base_branch": event.get("base_branch"),
        "head_branch": event.get("head_branch"),
        "additions": event.get("additions", 0),
        "deletions": event.get("deletions", 0),
    })

    author_login = event.get("author_login")
    if author_login:
        _ensure_person(neo4j, ref_data, author_login)
        neo4j.upsert_relationship(
            nk, "AUTHORED_BY", f"person:{author_login}",
            {"event_time_from": event.get("created_at"), "confidence": 1.0},
        )

    for branch_name in [event.get("base_branch"), event.get("head_branch")]:
        if branch_name:
            meta = _find_branch(ref_data.branches, branch_name)
            neo4j.upsert_node("Branch", f"branch:{branch_name}", {
                "name": branch_name,
                "status": meta.get("status", "unknown"),
                "protected": meta.get("protected", False),
            })

    seen_reviewers: set = set()
    for review in event.get("reviews", []):
        login = review.get("author_login")
        if login and login not in seen_reviewers:
            seen_reviewers.add(login)
            _ensure_person(neo4j, ref_data, login)
            neo4j.upsert_relationship(
                nk, "REVIEWED_BY", f"person:{login}",
                {
                    "event_time_from": review.get("created_at"),
                    "confidence": 1.0,
                    "review_state": review.get("state"),
                },
            )

    for label_name in event.get("labels", []):
        meta = _find_label(ref_data.labels, label_name)
        neo4j.upsert_node("Label", f"label:{label_name}", {
            "name": label_name,
            "color": meta.get("color", ""),
            "description": meta.get("description"),
        })

    for fc in event.get("files_changed", []):
        path = fc.get("path")
        if not path:
            continue
        neo4j.upsert_node("FileNode", f"file:{path}", {
            "path": path,
            "language": _infer_language(path),
            "status": "active",
        })
        neo4j.upsert_relationship(
            nk, "MODIFIES", f"file:{path}",
            {
                "event_time_from": event.get("created_at"),
                "confidence": 1.0,
                "change_type": fc.get("status"),
            },
        )

    _process_cross_references(nk, event, ref_data, neo4j)


def process_issue(event: dict, ref_data: ReferenceData, neo4j: Neo4jClient):
    num = event["number"]
    nk = f"issue:{num}"

    neo4j.upsert_node("Issue", nk, {
        "number": num,
        "title": event.get("title", ""),
        "body": event.get("body", ""),
        "state": event.get("state"),
        "created_at": event.get("created_at"),
        "closed_at": event.get("closed_at"),
    })

    author_login = event.get("author_login")
    if author_login:
        _ensure_person(neo4j, ref_data, author_login)
        neo4j.upsert_relationship(
            nk, "AUTHORED_BY", f"person:{author_login}",
            {"event_time_from": event.get("created_at"), "confidence": 1.0},
        )

    for label_name in event.get("labels", []):
        meta = _find_label(ref_data.labels, label_name)
        neo4j.upsert_node("Label", f"label:{label_name}", {
            "name": label_name,
            "color": meta.get("color", ""),
            "description": meta.get("description"),
        })

    _process_cross_references(nk, event, ref_data, neo4j)


def process_discussion(event: dict, ref_data: ReferenceData, neo4j: Neo4jClient):
    num = event["number"]
    nk = f"discussion:{num}"

    neo4j.upsert_node("Discussion", nk, {
        "number": num,
        "title": event.get("title", ""),
        "body": event.get("body", ""),
        "category": event.get("category"),
        "created_at": event.get("created_at"),
    })

    author_login = event.get("author_login")
    if author_login:
        _ensure_person(neo4j, ref_data, author_login)
        neo4j.upsert_relationship(
            nk, "AUTHORED_BY", f"person:{author_login}",
            {"event_time_from": event.get("created_at"), "confidence": 1.0},
        )

    _process_cross_references(nk, event, ref_data, neo4j)


def process_tag(event: dict, ref_data: ReferenceData, neo4j: Neo4jClient):
    name = event["name"]
    nk = f"tag:{name}"

    neo4j.upsert_node("Tag", nk, {
        "name": name,
        "commit_sha": event.get("commit_sha"),
        "release_name": event.get("release_name"),
        "release_body": event.get("release_body"),
        "published_at": event.get("published_at"),
    })

    author_login = event.get("author_login")
    if author_login:
        _ensure_person(neo4j, ref_data, author_login)
        neo4j.upsert_relationship(
            nk, "AUTHORED_BY", f"person:{author_login}",
            {"event_time_from": event.get("timestamp"), "confidence": 1.0},
        )

    commit_sha = event.get("commit_sha")
    if commit_sha:
        neo4j.upsert_relationship(
            nk, "REFERENCES", f"commit:{commit_sha}",
            {"event_time_from": event.get("timestamp"), "confidence": 1.0},
        )


_HANDLER_MAP = {
    "commit": process_commit,
    "pr": process_pr,
    "issue": process_issue,
    "discussion": process_discussion,
    "tag": process_tag,
}


def deterministic_extract(event: dict, ref_data: ReferenceData, neo4j: Neo4jClient):
    """Route event to the appropriate deterministic handler."""
    event_type = event.get("type")
    handler = _HANDLER_MAP.get(event_type)
    if handler:
        handler(event, ref_data, neo4j)
    else:
        logger.warning("Unknown event type: %s (key=%s)", event_type, event.get("natural_key"))
