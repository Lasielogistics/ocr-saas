# OCR Project Notes (2026-04-07)

## Current State

### TMS Project Structure
- Location: `/data/projects/tms/`
- OCR service: placeholder Dockerfile at `projects/tms/docker/ocr/Dockerfile`
- Docker-compose configured but OCR container does nothing
- Email-agent also placeholder

### OCR Workflow (planned)
```
/data/ocr/pending → OCR processing → /data/ocr/processed or /data/ocr/review
```

### Volume Mounts
- `/data/ocr/pending` - inbound documents
- `/data/ocr/temp` - temp processing
- `/data/ocr/processed` - completed
- `/data/ocr/review` - failed OCR needing manual review

### Supabase Integration
- OCR service has `SUPABASE_URL` and `SUPABASE_KEY` env vars
- OCR container can write results to Supabase (tables to be determined)
- Pattern follows existing services (api, appointments, etc.)

## Document Sources
Files come from **various sources** - not just email attachments.

## Storage Strategy

| Location | Purpose |
|----------|---------|
| OneDrive | Source of truth (redundancy) |
| NAS (RAID 5) | Local backup |
| Ubuntu Server | Working copies for Docker |

## Proposed Sync Approach (Option A - Two-way sync)

1. `rclone sync` OneDrive → `/data/ocr/pending` (every 5-10 min via cron)
2. OCR processes files on server
3. Processed files go to `/data/ocr/processed`
4. Another rclone cron syncs processed back to OneDrive

Use `--transfers 10` for parallel file copies.

## Next Steps
1. Implement actual OCR service (Tesseract OCR recommended for self-hosted)
2. Decide: Python vs Node.js for OCR service
3. Define database schema for OCR results
4. Set up rclone configuration for OneDrive sync
5. Test the full workflow