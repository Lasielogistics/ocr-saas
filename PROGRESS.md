# Mini-PC TMS/OCR System - Progress

## Migrated lasie-dispatch to TMS Docker Infrastructure

**Date:** April 3, 2026

### Completed

1. **Created API service** (`/data/projects/tms/api/`)
   - `main.py` - FastAPI server combining chat + appointments CRUD
   - `requirements.txt` - Python dependencies
   - `Dockerfile` - Python 3.11 container

2. **Updated UI service** (`/data/projects/tms/ui/`)
   - Migrated frontend files: `ai.html`, `calendar.html`, `containers.html`, `dashboard.html`, `sidebar.html`, `sidebar.js`, `tabulator.html`, `tabulator2.html`
   - Created nginx Dockerfile with API proxy
   - Created `index.html` redirect to dashboard

3. **Updated docker-compose.yml**
   - Replaced `ai-assistant` service with `api` service (port 9001)
   - Updated `ui` service to use nginx with API proxy (port 3000)
   - Added `extra_hosts` for lemonade-server.ai resolution
   - Removed obsolete services from orchestration

4. **Replaced Ollama with Lemonade server**
   - Updated `main.py` to call Lemonade OpenAI-compatible API at `http://lemonade-server.ai/api/v1`
   - Added `LEMONADE_API_BASE`, `LEMONADE_MODEL`, `LOG_ORIGINS` to .env
   - ai.html now embeds Lemonade UI in iframe with sidebar navigation

5. **Lemonade Server Info**
   - Running on port 8000 with router
   - OpenAI-compatible API at `/api/v1/chat/completions`
   - Ollama-compatible API on port 11434
   - Docs saved to `/data/projects/tms/ai/lemonade_server_spec.md`

### Working Services
- **UI**: http://localhost:3000 (nginx → api proxy)
- **API**: http://localhost:9001 (FastAPI - chat + appointments)

### Current Issue
- Port 9000 was in use by unknown process - using 9001 instead

---

## APM Appointments Scraper

**Date:** April 2, 2026

### Completed

1. **Created APM scraper** (`/data/projects/tms/appointments/apm/`)
   - `scraper.py` - Playwright-based scraper with Supabase upsert
   - `Dockerfile` - Docker image using system Chromium
   - `parse_saved.py` - Parser testing tool against saved HTML
   - `requirements.txt` - Python dependencies

2. **Docker Compose integration** - Added `apm-scraper` service to `/data/projects/tms/docker/docker-compose.yml`

3. **Parser development against saved HTML pages**
   - Saved pages in `/data/projects/tms/appointments/apm/saved_pages/`
   - Successfully extracts 4 fields: appointment ID, slot, truck, container ID, type, status, line OP, cargo ref, equip size, own chassis
   - All 4 test appointments parsed correctly

4. **Database table created** - `port_appointments` table in Supabase with:
   - Index on `(terminal, apm_appointment_id)` for upsert conflict
   - Row Level Security policies
   - Updated via `handle_upsert()` trigger function

### Current Issue

**APM blocks server IP** - The APM terminal website (termpoint.apmterminals.com) has anti-bot protection that blocks requests from the server's IP address. The scraper works correctly but cannot reach APM from this location.

**Workaround options:**
- Deploy scraper on a machine with a non-blocked IP (local Windows machine)
- Use SSH SOCKS proxy through a allowed machine
- Request APM whitelist the server IP

### Windows Testing (April 2, 2026)

Attempted to run scraper on Windows with Python 3.13:
- **Issue:** greenlet package fails to build - Python 3.13 doesn't have pre-built wheels
- **Error:** `fatal error C1189: #error: "this header requires Py_BUILD_CORE define"`
- **Solution:** Use Python 3.12 instead

```powershell
py -3.12 -m pip install playwright supabase
py -3.12 -m playwright install chromium
```

### Files

```
/data/projects/tms/appointments/apm/
├── scraper.py          # Main Playwright scraper
├── parse_saved.py      # HTML parser testing tool
├── Dockerfile           # Docker image definition
├── requirements.txt     # Python packages
├── test_login.py       # Login debugging script
└── saved_pages/        # Saved HTML for offline development
    ├── 1/Login.html
    ├── 2/Dashboard.html
    ├── 3/My Appointments.html (4 real appointments)
    └── 4/Schedule an Appointment.html
```

### Running

```bash
# Build Docker image
cd /data/projects/tms/appointments/apm
docker build -t apm-scraper .

# Run (requires environment variables set)
docker run --rm \
  -e SUPABASE_URL=... \
  -e SUPABASE_KEY=... \
  -e APM_USERNAME=... \
  -e APM_PASSWORD=... \
  apm-scraper
```

