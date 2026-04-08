#!/usr/bin/env python3
"""Test APM API credentials."""
import os

os.environ["ADMIRAL_CONSUMER_KEY"] = "3J0JyqZ5sQLmvsyldDyno7yC1AdR3Wci"
os.environ["ADMIRAL_CLIENT_SECRET"] = "yF2QO4yyJ5dP7VRs"
os.environ["APIGEE_CONSUMER_KEY"] = "bNaDGd6n5ioW7c2oVoFBs6GbAONswtPl"
os.environ["APIGEE_CONSUMER_SECRET"] = "AAxFgeakN5ZXWyHx"
os.environ["MAERSK_HOST"] = "https://api-stage.maersk.com"
os.environ["APM_HOST"] = "https://api-stage.apmterminals.com"

from apm_client import APMClient, APMApiError

client = APMClient()

print("Step 1: Getting Maersk ForgeRock token...")
try:
    token = client._get_forgerock_token()
    print(f"  ✓ Got token: {token[:40]}...")
except APMApiError as e:
    print(f"  ✗ Failed: {e}")
    exit(1)

print("\nStep 2: Getting Termpoint JWT...")
try:
    jwt = client._get_termpoint_jwt()
    print(f"  ✓ Got JWT: {jwt[:60]}...")
except APMApiError as e:
    print(f"  ✗ Failed: {e}")
    exit(1)

print("\nStep 3: Listing appointments (USLAX)...")
try:
    appts = client.list_appointments("USLAX")
    print(f"  ✓ Found {len(appts)} appointments")
    for a in appts[:5]:
        print(f"    - {a.appointment_id}: {a.container_id} | {a.appointment_type} | {a.status}")
except APMApiError as e:
    print(f"  ✗ Failed: {e}")

print("\nDone.")
