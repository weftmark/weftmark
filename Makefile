APP_VERSION := $(shell cat VERSION | tr -d '[:space:]')
export APP_VERSION

.PHONY: build up down logs ps prune dev

build:
	docker compose build
	docker image prune -f

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

prune:
	docker image prune -a -f

dev:
	docker compose -f .devcontainer/docker-compose.devcontainer.yml up -d
