# TMS Docker Setup

## Quick Start

1. Copy the environment template:
```bash
cp .env.example .env
```

2. Edit .env with your credentials:
```bash
nano .env
```

3. Build and start all containers:
```bash
docker compose up -d
```

4. Check status:
```bash
docker compose ps
```

5. View logs:
```bash
docker compose logs -f
```

## Containers

| Container | Port | Purpose |
|-----------|------|---------|
| ui | 3000 | Web dashboard |
| ai-assistant | 8080 | Business query API |
| email-agent | - | Inbound email polling |
| ocr | - | Document OCR |
| appointments | - | Terminal booking |
| invoices | - | Invoice generation |
| email | - | Outbound email |

## Stop/Start

```bash
docker compose down      # Stop all
docker compose up -d   # Start all in background
docker compose restart # Restart all
```

## Individual Container

```bash
docker compose up -d ui        # Start just UI
docker compose logs -f ui       # View UI logs
docker compose restart ui      # Restart just UI
```

## Getting Credentials

### Supabase
- Go to https://supabase.com
- Your project → Settings → API
- Find "Project URL" and "anon public" key

### Microsoft 365
Option A: Shared Mailbox (recommended - no extra license)
- Create in Admin Center → Shared mailboxes
- Give your main account access to it
- Use that account's password in the .env

Option B: Regular account with app password
- Enable 2FA first, then create an App Password:
  - https://account.microsoft.com/security → Security basics → App passwords

### AI API
- OpenAI: https://platform.openai.com/api-keys
- Or your preferred AI provider