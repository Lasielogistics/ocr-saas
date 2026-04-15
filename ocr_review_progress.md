# OCR Review Page - Current Progress

## Last Session: 2026-04-14

### Completed Today

1. **Fixed column widths** - Adjusted column percentages to sum exactly to 100%, changed Actions column from 90px to 8%, added border-collapse for consistent sizing

2. **Added lightweight stats API** - New `/api/v1/documents/stats` endpoint returns counts by status without loading all documents into memory

3. **Fixed frontend stats loading** - OCR review page now uses efficient stats endpoint instead of loading 99999 documents

4. **Pushed to git** - Committed all changes

### Root Cause of Chrome Crash
The `loadStats()` function was requesting `limit=99999` documents just to count statuses. With 1338+ documents, this caused memory issues that crashed Chrome.

### Fix Applied
- New API endpoint `/api/v1/documents/stats` returns `{review, failed, ocr, verified, total}` in one lightweight query
- Frontend now calls this endpoint instead of loading all documents

### Key Files

- `/data/projects/tms/ui/ocr_review.html` - Main UI file with virtual scrolling and filters
- `/data/projects/tms/ocr_api/api/main.py` - API endpoints (stats added at line 74)
- `/data/projects/tms/worker/tasks.py` - Celery worker sets status to "ocr" after processing
- `/data/projects/tms/shared/models.py` - DocumentStatus enum (OCR, VERIFIED, REVIEW, FAILED)

### Stats Cards
- Needs Review (review status)
- Failed (failed status)
- OCR (ocr status - not yet verified)
- Verified (verified status - manually reviewed)

### Filter Options
- Status: OCR, Verified, Needs Review, Failed, All
- Type: All document types (POD, Invoice, Container EIR, etc.)
- Auto-applies filter on dropdown change (debounced 200ms)

### Virtual Scrolling
- ROW_HEIGHT = 56px
- BUFFER_SIZE = 10 rows
- Only renders ~30 rows in DOM despite having 1338+ documents

### Next Steps
- Test column width stability during scroll
- Potentially adjust column width percentages if needed
- Add more features as needed by user