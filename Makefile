.PHONY: demo

demo: ## The whole stack in Docker on http://localhost:8000 (compose.yaml)
	docker compose up --build
