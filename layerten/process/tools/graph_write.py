from __future__ import annotations

import logging

from layerten.process.neo4j_client import Neo4jClient
from layerten.process.tools.validator import (
    ValidationError,
    validate_confidence,
    validate_evidence,
    validate_label,
    validate_predicate,
)

logger = logging.getLogger(__name__)


def write_node(
    label: str,
    natural_key: str,
    properties: dict,
    evidence: dict,
    neo4j: Neo4jClient,
) -> dict:
    """Create or update an entity node with evidence."""
    try:
        validate_label(label)
        validate_evidence(evidence)
        validate_confidence(properties.get("confidence"))
    except ValidationError as e:
        return {"error": str(e)}

    props = dict(properties)
    props["evidence_excerpt"] = evidence.get("excerpt", "")
    props["evidence_source"] = evidence.get("source", "")

    try:
        neo4j.upsert_node(label, natural_key, props)
        return {"status": "ok", "action": "upserted", "natural_key": natural_key}
    except Exception as e:
        return {"error": f"Failed to write node: {e}"}


def write_relationship(
    subject_key: str,
    predicate: str,
    object_key: str,
    properties: dict,
    evidence: dict,
    neo4j: Neo4jClient,
) -> dict:
    """Create a relationship between two existing nodes with evidence."""
    try:
        validate_predicate(predicate)
        validate_evidence(evidence)
        validate_confidence(properties.get("confidence"))
    except ValidationError as e:
        return {"error": str(e)}

    props = dict(properties)
    props["evidence_excerpt"] = evidence.get("excerpt", "")
    props["evidence_source"] = evidence.get("source", "")

    try:
        neo4j.upsert_relationship(subject_key, predicate, object_key, props)
        return {
            "status": "ok",
            "action": "created",
            "subject": subject_key,
            "predicate": predicate,
            "object": object_key,
        }
    except Exception as e:
        return {"error": f"Failed to write relationship: {e}"}


def update_node(
    natural_key: str,
    updates: dict,
    evidence: dict,
    neo4j: Neo4jClient,
) -> dict:
    """Update properties on an existing node."""
    try:
        validate_evidence(evidence)
    except ValidationError as e:
        return {"error": str(e)}

    updates["evidence_excerpt"] = evidence.get("excerpt", "")

    try:
        query = """
        MATCH (n {natural_key: $nk})
        SET n += $props, n.updated_at = datetime()
        """
        neo4j.run(query, nk=natural_key, props=updates)
        return {"status": "ok", "natural_key": natural_key}
    except Exception as e:
        return {"error": f"Failed to update node: {e}"}


def supersede_claim(
    old_claim_key: str,
    new_claim: dict,
    reason: str,
    evidence: dict,
    neo4j: Neo4jClient,
) -> dict:
    """Mark an old claim as superseded and create a new one."""
    try:
        validate_evidence(evidence)
    except ValidationError as e:
        return {"error": str(e)}

    try:
        neo4j.run(
            """
            MATCH (n {natural_key: $key})
            SET n.is_current = false,
                n.superseded_reason = $reason,
                n.updated_at = datetime()
            """,
            key=old_claim_key,
            reason=reason,
        )

        if new_claim.get("label") and new_claim.get("natural_key"):
            props = new_claim.get("properties", {})
            props["is_current"] = True
            props["supersedes"] = old_claim_key
            props["evidence_excerpt"] = evidence.get("excerpt", "")
            neo4j.upsert_node(new_claim["label"], new_claim["natural_key"], props)

            neo4j.upsert_relationship(
                new_claim["natural_key"],
                "SUPERSEDES",
                old_claim_key,
                {"reason": reason, "evidence_excerpt": evidence.get("excerpt", "")},
            )

        return {"status": "ok", "old": old_claim_key, "new": new_claim.get("natural_key")}
    except Exception as e:
        return {"error": f"Failed to supersede claim: {e}"}
