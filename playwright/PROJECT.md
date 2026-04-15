---
name: playwright-e2e-scripts
description: Playwright in Docker for TMS e2e tests and browser automation
type: project
---

Playwright container at `/data/projects/tms/playwright/`
- **Use cases**: E2E UI testing, port terminal appointment automation, any headed browser task
- **Setup**: Alpine + Chromium from system packages (not Playwright's bundled browsers)
- **Tests dir**: `projects/tms/playwright/tests/`
- **Run tests**: `docker compose -f docker-compose.yml run playwright npx playwright test`
- **Headed mode**: `docker compose -f docker-compose.yml run playwright npx playwright test --headed`
- **Base URL in container**: `http://tms-ui:80` (resolves via docker network)