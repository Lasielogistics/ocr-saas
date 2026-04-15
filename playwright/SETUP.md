---
name: playwright-setup
description: Playwright Docker setup with noVNC for headed browser automation
type: reference
---

Playwright in Docker at `/data/projects/tms/playwright/`

**Access:**
- Local: `http://192.168.50.100:6080/vnc.html?host=192.168.50.100&port=9222`
- Tailscale: `http://100.121.68.113:6080/vnc.html?host=100.121.68.113&port=9222`

**Run via docker compose:**
```bash
cd /data/projects/tms/docker
docker compose exec playwright npx playwright test
docker compose exec playwright npx playwright test --headed
```

**Run via helper script:**
```bash
/data/projects/tms/playwright/run.sh npx playwright test --headed
```

**Tests dir:** `/data/projects/tms/playwright/tests/`
**Browser binaries:** Installed via `npx playwright install chromium --with-deps` in Dockerfile