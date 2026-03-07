from __future__ import annotations

SYSTEM_PROMPT = """You are a knowledge graph extraction agent analyzing GitHub repository events for the 567-labs/instructor project.

Your job is to identify and extract **design decisions, components, and semantic relationships** from event text that go beyond what deterministic extraction can capture.

The deterministic layer has already created structural nodes (Commit, PR, Issue, Discussion, Tag, Person, FileNode, Branch, Label) and structural relationships (AUTHORED_BY, MODIFIES, REVIEWED_BY, CLOSES, REFERENCES, RENAMES). You should NOT recreate these.

Your focus is on extracting:
- DesignDecision nodes: architectural choices, migration decisions, API changes
- Component nodes: logical software components (e.g., "retry system", "validation layer")
- Semantic relationships: SUPERSEDES, REVERTS, DEPRECATES, DEPENDS_ON, BELONGS_TO, INTRODUCES, DECISION_FOR

## HARD RULES

1. EVIDENCE REQUIREMENT: Every claim MUST have evidence with an exact excerpt from the event text. If you cannot find supporting text, do not create the claim.

2. SCHEMA COMPLIANCE: Only use allowed labels and predicates. Do not invent new types.
   Allowed labels: Person, FileNode, Component, Commit, Branch, PullRequest, Issue, Discussion, Review, Label, DesignDecision, Tag
   Allowed predicates: MODIFIES, CLOSES, REFERENCES, AUTHORED_BY, REVIEWED_BY, ASSIGNED_TO, INTRODUCES, REVERTS, DEPRECATES, DEPENDS_ON, BELONGS_TO, DECISION_FOR, SUPERSEDES, RENAMES, MERGED_INTO, CHERRY_PICKED_FROM, REBASE_OF, ON_BRANCH, STATE_CHANGED_TO

3. TEMPORAL VALIDITY: Every claim must have event_time_from set to the current event's timestamp.

4. IDEMPOTENCY: Always use natural_key for nodes. Use query_graph() to check before creating duplicates.

5. CONFIDENCE CALIBRATION:
   - 1.0 = explicitly stated in structured data
   - 0.8-0.9 = explicitly stated in natural text
   - 0.6-0.8 = strongly implied
   - 0.4-0.6 = inferred from context
   - below 0.4 = do not create the claim

6. DEDUP BEFORE CREATE: Before creating a DesignDecision, always query_graph() to check if a similar decision already exists. If it does, add evidence to the existing one or create a SUPERSEDES relationship.

7. COMPONENT INFERENCE: Only create Component nodes when there is strong evidence from multiple sources. Never infer from a single commit.

8. DO NOT OVER-EXTRACT: Not every PR contains a design decision. Most are routine changes. Only extract when there is explicit rationale, alternative consideration, or architectural choice stated in the text. If nothing meaningful to extract, simply respond with text saying so — do not force tool calls.

## EXTRACTION PATTERNS

Look for these patterns in event text:
- "We decided to..." / "Going with X because..." → DesignDecision + INTRODUCES
- "This replaces..." / "Instead of the old approach..." → SUPERSEDES
- "Reverts #123" / "Undoes the change from..." → REVERTS
- "Deprecating X" / "No longer used" → DEPRECATES
- File import patterns in diffs → DEPENDS_ON between FileNodes
- Module/component mentions → BELONGS_TO Component
- Architectural rationale → DesignDecision with alternatives_considered

## TOOLS AVAILABLE

- read_diff(sha, path): Get untruncated diff for a commit
- read_codebase(path, ref): Read file at any commit
- query_graph(cypher): Read-only Cypher query against current graph
- get_event(key): Get full event data by natural_key
- get_related_events(key, types): Find related events
- write_node(label, natural_key, properties, evidence): Create/update entity
- write_relationship(subject_key, predicate, object_key, properties, evidence): Create relationship
- update_node(natural_key, updates, evidence): Update entity properties
- supersede_claim(old_claim_key, new_claim, reason, evidence): Mark old claim as superseded
"""


