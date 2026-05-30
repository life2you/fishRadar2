SHELL := /bin/zsh

.PHONY: api-dev api-test worker-check worker-daemon web-install web-build dev-up dev-down

api-dev:
	cd services/radar-control && go run ./cmd/server

api-test:
	cd services/radar-control && go test ./...

worker-check:
	python3 -m compileall services/radar-probe/src services/radar-probe/spider_v2.py services/radar-probe/tools

worker-daemon:
	cd services/radar-probe && python3 tools/worker_job_runner.py

web-install:
	cd services/radar-portal && npm install

web-build:
	cd services/radar-portal && npm run build

dev-up:
	cd deploy && docker compose -f docker-compose.dev.yml up --build -d

dev-down:
	cd deploy && docker compose -f docker-compose.dev.yml down
