// ---------------------------------------------------------------------------
// WorkGraph — handy Cypher queries for the Neo4j Browser (localhost:7474)
// Run `workgraph rank` first so n.prominence is populated.
// ---------------------------------------------------------------------------

// 1. The first useful query — what's prominent right now (from the SPEC)
MATCH (p:Person {self: true})-[e]->(n)
WHERE e.at > datetime() - duration('P30D')
RETURN n.title AS title, n.type AS type, sum(e.base_weight) AS prominence
ORDER BY prominence DESC
LIMIT 20;

// 2. Top nodes by computed WorkRank (decay-aware, written by `workgraph rank`)
MATCH (n) WHERE n.prominence IS NOT NULL
RETURN n.title, n.type, n.prominence
ORDER BY n.prominence DESC
LIMIT 20;

// 3. Orphaned knowledge — documents a departed person solely held
MATCH (n) WHERE n.orphaned_knowledge = true
RETURN n.title, n.type, n.prominence;

// 4. Your week ahead — upcoming meetings (these get the future_boost)
MATCH (p:Person {self: true})-[e:ATTENDED]->(m:Meeting)
WHERE e.at >= datetime()
RETURN m.title, e.at
ORDER BY e.at ASC;

// 5. The neighbourhood of the single most prominent node (good for the viz)
MATCH (n) WHERE n.prominence IS NOT NULL
WITH n ORDER BY n.prominence DESC LIMIT 1
MATCH path = (n)<-[r]-(p:Person)
RETURN path;

// 6. Who else touches the things you touch (collaboration surface)
MATCH (me:Person {self: true})-->(n)<--(other:Person)
WHERE other.id <> me.id
RETURN other.id AS person, count(DISTINCT n) AS shared_entities
ORDER BY shared_entities DESC;
