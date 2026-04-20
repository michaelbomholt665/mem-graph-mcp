from typing import Any, Optional
from ..db import db_get_connection
from ..ids import id_generate_v7

class GraphWriterService:
    def __init__(self, conn: Any = None):
        self.conn = conn or db_get_connection()

    def write_node(
        self,
        label: str,
        properties: dict[str, Any],
        parent_id: Optional[str] = None,
        parent_label: Optional[str] = None,
        relationship_name: str = "HAS_CHILD",
    ) -> str:
        """Write a node to the graph and return its ID."""
        node_id = properties.get("id") or id_generate_v7()
        properties["id"] = node_id
        
        props_str = ", ".join([f"{k}: ${k}" for k in properties.keys()])
        query = f"CREATE (n:{label} {{ {props_str} }})"
        self.conn.execute(query, properties)
        
        if parent_id and parent_label:
            self.write_relationship(parent_id, node_id, relationship_name, parent_label, label)
            
        return node_id

    def write_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_name: str,
        from_label: str = "Project",
        to_label: str = "Node",
        properties: Optional[dict[str, Any]] = None,
    ) -> None:
        """Write a relationship between two nodes."""
        query = f"""
        MATCH (a:{from_label} {{id: $from_id}}), (b:{to_label} {{id: $to_id}})
        CREATE (a)-[:{rel_name}]->(b)
        """
        params = {"from_id": from_id, "to_id": to_id}
        self.conn.execute(query, params)

