from __future__ import annotations

import re

ALLOWED_LABELS = frozenset({
    "Repository", "Person", "FileNode", "Component", "Commit", "Branch",
    "PullRequest", "Issue", "Discussion", "Review", "Label",
    "DesignDecision", "Tag", "Evidence",
})

ALLOWED_PREDICATES = frozenset({
    "MODIFIES", "CLOSES", "REFERENCES", "AUTHORED_BY", "REVIEWED_BY",
    "ASSIGNED_TO", "INTRODUCES", "REVERTS", "DEPRECATES", "DEPENDS_ON",
    "BELONGS_TO", "DECISION_FOR", "SUPERSEDES", "RENAMES", "MERGED_INTO",
    "CHERRY_PICKED_FROM", "REBASE_OF", "ON_BRANCH", "STATE_CHANGED_TO",
})

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DROP|CALL|LOAD)\b", re.IGNORECASE
)


class ValidationError(Exception):
    pass


def validate_label(label: str):
    if label not in ALLOWED_LABELS:
        raise ValidationError(f"Label '{label}' not in allowed labels: {ALLOWED_LABELS}")


def validate_predicate(predicate: str):
    if predicate not in ALLOWED_PREDICATES:
        raise ValidationError(
            f"Predicate '{predicate}' not in allowed predicates: {ALLOWED_PREDICATES}"
        )


def validate_evidence(evidence: dict | None):
    if not evidence:
        raise ValidationError("Evidence is required for every write operation")
    if not evidence.get("excerpt"):
        raise ValidationError("Evidence must include a non-empty 'excerpt'")


def validate_confidence(confidence: float | None):
    if confidence is None:
        return
    if not (0.0 <= confidence <= 1.0):
        raise ValidationError(f"Confidence must be 0.0-1.0, got {confidence}")
    if confidence < 0.4:
        raise ValidationError(
            f"Confidence {confidence} is below 0.4 threshold — claim rejected"
        )


def validate_read_only_cypher(cypher: str):
    """Ensure the Cypher query is read-only (no mutations)."""
    if _WRITE_KEYWORDS.search(cypher):
        raise ValidationError(
            f"Query contains write keywords. Only MATCH/RETURN queries allowed. "
            f"Got: {cypher[:200]}"
        )