---

**Date:** March 29, 2026

## Completed Today

### 1. Folder Structure Created
```
/data/
├── ocr/          # Pending, temp, processed, review
├── projects/tms/  # ui, email-agent, appointments, invoices, email, ai-assistant
├── logs/
├── dev/
└── prod/

/mnt/qnap-tms/    # documents, exports, backup
```

### 2. Docker Setup
- All 7 containers created as placeholders
- docker-compose.yml configured
- All containers running successfully

### 3. Hardware Benchmark
- OS drive (512GB): ~5.6 GiB/s read
- Data drive (2TB Samsung): ~5.85 GiB/s read

### 4. Microsoft 365
- Created shared mailbox: tms@lasielogistics.com

### 5. NPU/AI Stack Installation & Working
- Added Lemonade PPA
- Installed: libxrt-npu2, amdxdna-dkms, libxrt-utils-npu
- Installed: Lemonade Server (v10.0.1)
- Installed: FastFlowLM (v0.9.37)
- xrt-smi monitoring working
- **NPU DETECTED:** RyzenAI-npu4 (c7:00.1)
- **XRT Version:** 2.21.75
- **NPU Firmware:** 1.1.2.64
- **FastFlowLM server running on port 52625**
- **20+ models available** (llama3.2, qwen3, gemma3, phi4, etc.)
- **First AI inference completed on NPU!**
- Models auto-download on first use (llama3.2-1B: 1.2GB, qwen3-1.7B: 1.6GB)

---

## Current System Status

| Component | Details |
|-----------|---------|
| Server | MINISFORUM AX1 Pro |
| CPU | AMD Ryzen AI 9 HX 470, 64GB RAM |
| OS | Ubuntu Server 25.10 |
| Storage | 512GB OS + 2TB data + 38TB NAS |
| Docker | 7 containers running |
| AI Stack | FastFlowLM v0.9.37 |
| NPU | RyzenAI-npu4, 58 TOPS |

---

## Commands

```bash
# Docker
cd /data/projects/tms/docker
docker compose up -d
docker compose logs -f
docker stats

# Check NPO
sudo xrt-smi examine
sudo xrt-smi --version
sudo xrt-smi validate

# FastFlowLM AI
sudo flm serve --socket 10 --q-len 15 &
curl localhost:52625/v1/models
curl -X POST localhost:52625/v1/completions -d '{"model": "llama3.2:1b", "prompt": "Hello", "max_tokens": 50}'
curl -X POST localhost:52625/v1/chat/completions -d '{"model": "qwen3:1.7b", "messages": [{"role": "user", "content": "Hello"}]}'
```

---

## What's Next

1. Implement actual Docker containers (UI, OCR, AI assistant, etc.)
2. Set up Supabase tables
3. Configure terminal integrations
4. Download more models
5. **Install Whisper** for speech-to-text transcription

## Whisper Tomorrow

Install Whisper for voice/input transcription:
- Whisper.cpp or WhisperCpp integration
- Voice input to text
- Audio transcription capabilities

---

## Key Achievements Today

- ✓ 7 Docker containers running
- ✓ NPU working on Ryzen AI 9 HX 470
- ✓ FastFlowLM running on NPU
- ✓ First local AI inference on mini-pc!
- ✓ Local AI server operational

---

## OCR SaaS - Multi-Tenant OCR Service

**Date:** April 8, 2026

### Architecture
Built a scalable multi-tenant OCR SaaS with:
- **FastAPI** REST API server for uploads and status
- **Celery + Redis** for async job queue with worker scaling
- **Surya OCR** for document processing
- **Per-customer Supabase projects** for data isolation
- **Email ingestion** via IMAP polling

### Directory Structure
```
/data/projects/tms/
├── ocr_api/                    # FastAPI REST API
│   ├── api/main.py            # Routes: /upload, /status, /webhook
│   ├── api/auth.py            # API key authentication
│   ├── api/celery_app.py      # Celery configuration
│   ├── api/email_consumer.py  # IMAP polling
│   ├── shared/                 # Shared modules
│   ├── Dockerfile
│   └── requirements.txt
│
├── worker/                     # Celery OCR worker
│   ├── celery.py              # Celery instance
│   ├── tasks.py               # process_document task
│   ├── processor.py           # OCR pipeline (Surya OCR)
│   ├── preprocessing.py       # Image enhancement
│   ├── classifier.py          # Document type classification
│   ├── extractor.py           # Field extraction
│   ├── Dockerfile
│   └── requirements.txt
│
├── shared/                     # Shared between API and worker
│   ├── models.py              # Pydantic models
│   ├── supabase.py            # Per-customer Supabase client factory
│   ├── storage.py             # File storage utilities
│   └── customers.json         # Customer config template
│
└── scripts/
    └── init_customer.sql      # SQL schema for new customer
```

