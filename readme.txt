# Mini-PC TMS/OCR System

Set up my Ubuntu mini PC and QNAP NAS for TMS (Transportation Management System) with OCR capabilities.

## Hardware / Storage

| Component | Details |
|-----------|---------|
| Server | MINISFORUM AX1 Pro |
| CPU | AMD Ryzen AI 9 HX 470 |
| RAM | 64GB |
| OS | Ubuntu Server 25.10 (must stay on this version) |
| Ubuntu OS drive | 512GB SK hynix NVMe mounted at `/` |
| Local data drive | 2TB Samsung 9100 Pro mounted at `/data` |
| QNAP NAS hostname | TheArchives |
| QNAP IP | 192.168.50.99 |
| Mini-PC IP | 192.168.50.100 |
| Access pattern | Windows laptop as frontend; Ubuntu server as AI backend host |
| Remote access | Browser-based or SSH from Windows laptop |

## Storage Architecture

- **Supabase** (cloud) = Source of truth for business records, metadata, OCR extracted fields, audit history, workflow state
- **NAS** = Permanent file storage
- **/data** on local 2TB NVMe = Hot local storage for Docker, staging, OCR temp, workspace, logs
- **OneDrive** = Backup target (not live primary storage)

## Folder Structure

```
/data/
├── ocr/
│   ├── pending/        # Files waiting for OCR
│   ├── temp/           # OCR scratch space
│   ├── processed/      # Completed OCR
│   └── review/         # Failed OCR needing manual review
├── chat/               # Chat log files (JSONL)
├── projects/
│   └── tms/
│       ├── ui/              # Web dashboard (nginx + static files)
│       ├── api/             # FastAPI - chat + appointments endpoints
│       ├── email-agent/      # Inbound email classifier + parser
│       ├── appointments/    # Terminal booking code (including apm/)
│       ├── invoices/        # Invoice generation code
│       ├── email/           # Email service code
│       └── ai/              # AI documentation (lemonade specs)
├── logs/               # Container logs + CLI tool logs
├── dev/                # Dev environment data
└── prod/               # Prod environment data

/mnt/qnap-tms/
├── documents/          # Permanent uploaded docs
├── exports/            # Invoices, PDFs, CSVs
└── backup/             # Backup/recovery files
```

## Docker Containers

Seven containers, each doing one thing:

| Container | Purpose |
|-----------|---------|
| `ui` | Web dashboard (nginx) - proxies to api; serves static files for dispatchers |
| `api` | FastAPI server - chat (Lemonade AI) + appointments CRUD; runs on port 9001 |
| `email-agent` | Polls inbox, classifies incoming emails (DO, RFQ, other), parses delivery orders and pushes to Supabase, generates RFQ draft replies from rate sheet |
| `ocr` | Document OCR - reads uploaded documents, extracts text and fields |
| `appointments` | Terminal booking - placeholder for booking logic |
| `invoices` | Generates PDFs from Supabase data, emails to customers |
| `email` | Centralized email service - handles all outgoing emails (OCR failures, reminders, invoices, driver manifests) |
| `apm-scraper` | APM TERMPoint scraper - Playwright-based browser automation |

### Appointment Terminals

| Status | Terminals |
|--------|-----------|
| Have API | APM, LBCT (not tested yet) |
| Need scraping | emodal (Everport, ITS, PCT, Pier A, TTI, Trapac), FMS (Fenix Marine), YTI (Yusen), WBCT (West Basin) |

The appointments container spawns multiple browser instances to handle different terminal websites. Only one logged-in session per terminal website is allowed.

## Container Cycle

Complete workflow for each container:

```
1. INTAKE        → Customer emails DO → Enter in UI → Supabase
2. CHECK         → Query terminal for container status (holds, availability)
3. BOOK          → Schedule pickup appointment (or dummy appointment)
4. DISPATCH      → Assign driver in UI
5. PICKUP        → Live unload OR Drop at customer location
6. RETURN        → Return empty container + chassis
7. INVOICE       → Generate from Supabase data → Email to customer
8. PAYMENT       → Track payment received
```

**Notes:**
- **UI** handles dispatching loads to drivers
- **Mobile app** (future) shows drivers their assigned loads, lets them upload docs
- **Customer portal** (future) could be same UI or separate web page
- **Rate sheet** stored in Supabase for email-agent to reference when generating RFQ replies

## Reminders System

The appointments container monitors for:
- Containers available but no appointment booked
- No empty-in appointment scheduled
- Appointments that need to be modified (dummy → real container number)
- 48-hour deadline for empty returns

