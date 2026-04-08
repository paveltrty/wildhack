.PHONY: up down build logs migrate seed ps restart-api shell-api shell-db

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f --tail=100

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.scripts.seed_demo_data

ps:
	docker compose ps

restart-api:
	docker compose restart api

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec postgres psql -U dispatch dispatch
