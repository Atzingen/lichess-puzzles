.PHONY: build up down logs ingest rebuild test clean

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ingest:
	docker compose run --rm app python -m ingest.run

rebuild:
	docker compose down
	docker compose build
	docker compose up -d

test:
	docker compose run --rm app pytest -v

clean:
	rm -f data/puzzles.sqlite
