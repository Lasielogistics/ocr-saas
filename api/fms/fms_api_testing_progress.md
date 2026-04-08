# FMS API Testing Progress

## Date: 2026-04-04

## FMS API Spec (FCI API Specs 1.8)
- Located at: `/data/projects/tms/api/fms/docs/FCI API Specs 1.8.docx`
- Also available as PDF: `FCI API Specs 1.8.pdf`
- Describes SOAP-based APIs for Fenix Commercial Interface (FCI)
- Version 1.8, dated 19-Mar-2025

### FCI API Endpoints (from spec):
1. **Container Availability / Unit Finder Query**
   - URL: `https://n4.fenixmarineservices.com/apex/api/codeextension`
   - Params: `extensionname=FenixCheckCtrAvailability`, `operatorId=FMS`, `complexId=USSPQ`, `facilityId=FMS`, `yardId=FMS`, `PARM_filterName=UNIT_FINDER_QUERY`, `PARM_CTRNBR=<container_number>`

2. **Booking Inquiry API**
   - URL: `https://n4.fenixmarineservices.com/apex/api/query`
   - Params: `filtername=BOOKING_INQUIRY`, `PARM_NBR=<booking_number>`, etc.

3. **Vessel Schedule API**
   - URL: `https://n4.fenixmarineservices.com:9081/apex/api/query`
   - Params: `filtername=VESSEL_SCHEDULE`, etc.

4. **Pre-Record Truck Details (Appointment Update)**
   - SOAP-based WS request
   - Root element: `custom` with `class="FMSAppointmentWSHandler"` and `type="extension"`

---

## Running TMS API (Port 9001)

### Container Info:
- Container name: `tms-api`
- Image: `docker-api`
- Port: 9001 → container 9000
- Docker network: `docker_tms-network`

### Tech Stack:
- FastAPI + Uvicorn
- Supabase (PostgreSQL) - URL: `https://bsaffwfvnnyaihmrmqwt.supabase.co`
- Lemonade AI server for chat

### Endpoints:
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/chat` | AI chat (queries containers via Supabase) |
| POST | `/log` | Log entries |
| GET/POST | `/appointments` | Appointment CRUD |
| GET | `/apm/slots` | APM slots (Admiral API) |
| GET | `/apm/appointments` | APM appointments |
| POST | `/apm/sync` | Sync with APM system |

---

## Lemonade Server (Port 8000)

- Running on host at port 8000
- Models available include: `qwen3.5-4b-FLM`, `DeepSeek-Qwen3-8B-GGUF`, etc.
- Health: `http://localhost:8000/api/v1/health`

---

## Fixes Applied

### 1. Lemonade API Connection Issue (RESOLVED)
**Problem:** `tms-api` container couldn't reach `lemonade-server.ai` due to DNS returning Cloudflare IPv6 addresses.

**Solution:** Updated `/data/projects/tms/docker/.env`:
```
LEMONADE_API_BASE=http://172.17.0.1:8000/api/v1
```
instead of `http://lemonade-server.ai/api/v1`

### 2. Model Name Issue (RESOLVED)
**Problem:** Model `qwen3:1.7b` not found.

**Solution:** Updated model name to:
```
LEMONADE_MODEL=qwen3.5-4b-FLM
```

### 3. Container Restart Required
After changing `.env`, container must be recreated:
```bash
cd /data/projects/tms/docker
docker compose rm -sf api
docker compose up -d api
```

---

## Testing the Chat Endpoint

```bash
curl -X POST http://localhost:9001/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What containers are in the database?"}]}'
```

**Verified working:** AI responds with container data from Supabase.

---

## Files Modified
- `/data/projects/tms/docker/.env` - LEMONADE_API_BASE and LEMONADE_MODEL settings

---

## Notes
- The FCI API spec describes SOAP APIs at external URLs (n4.fenixmarineservices.com)
- The port 9001 TMS API is an internal REST wrapper that queries Supabase and uses Lemonade AI
- APM endpoints on port 9001 require Admiral credentials (not currently configured)
