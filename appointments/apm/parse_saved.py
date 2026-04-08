#!/usr/bin/env python3
"""
APM Appointments Parser
Tests parsing logic against saved HTML pages
"""

import re
from datetime import datetime
from pathlib import Path

# Path to saved pages
SAVED_DIR = Path("/data/projects/tms/appointments/apm/saved_pages")

# Terminal name
TERMINAL = "APM"
COMPANY_NAME = "Lasielogistics"


def parse_appointments_from_html(html_content):
    """Parse appointments from My Appointments HTML page."""
    appointments = []

    # Find all appointment numbers and their positions
    appt_matches = list(re.finditer(r'class="clearpadding">(\d+)</a>', html_content))
    print(f"Found {len(appt_matches)} appointments")

    for i, appt_match in enumerate(appt_matches):
        try:
            appt_num = appt_match.group(1)
            # Start of this appointment's HTML block
            start_pos = appt_match.start()
            # End is start of next appointment (or end of HTML)
            end_pos = appt_matches[i+1].start() if i+1 < len(appt_matches) else len(html_content)

            # Extract chunk for this appointment only
            chunk = html_content[start_pos:end_pos]

            # Extract slot and truck - these are in the same div before multi-rows
            slot_match = re.search(r'Slot</span>[^<]*<b>([^<]+)</b>', chunk)
            truck_match = re.search(r'Truck</span>[^<]*<b>([^<]+)</b>', chunk)
            slot_text = slot_match.group(1).strip() if slot_match else ""
            truck_text = truck_match.group(1).strip() if truck_match else ""

            # Extract type - inside color-extra span in checkbox label
            type_match = re.search(r'<span class="color-extra">(IMPORT|EXPORT|EMPTY|CHASSIS)[^<]*</span>', chunk)
            appt_type = type_match.group(1) if type_match else ""

            # Extract container ID - either in anchor (IMPORT/EXPORT) or span (EMPTY/CHASSIS)
            container_match = re.search(r'<a href="javascript:void\(0\)">([A-Z]{4}[0-9]{7})</a>', chunk)
            if not container_match:
                # Try span format for EMPTY/CHASSIS appointments
                container_match = re.search(r'<span>([A-Z]{4}[0-9]{7})\s*</span>', chunk)
            container_id = container_match.group(1) if container_match else ""

            # Extract line op - text before <span class="color-extra"> inside span
            line_match = re.search(r'<span>(MAE|EGL|MSC|CMA|ONE|HPL|HMM|COS|ZIM|EMC)<span class="color-extra"></span></span>', chunk)
            line_op = line_match.group(1) if line_match else ""

            # Extract cargo ref - 9+ digit number
            cargo_match = re.search(r'<span>(\d{9,})\s*</span>', chunk)
            cargo_ref = cargo_match.group(1) if cargo_match else ""

            # Extract size - 40GP96 style pattern (digits + alphanumeric)
            size_match = re.search(r'<span>(\d{2}[A-Z0-9]{2,4})<span class="color-extra"></span></span>', chunk)
            size = size_match.group(1) if size_match else ""

            # Extract own chassis - Yes or No
            chassis_match = re.search(r'<span>(Yes|No)<span class="color-extra"></span></span>', chunk)
            own_chassis = chassis_match.group(1) if chassis_match else ""

            # Extract status - in bold firebright div
            status_match = re.search(r'<div class="column cell bold firebright[^>]*>.*?<span>([^<]+)<span class="color-extra"></span></span>', chunk, re.DOTALL)
            status = status_match.group(1) if status_match else ""

            # Parse slot datetime
            slot_dt = None
            if slot_text:
                try:
                    slot_dt = datetime.strptime(slot_text, "%m/%d/%Y, %H:%M")
                except:
                    pass

            appointment = {
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
            }

            appointments.append(appointment)
            print(f"  ✓ {appt_num}: {container_id} | {appt_type} | {slot_text} | {status}")

        except Exception as e:
            print(f"  Error parsing block: {e}")
            continue

    return appointments


def main():
    # Find the My Appointments saved page
    my_appt_file = SAVED_DIR / "3" / "My Appointments.html"

    if not my_appt_file.exists():
        print(f"Error: {my_appt_file} not found")
        return

    print(f"Reading {my_appt_file}")
    with open(my_appt_file, 'r', encoding='utf-8') as f:
        html = f.read()

    print(f"HTML length: {len(html)} chars")

    appointments = parse_appointments_from_html(html)

    print(f"\nTotal appointments found: {len(appointments)}")

    if appointments:
        print("\nFirst appointment:")
        for k, v in appointments[0].items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