## AI Assistant

The AI assistant lets dispatchers and drivers ask business questions in plain English.

### Architecture

This is a structured-data problem, NOT a raw LLM problem. The AI does NOT guess against raw data.

```
User asks question → Backend classifies intent → Backend maps to safe function → Backend queries Supabase → Model formats answer
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ai/query` | POST | Ask business question |
| `/ai/transcribe` | POST | Voice input to text |
| `/health` | GET | Service health check |

### Safe Business Functions

The AI assistant uses strict tool/function-based access to Supabase:

| Function | Description |
|----------|-------------|
| `count_available_without_appointments()` | Containers available but no appointment |
| `count_not_invoiced()` | Containers not yet invoiced |
| `count_invoiced_unpaid()` | Invoiced but payment not received |
| `list_stale_containers()` | Containers in stuck state |

### Driver App (Future)

Simple mobile app for drivers:
- Login
- Text input
- Voice input
- Response display
- View assigned loads
- Upload docs

The driver app is a thin client - it does NOT contain raw DB logic. It calls the AI assistant API.

### Dispatcher Chat Widget

Chat widget embedded in the UI for dispatchers to ask questions like:
- "How many containers are available but don't have appointments?"
- "How many containers are not invoiced?"
- "How many containers are invoiced but payments not received?"

### Monitoring / Metrics

Collect both app-level and NPP/system metrics:

**App metrics:**
- Request timestamp
- Question text
- Selected tool/function
- DB query time
- Model latency
- Tokens in / out
- Tokens/sec
- Total response time
- Errors

**System metrics (via AMD tooling):**
- xrt-smi snapshots
- CPU usage
- RAM usage
- NPU usage

## AI Stack

### Architecture

Hybrid approach:
- **Native on host** (for hardware access): AMD NPU stack
- **Docker** (for application services): AI assistant, TMS containers

Native:
- amdxdna / XRT
- xrt-smi for NPU inspection
- FastFlowLM / Lemonade for Linux NPU LLM path
- AMD Ryzen AI tooling for monitoring/profiling

Docker:
- AI assistant API
- TMS containers (ui, ocr, appointments, etc.)
- Logging/metrics stack

### Layering

```
1. Base OS: Ubuntu Server 25.10
2. Native AMD tooling: amdxdna, XRT, xrt-smi
3. LLM runtime: FastFlowLM / Lemonade
4. Docker: Application services
```

### Important Notes

- Ubuntu Server 25.10 is required - other Ubuntu versions cause iGPU issues
- Do NOT use Ubuntu Desktop
- Do NOT try to containerize the AMD/NPO stack
- Use browser/SSH access from Windows laptop, not desktop on server

## Notes

- Hot active processing stays on `/data`
- Permanent documents/exports/backups go on NAS
- Supabase holds metadata/truth/search/audit, not folder organization
- Dev and prod environments are separate

## Commands

### Mount NAS (if not persistent)
```bash
sudo mount -t nfs -o nfsvers=4 192.168.50.99:/tms /mnt/qnap-tms
```

### Create folders
```bash
sudo mkdir -p /data/ocr/pending /data/ocr/temp /data/ocr/processed /data/ocr/review /data/projects/tms/ui /data/projects/tms/email-agent /data/projects/tms/appointments /data/projects/tms/invoices /data/projects/tms/email /data/projects/tms/ai-assistant /data/logs /data/dev /data/prod /mnt/qnap-tms/documents /mnt/qnap-tms/exports /mnt/qnap-tms/backup
```

### Make NFS mount persistent (optional)
Add to `/etc/fstab`:
```
192.168.50.99:/tms /mnt/qnap-tms nfs defaults,nfsvers=4 0 0
```

## Next Steps

1. Mount NAS and create folder structure
2. Install Docker on mini-pc
3. Set up Docker Compose for OCR container
4. Test OCR on sample documents
5. Set up appointments container with browser automation
6. Test terminal logins and booking
7. Set up invoices container
8. Set up email container
9. Configure Supabase tables for container cycle tracking
10. Test full cycle end-to-end

## To Be Covered Later

- Supabase table schema (containers, rates, customers, audit fields)
- Internal API communication between containers
- Scheduling (email-agent poll interval, reminder check frequency)
- Credentials management (API keys, terminal logins)
- Rate sheet format and fields
- NAS to OneDrive backup automation
- Container orchestration details
- Detailed testing plan
- Safe business query functions implementation
- AI assistant monitoring setup
- Driver voice input implementation
