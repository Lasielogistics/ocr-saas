# APM Appointments Scraper

Scrapes appointment data from APM Terminals TERMPoint (termpoint.apmterminals.com) and syncs to Supabase.

## Files

| File | Description |
|------|-------------|
| `scraper.py` | Main scraper - uses Playwright to login and scrape appointments |
| `parse_saved.py` | Offline parser testing tool - tests regex against saved HTML pages |
| `Dockerfile` | Docker image definition |
| `requirements.txt` | Python dependencies |
| `test_login.py` | Quick login debugging script |

## Flow

1. Login to TERMPoint with credentials
2. Navigate to My Appointments page
3. Parse all appointment rows
4. Upsert each appointment to Supabase `port_appointments` table

## Parser Logic (parse_saved.py)

Works against saved HTML pages in `saved_pages/` directory. Extracts:
- Appointment ID (from `<a class="clearpadding">`)
- Slot datetime (from `Slot</span>...<b>`)
- Truck number
- Type (IMPORT PICKUP, EMPTY DROPOFF, etc.)
- Container ID (4 letters + 7 digits)
- Line OP (MAE, EGL, etc.)
- Cargo ref (9+ digits)
- Equipment size (40GP96, etc.)
- Own chassis (Yes/No)
- Status (CONFIRMED, etc.)

**Test results on saved HTML (3/My Appointments.html):**
```
Found 4 appointments
  ✓ 6354539: TIIU5204104 | IMPORT | 04/01/2026, 02:00 | CONFIRMED
  ✓ 6423841: TIIU5204104 | EMPTY | 04/02/2026, 09:00 | CONFIRMED
  ✓ 6410831: DRYU9828637 | IMPORT | 04/04/2026, 11:30 | CONFIRMED
  ✓ 6410832: DRYU9851513 | IMPORT | 04/04/2026, 11:30 | CONFIRMED
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase API key |
| `APM_USERNAME` | Yes | TERMPoint login username |
| `APM_PASSWORD` | Yes | TERMPoint login password |
| `TERMINAL` | No | Terminal name (default: APM) |
| `COMPANY_NAME` | No | Company name (default: Lasielogistics) |

## Running

### With Docker

```bash
# Build
cd /data/projects/tms/appointments/apm
docker build -t apm-scraper .

# Run (set env vars first)
docker run --rm \
  -e SUPABASE_URL="$SUPABASE_URL" \
  -e SUPABASE_KEY="$SUPABASE_KEY" \
  -e APM_USERNAME="$APM_USERNAME" \
  -e APM_PASSWORD="$APM_PASSWORD" \
  apm-scraper
```

### Parse saved HTML (offline testing)

```bash
cd /data/projects/tms/appointments/apm
python3 parse_saved.py
```

## Windows Setup (Python 3.13 Issue)

Python 3.13 has compatibility issues with some packages (greenlet) due to missing pre-built wheels.

**Recommended: Use Python 3.12**
```powershell
py -3.12 --version  # check if available
py -3.12 -m pip install playwright supabase
py -3.12 -m playwright install chromium
py -3.12 scraper.py
```

**Alternative: Use pip only-binary**
```powershell
pip install --only-binary :all: supabase
pip install playwright
python -m playwright install chromium
```

## Known Issues

1. **APM blocks server IP** - The server's IP is blocked by APM's anti-bot protection. Deploy on a local machine with an allowed IP.

2. **Python 3.13 compatibility** - greenlet package doesn't have pre-built wheels for Python 3.13. Use Python 3.12 or earlier.

## Database Schema

Appointments are upserted to `port_appointments` table with this structure:

```sql
CREATE TABLE port_appointments (
    id BIGSERIAL PRIMARY KEY,
    terminal TEXT NOT NULL,
    apm_appointment_id TEXT NOT NULL,
    apm_slot TIMESTAMPTZ,
    apm_truck TEXT,
    apm_type TEXT,
    apm_status TEXT,
    container_id TEXT,
    line_op TEXT,
    cargo_ref TEXT,
    equip_size TEXT,
    own_chassis TEXT,
    company_name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(terminal, apm_appointment_id)
);
```