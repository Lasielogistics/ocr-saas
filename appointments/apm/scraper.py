#!/usr/bin/env python3
"""
APM TERMPoint Scraper
Logs into APM TERMPoint and scrapes appointments to Supabase
"""

import os
import sys
import time
from datetime import datetime
from supabase import create_client
from playwright.sync_api import sync_playwright

# Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://bsaffwfvnnyaihmrmqwt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJzYWZmd2Z2bm55YWlobXJtcXd0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTgxNDk1NzksImV4cCI6MjA3MzcyNTU3OX0.RyyuoUS8bcf-a18SWExPZurd8mbX4XLOITiSAARV7sI")

# APM credentials
APM_USERNAME = os.getenv("APM_USERNAME")
APM_PASSWORD = os.getenv("APM_PASSWORD")

# Terminal name
TERMINAL = os.getenv("TERMINAL", "APM")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Lasielogistics")

def parse_appointments(page):
    """Parse appointment data from the My Appointments page."""
    appointments = []

    try:
        # Find all appointment rows in the grid
        rows = page.locator('[name="multigrid"]').all()

        for row in rows:
            try:
                # Extract appointment data
                appt_num_elem = row.locator('a.clearpadding').first
                appt_num = appt_num_elem.inner_text().strip() if appt_num_elem.count() > 0 else ""

                # Skip if no appointment number
                if not appt_num:
                    continue

                # Extract slot and truck info
                slot_elem = row.locator('span >> text=/Slot/')
                slot_text = slot_elem.inner_text().split(':')[1].strip() if slot_elem.count() > 0 else ""

                truck_elem = row.locator('span >> text=/Truck/')
                truck_text = truck_elem.inner_text().split(':')[1].strip() if truck_elem.count() > 0 else ""

                # Extract type
                type_elem = row.locator('span.color-extra').first
                appt_type = type_elem.inner_text().strip() if type_elem.count() > 0 else ""

                # Extract container ID - from column cell containing container number
                # Column cells are: type, container, line, cargo, size, chassis, status
                # Container is in column index 1 (second column)
                column_cells = row.locator('.column.cell').all()
                container_id = ""
                if len(column_cells) >= 2:
                    cell_text = column_cells[1].inner_text().strip()
                    # Container is 4 letters + 7 digits
                    import re
                    container_match = re.search(r'([A-Z]{4}\d{7})', cell_text)
                    if container_match:
                        container_id = container_match.group(1)

                # Extract line op - look for shipping line codes in spans
                line_codes = ['MAE', 'EGL', 'MSC', 'CMA', 'ONE', 'HPL', 'HMM', 'COS', 'ZIM', 'EMC']
                line_op = ""
                for code in line_codes:
                    line_elem = row.locator(f'span:has-text("{code}")').first
                    if line_elem.count() > 0:
                        line_op = code
                        break

                # Extract cargo ref - look for 9+ digit numbers
                all_spans = row.locator('span').all()
                cargo_ref = ""
                for span in all_spans:
                    text = span.inner_text().strip()
                    if text.isdigit() and len(text) >= 9:
                        cargo_ref = text
                        break

                # Extract size - look for patterns like 40GP, 40HC, 45HC
                size = ""
                for span in all_spans:
                    text = span.inner_text().strip()
                    if len(text) == 4 and text[:2].isdigit():
                        size = text
                        break
                    elif len(text) == 5 and text[:2].isdigit() and text[2:].isalpha():
                        size = text
                        break

                # Extract own chassis - Yes or No
                chassis_elem = row.locator('span:has-text("Yes"), span:has-text("No")').first
                own_chassis = chassis_elem.inner_text().strip() if chassis_elem.count() > 0 else ""

                # Extract status - in bold firebright span
                status_elem = row.locator('span.bold.firebright').first
                status = status_elem.inner_text().strip() if status_elem.count() > 0 else ""

                # Parse slot datetime
                slot_dt = None
                if slot_text:
                    try:
                        slot_dt = datetime.strptime(slot_text, "%m/%d/%Y, %H:%M")
                    except:
                        try:
                            slot_dt = datetime.strptime(slot_text.strip(), "%m/%d/%Y, %H:%M")
                        except:
                            pass

                appointments.append({
                    "apm_appointment_id": appt_num,
                    "apm_slot": slot_dt.isoformat() if slot_dt else None,
                    "apm_truck": truck_text,
                    "apm_type": appt_type,
                    "apm_status": status,
                    "container_id": container_id,
                    "line_op": line_op,
                    "cargo_ref": cargo_ref,
                    "equip_size": size,
                    "own_chassis": own_chassis,
                    "terminal": TERMINAL,
                    "company_name": COMPANY_NAME,
                })

            except Exception as e:
                print(f"Error parsing row: {e}")
                continue

    except Exception as e:
        print(f"Error finding appointment rows: {e}")

    return appointments


def scrape():
    """Main scraper function."""
    print(f"🔍 Starting APM scraper for {TERMINAL}...")

    if not APM_USERNAME or not APM_PASSWORD:
        print("❌ Error: APM_USERNAME and APM_PASSWORD environment variables required")
        sys.exit(1)

    # Connect to Supabase
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    with sync_playwright() as p:
        # Launch browser (headless)
        browser = p.chromium.launch(
            headless=True,
            executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "/usr/bin/chromium"),
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        print("🌐 Logging into TERMPoint...")

        # Go to login page
        page.goto("https://termpoint.apmterminals.com/")
        page.wait_for_load_state("networkidle")

        # Fill in login form
        page.fill('input[name="Login_Nm"]', APM_USERNAME)
        page.fill('input[name="Login_Pwd"]', APM_PASSWORD)

        # Set up console message capture before clicking
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        # Click the login button
        page.click('button[class*="LoginButton"]')

        # Wait for any response from the server
        time.sleep(3)

        # Check what happened
        print(f"   Console messages: {console_messages[:5]}")

        # Wait for navigation after login
        time.sleep(5)

        current_url = page.url
        print(f"   URL after login attempt: {current_url}")

        if "dashboard" in current_url or page.query_selector('text=LasieLogistics'):
            print("✅ Logged in successfully")
        else:
            # Try clicking again and waiting
            page.screenshot(path="/app/login_debug.png")
            with open("/app/login_debug.html", "w") as f:
                f.write(page.content())
            print(f"⚠️ Login may have failed. Current URL: {current_url}")
            print(f"   Screenshot: /app/login_debug.png")

        # Go to My Appointments
        print("📋 Fetching My Appointments...")
        page.goto("https://termpoint.apmterminals.com/MyAppointments")
        page.wait_for_load_state("networkidle")

        # Wait for grid to load
        page.wait_for_selector('[name="multigrid"]', timeout=10000)

        # Parse appointments
        appointments = parse_appointments(page)
        print(f"📊 Found {len(appointments)} appointments")

        if appointments:
            # Upsert to Supabase
            print("💾 Pushing to Supabase...")
            for apt in appointments:
                try:
                    # Upsert: insert or update on (terminal, apm_appointment_id)
                    response = supabase.table("port_appointments").upsert(
                        apt,
                        on_conflict="terminal,apm_appointment_id"
                    ).execute()
                    print(f"  ✓ {apt['apm_appointment_id']} - {apt['container_id']}")
                except Exception as e:
                    print(f"  ✗ Error upserting {apt.get('apm_appointment_id')}: {e}")

            print(f"✅ Successfully synced {len(appointments)} appointments")
        else:
            print("⚠️ No appointments found")

        browser.close()


if __name__ == "__main__":
    scrape()
