# Lemonade Server / TMS Integration Progress

## Date: 2026-04-04

## TMS API Chat Endpoint - Lemonade Integration

The `tms-api` container uses Lemonade Server to provide AI-powered chat over container/logistics data.

### Connection Details:
- **Host**: Port 8000
- **Container**: Connects via `http://172.17.0.1:8000/api/v1` (host Docker gateway)
- **Model Used**: `qwen3.5-4b-FLM`

### Environment Variables (in `/data/projects/tms/docker/.env`):
```
LEMONADE_API_BASE=http://172.17.0.1:8000/api/v1
LEMONADE_MODEL=qwen3.5-4b-FLM
```

### How It Works:
1. User sends question to `POST http://localhost:9001/chat`
2. TMS API checks if query is container-related (keywords: container, pickup, delivery, driver, vessel, etc.)
3. If yes, queries Supabase for container data and includes it as context
4. Sends question + context to Lemonade Server (`/api/v1/chat/completions`)
5. Returns streaming response

### Issues Fixed:
1. **DNS Resolution**: Container couldn't resolve `lemonade-server.ai` (Cloudflare IPv6 took precedence over /etc/hosts). Fixed by using host IP `172.17.0.1` instead.

2. **Model Name**: Original model `qwen3:1.7b` didn't exist. Updated to `qwen3.5-4b-FLM`.

### Testing:
```bash
curl -X POST http://localhost:9001/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What containers are in the database?"}]}'
```

**Verified working** - AI responds with container data from Supabase.

### Available Models:
Run `GET http://localhost:8000/api/v1/models` to see all available models.

Current model loaded: `qwen3.5-4b-FLM` (Qwen 3.5 4B params, FLM recipe)
