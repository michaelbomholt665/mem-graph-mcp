-- Sample SQL queries for tree-sitter validation

SELECT
    u.id,
    u.email,
    u.created_at,
    p.name AS plan_name
FROM users u
JOIN plans p ON p.id = u.plan_id
WHERE u.active = true
  AND u.created_at > '2024-01-01'
ORDER BY u.created_at DESC
LIMIT 100;

WITH ranked_orders AS (
    SELECT
        o.user_id,
        o.total,
        ROW_NUMBER() OVER (PARTITION BY o.user_id ORDER BY o.total DESC) AS rn
    FROM orders o
    WHERE o.status = 'completed'
),
top_orders AS (
    SELECT user_id, total
    FROM ranked_orders
    WHERE rn = 1
)
SELECT u.email, t.total
FROM users u
JOIN top_orders t ON t.user_id = u.id;

INSERT INTO events (user_id, event_type, payload, created_at)
VALUES ($1, $2, $3::jsonb, NOW());

UPDATE users
SET updated_at = NOW(),
    plan_id = $1
WHERE id = $2;

DELETE FROM sessions
WHERE expires_at < NOW();

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    table_name  TEXT NOT NULL,
    operation   TEXT NOT NULL,
    row_id      BIGINT,
    changed_at  TIMESTAMPTZ DEFAULT NOW()
);

SELECT
    count(*) AS total,
    sum(total) AS revenue,
    avg(total) AS avg_order
FROM orders
WHERE created_at BETWEEN $1 AND $2
GROUP BY DATE_TRUNC('day', created_at)
HAVING count(*) > 10;
