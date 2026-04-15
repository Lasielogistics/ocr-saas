#!/bin/bash
# Run Playwright via docker compose - usage: ./run.sh npx playwright test --headed
cd "$(dirname "$0")/../docker"
docker compose exec -T playwright "$@"