### Document Types Supported
pod, invoice, receipt, rate_confirmation, fuel_receipt, scale_ticket, eir, gate_ticket, load_confirmation, terminal_paperwork, appointment_confirmation, container_pickup, container_dropoff, chassis_paperwork, yard_ticket, reference_sheet

### Docker Services Added
| Service | Port | Description |
|---------|------|-------------|
| `tms-redis` | 6379 | Celery message broker |
| `tms-ocr-api` | 9000 | REST API for uploads/status |
| `tms-ocr-worker` | - | Celery worker for OCR |

### Key Features
- **File watcher style** via REST API (upload → job_id → poll status)
- **Multi-page PDF support** via pdf2image
- **Image preprocessing**: deskew, CLAHE contrast, denoise, resize
- **Document classification**: keyword + pattern heuristics
- **Field extraction**: container numbers, dates, amounts, references
- **Webhook notifications** on job completion
- **Email ingestion**: IMAP polling per customer mailbox

### To Build & Test
```bash
cd /data/projects/tms/docker
docker compose build redis ocr_api ocr_worker
docker compose up -d redis ocr_api ocr_worker

# Test health
curl http://localhost:9000/health

# Upload document
curl -X POST http://localhost:9000/api/v1/upload \
  -F "file=@test.pdf" \
  -H "X-API-Key: your_api_key"
```

### Pending - Before Production
1. Populate `/data/projects/tms/shared/customers.json` with real customer Supabase credentials
2. Run `/data/projects/tms/scripts/init_customer.sql` in each customer's Supabase project
3. Add real IMAP credentials for email ingestion
4. Test end-to-end with sample documents

### Services Status (2026-04-08)
- tms-api: Running (port 9001) - TMS chat + appointments + APM API ✓ Restored
- tms-ocr-api: Running (port 9010) - OCR SaaS REST API ✓
- tms-ocr-worker: Running - Celery worker ✓
- tms-redis: Running (port 6379) ✓

---

## OCR SaaS - Fixes & Surya OCR Working (2026-04-08)

### Fixes Applied Today

1. **OpenCV API change** (`worker/preprocessing.py:118`)
   - `fastNlMeansDenoisingColored` in OpenCV 4.11+ uses positional args instead of keyword args
   - Changed from `hForColorComponents=10` to positional `10`

2. **Idempotent file moves** (`shared/storage.py:53-68`)
   - `move_to_processed` and `move_to_review` now check if file already exists
   - Handles retry scenarios where file may already be moved

3. **Renamed supabase.py** to avoid conflict with `supabase` pip package
   - `shared/supabase.py` → `shared/supabase_client.py`
   - `worker/supabase.py` → `worker/supabase_client.py`

### Surya OCR - Now Working

Surya OCR was already in requirements.txt and Dockerfile. Rebuilt worker container:
- Rebuilt `docker-ocr_worker` image with Surya OCR
- Worker now uses Surya OCR instead of Tesseract fallback
- End-to-end test passed with real logistics documents

**Test Results:**
| File | Type | Extracted Fields |
|------|------|------------------|
| `AIMZ484307 EIR OUT.pdf` | receipt | reference_number: 01039151 |
| `AIMZ401646 EIR IN.pdf` | chassis_paperwork | - |
| `BEAU5507464 POD.pdf` | load_confirmation | - |

### API Working End-to-End

```bash
# Upload
curl -X POST http://localhost:9010/api/v1/upload \
  -H "X-API-Key: ocr_test_key_123" \
  --form "file=@/data/ocr/pending/AIMZ484307\ EIR\ OUT.pdf"

# Check status
curl http://localhost:9010/api/v1/status/{job_id} \
  -H "X-API-Key: ocr_test_key_123"
```

Response:
```json
{
  "job_id": "dfde5112-1d7",
  "status": "completed",
  "document_type": "receipt",
  "confidence_score": 0.85,
  "extracted_fields": {"reference_number": "01039151"},
  "ocr_text": "Flexivan Leasing\nLLC\n\nGate Receipt\n...",
  "processed_at": "2026-04-08T04:58:55Z"
}
```

### Git Commits

- `62c9165` - Fix OCR processing: OpenCV API and file path handling

### Next Steps (Tomorrow)

1. **Create review web page** - UI to show documents needing review
2. **Detailed document classification** - More granular types for organizing docs
3. **Test with 5 real logistics documents** (EIRs, PODs, Bills)

### Plan File
Full plan saved at: `/home/talha/.claude/plans/cuddly-exploring-cerf.md