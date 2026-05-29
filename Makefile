SHELL := /bin/zsh

.PHONY: api-dev api-test worker-check worker-daemon web-install web-build dev-up dev-down

api-dev:
	cd services/api-go && go run ./cmd/server

api-test:
	cd services/api-go && go test ./...

worker-check:
	python3 -m compileall services/worker-py/src services/worker-py/spider_v2.py services/worker-py/tools

worker-daemon:
	cd services/worker-py && python3 tools/worker_job_runner.py

web-install:
	cd services/web-ui && npm install

web-build:
	cd services/web-ui && npm run build

dev-up:
	cd deploy && docker compose -f docker-compose.dev.yml up --build -d

dev-down:
	cd deploy && docker compose -f docker-compose.dev.yml down
