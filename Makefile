COMPOSE := docker compose -f infra/docker-compose.yml

.DEFAULT_GOAL := help

.PHONY: help install mcp-build up down logs dev dash seed test clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install all deps (Python via uv, JS via pnpm)
	uv sync --extra dev
	pnpm install

mcp-build: ## Build the MCP server so .mcp.json can launch it (node dist/index.js)
	pnpm --filter @phoenixos/mcp build

up: ## Start Neo4j + core API in the background (docker)
	$(COMPOSE) up -d --build

down: ## Stop Neo4j + core API
	$(COMPOSE) down

logs: ## Tail core + Neo4j logs
	$(COMPOSE) logs -f

dev: up mcp-build ## Run everything: docker (neo4j+core) + built MCP + dashboard (foreground)
	@echo "→ core API   http://localhost:8000/health"
	@echo "→ Neo4j      http://localhost:7474"
	@echo "→ dashboard  http://localhost:3000  (starting…)"
	@echo "→ MCP server built — Claude Code / Cursor launch it on demand via .mcp.json"
	pnpm --filter @phoenixos/dashboard dev

dash: ## Run dashboard dev server only (assumes core already up)
	pnpm --filter @phoenixos/dashboard dev

seed: ## Seed demo failure signatures into the running stack
	uv run python scripts/seed_demo.py

test: ## Run Python + MCP test suites
	uv run pytest tests/ -q
	pnpm --filter @phoenixos/mcp test

clean: ## Stop services and remove the Neo4j volume
	$(COMPOSE) down -v
