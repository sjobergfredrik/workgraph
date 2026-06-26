.PHONY: up down test install seed rank logs shell

up:           ## Start Neo4j + workgraph containers
	docker compose up -d

down:         ## Stop containers
	docker compose down

install:      ## Local dev install (editable) + test deps
	pip install -e ".[dev]"

test:         ## Run unit tests (no Neo4j required)
	pytest -q

seed:         ## Load example events into the graph
	workgraph seed examples/seed_events.json

rank:         ## Compute + print WorkRank
	workgraph rank

logs:         ## Tail Neo4j logs
	docker compose logs -f neo4j

shell:        ## Shell into the workgraph container
	docker compose exec workgraph bash
