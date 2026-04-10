.PHONY: up down build logs migrate demo seed ps shell-api shell-db trigger-cycle

up:
	docker compose up -d

down:
	docker compose down -v

build:
	docker compose build --no-cache

logs:
	docker compose logs -f --tail=100

migrate:
	docker compose exec api alembic upgrade head

demo:
	docker compose -f docker-compose.yml -f docker-compose.demo.yml up

demo-d:
	docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d

ps:
	docker compose ps

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec postgres psql -U dispatch dispatch

trigger-cycle:
	curl -s -X POST http://localhost/api/internal/trigger-cycle | python3 -m json.tool
