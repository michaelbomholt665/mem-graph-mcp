// Sample Cypher queries for tree-sitter validation

MATCH (p:Person {name: $name})-[:KNOWS]->(friend:Person)
WHERE friend.age > 25
RETURN friend.name, friend.age
ORDER BY friend.age DESC
LIMIT 10;

MATCH (u:User)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
WHERE o.created_at > $since
WITH u, count(o) AS order_count, sum(p.price) AS total_spent
WHERE order_count > 3
RETURN u.id, u.email, order_count, total_spent
ORDER BY total_spent DESC;

MERGE (p:Person {id: $id})
ON CREATE SET p.name = $name, p.created_at = timestamp()
ON MATCH SET p.updated_at = timestamp()
RETURN p;

CREATE (n:Node {name: $name, value: $value})
RETURN n.name AS name, id(n) AS node_id;

MATCH (a:Person), (b:Person)
WHERE a.name = $from AND b.name = $to
CREATE (a)-[r:KNOWS {since: $since}]->(b)
RETURN r;

MATCH (n:Person)
WHERE n.name STARTS WITH $prefix
DELETE n;

CALL {
  MATCH (p:Product)-[:IN_CATEGORY]->(c:Category)
  RETURN p, c
}
WITH p, c
RETURN p.name, c.name;

UNWIND $items AS item
MERGE (n:Item {id: item.id})
SET n.name = item.name
RETURN count(n) AS updated;
