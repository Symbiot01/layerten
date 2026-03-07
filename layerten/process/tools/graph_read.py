from __future__ import annotations

import logging

from layerten.process.neo4j_client import Neo4jClient
from layerten.process.tools.validator import ValidationError, validate_read_only_cypher

logger = logging.getLogger(__name__)


def query_graph(cypher: str, neo4j: Neo4jClient) -> dict:
    """Execute a read-only Cypher query against the knowledge graph."""
    try:
        validate_read_only_cypher(cypher)
    except ValidationError as e:
        return {"error": str(e)}

    try:
        results = neo4j.read_query(cypher)
        if len(results) > 100:
            results = results[:100]
            return {"results": results, "truncated": True, "total": ">100"}
        return {"results": results}
    except Exception as e:
        return {"error": f"Cypher execution failed: {e}"}
