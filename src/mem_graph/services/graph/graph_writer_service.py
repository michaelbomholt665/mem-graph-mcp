#!/usr/bin/env python3
# src/mem_graph/services/graph/graph_writer_service.py
"""
GraphWriterService — Shared write operations for the knowledge graph.

Provides high-level abstractions for creating nodes and relationships,
ensuring consistent patterns for IDs, timestamps, and project linkage.
Reduces boilerplate in domain-specific writers (reports, violations).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ...db import db_get_connection
from ...ids import id_generate_v7

logger = logging.getLogger(__name__)


class GraphWriterService:
    """
    Service for executing write operations on the knowledge graph.

    Encapsulates common patterns like node creation, relationship linking,
    and parent-child hierarchy writes.
    """

    def __init__(self, conn: Any = None) -> None:
        """
        Initialise with an optional connection.

        Args:
            conn: Active Ladybug connection. If None, uses db_get_connection().
        """
        self.conn = conn or db_get_connection()

    def write_node(
        self,
        label: str,
        properties: dict[str, Any],
        parent_id: str | None = None,
        parent_label: str | None = None,
        relationship_name: str | None = None,
    ) -> str:
        """
        Write a node to the graph and optionally link it to a parent.

        If 'id' is not in properties, a new UUIDv7 is generated.
        If 'created_at' is not in properties, current UTC time is added.

        Args:
            label: The node label (e.g. 'Note', 'Violation').
            properties: Dictionary of properties to set on the node.
            parent_id: Optional ID of a parent node to link to.
            parent_label: Optional label of the parent node.
            relationship_name: Optional relationship type (e.g. 'HAS_NOTE').

        Returns:
            The ID of the created node.
        """
        node_id = properties.get("id") or id_generate_v7()
        props = properties.copy()
        props["id"] = node_id

        if "created_at" not in props and "detected_at" not in props:
            props["created_at"] = datetime.now(timezone.utc)

        # Build Cypher CREATE statement
        keys = list(props.keys())
        keys_str = ", ".join(f"{k}: ${k}" for k in keys)
        query = f"CREATE (n:{label} {{{keys_str}}})"

        try:
            self.conn.execute(query, props)  # nosemgrep

            if parent_id and parent_label and relationship_name:
                self.write_relationship(
                    parent_id, parent_label, node_id, label, relationship_name
                )

            return node_id
        except Exception as exc:
            logger.error("Failed to write node %s: %s", label, exc)
            raise

    def write_relationship(
        self,
        from_id: str,
        from_label: str,
        to_id: str,
        to_label: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """
        Write a relationship between two existing nodes.

        Args:
            from_id: ID of the source node.
            from_label: Label of the source node.
            to_id: ID of the target node.
            to_label: Label of the target node.
            rel_type: The relationship type (e.g. 'HAS_NOTE').
            properties: Optional properties for the relationship.
        """
        props = properties or {}
        if "assigned_at" not in props:
            props["assigned_at"] = datetime.now(timezone.utc)

        keys = list(props.keys())
        keys_str = ", ".join(f"{k}: ${k}" for k in keys)
        props["from_id"] = from_id
        props["to_id"] = to_id

        query = (
            f"MATCH (f:{from_label} {{id: $from_id}}), (t:{to_label} {{id: $to_id}}) "
            f"CREATE (f)-[r:{rel_type} {{{keys_str}}}]->(t)"
        )

        try:
            self.conn.execute(query, props)  # nosemgrep
        except Exception as exc:
            logger.error("Failed to write relationship %s: %s", rel_type, exc)
            raise

    def write_parent_child(
        self,
        parent_id: str,
        parent_label: str,
        child_label: str,
        child_properties: dict[str, Any],
        rel_type: str = "HAS_CHILD",
    ) -> str:
        """
        Create a child node and link it to a parent in one operation.

        Args:
            parent_id: ID of the parent node.
            parent_label: Label of the parent node.
            child_label: Label for the new child node.
            child_properties: Properties for the child node.
            rel_type: Relationship type from parent to child.

        Returns:
            The ID of the created child node.
        """
        return self.write_node(
            child_label,
            child_properties,
            parent_id=parent_id,
            parent_label=parent_label,
            relationship_name=rel_type,
        )
