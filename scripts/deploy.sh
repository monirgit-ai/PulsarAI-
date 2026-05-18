#!/usr/bin/env bash
# Deploy on Ubuntu server: pull latest and restart stack
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Pulling latest from Git..."
git pull origin main

echo "Starting PulsarAI stack..."
docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml up -d --build

echo "Running migrations..."
docker compose -f docker/docker-compose.yml run --rm migrate

echo "Deploy complete."
docker compose -f docker/docker-compose.yml ps