def format_event_prompt(event: dict) -> str:
    """Format an event into a prompt for the agent."""
    event_type = event.get("type", "unknown")
    nk = event.get("natural_key", "")
    timestamp = event.get("timestamp", "")

    parts = [
        f"## Event: {event_type} — {nk}",
        f"**Timestamp**: {timestamp}",
    ]

    if event_type == "commit":
        parts.append(f"**SHA**: {event.get('sha', '')}")
        parts.append(f"**Message**: {event.get('message', '')}")
        author = event.get("author", {})
        parts.append(f"**Author**: {author.get('login', author.get('email', ''))}")
        files = event.get("files_changed", [])
        if files:
            file_list = ", ".join(f.get("path", "") for f in files[:20])
            parts.append(f"**Files changed** ({len(files)}): {file_list}")
        xrefs = event.get("cross_references", [])
        if xrefs:
            parts.append(f"**Cross-references**: {xrefs}")
        parts.append(f"**Merge commit for PR**: {event.get('merge_commit_for_pr')}")

    elif event_type == "pr":
        parts.append(f"**Number**: #{event.get('number')}")
        parts.append(f"**Title**: {event.get('title', '')}")
        body = event.get("body", "") or ""
        if len(body) > 3000:
            body = body[:3000] + "... (truncated)"
        parts.append(f"**Body**:\n{body}")
        parts.append(f"**State**: {event.get('state')}")
        parts.append(f"**Author**: {event.get('author_login', '')}")
        parts.append(f"**Base**: {event.get('base_branch')} ← **Head**: {event.get('head_branch')}")
        parts.append(f"**Additions**: {event.get('additions', 0)}, **Deletions**: {event.get('deletions', 0)}")

        reviews = event.get("reviews", [])
        if reviews:
            review_summary = "; ".join(
                f"{r.get('author_login')}: {r.get('state')}" for r in reviews[:10]
            )
            parts.append(f"**Reviews**: {review_summary}")

        comments = event.get("comments", [])
        if comments:
            for c in comments[:5]:
                c_body = (c.get("body", "") or "")[:500]
                parts.append(f"**Comment by {c.get('author_login', '?')}**: {c_body}")

        files = event.get("files_changed", [])
        if files:
            file_list = ", ".join(f.get("path", "") for f in files[:30])
            parts.append(f"**Files changed** ({len(files)}): {file_list}")

    elif event_type == "issue":
        parts.append(f"**Number**: #{event.get('number')}")
        parts.append(f"**Title**: {event.get('title', '')}")
        body = event.get("body", "") or ""
        if len(body) > 3000:
            body = body[:3000] + "... (truncated)"
        parts.append(f"**Body**:\n{body}")
        parts.append(f"**State**: {event.get('state')}")
        parts.append(f"**Author**: {event.get('author_login', '')}")

        comments = event.get("comments", [])
        if comments:
            for c in comments[:5]:
                c_body = (c.get("body", "") or "")[:500]
                parts.append(f"**Comment by {c.get('author_login', '?')}**: {c_body}")

    elif event_type == "discussion":
        parts.append(f"**Number**: #{event.get('number')}")
        parts.append(f"**Title**: {event.get('title', '')}")
        body = event.get("body", "") or ""
        if len(body) > 3000:
            body = body[:3000] + "... (truncated)"
        parts.append(f"**Body**:\n{body}")
        parts.append(f"**Category**: {event.get('category')}")
        parts.append(f"**Author**: {event.get('author_login', '')}")

        replies = event.get("replies", [])
        if replies:
            for r in replies[:5]:
                r_body = (r.get("body", "") or "")[:500]
                parts.append(f"**Reply by {r.get('author_login', '?')}**: {r_body}")

    elif event_type == "tag":
        parts.append(f"**Name**: {event.get('name', '')}")
        parts.append(f"**Commit SHA**: {event.get('commit_sha', '')}")
        release_body = event.get("release_body", "") or ""
        if len(release_body) > 3000:
            release_body = release_body[:3000] + "... (truncated)"
        if release_body:
            parts.append(f"**Release notes**:\n{release_body}")

    return "\n".join(parts)
