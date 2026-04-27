import httpx, json
from apm_client import APMClient, APMApiError

client = APMClient()

print("=== Test: Auth ===")
try:
    jwt = client._get_termpoint_jwt()
    print(f"  JWT OK: {jwt[:40]}...")
except Exception as e:
    print(f"  FAILED: {e}")

print("\n=== Test: get_slots (IP, Apr 20) ===")
try:
    slots = client.get_slots("APMLA", "2026-04-20", "2026-04-21", "IP")
    print(f"  Got {len(slots)} slots")
    for s in slots[:5]:
        print(f"    {s.slot_from} - {s.slot_to} | {s.appointment_type} | available: {s.available}")
except APMApiError as e:
    print(f"  APMApiError: {e}")

print("\n=== Test: list_appointments (Apr window) ===")
try:
    appts = client.list_appointments("APMLA", "2026-04-01T00:00:00", "2026-04-19T23:00:00")
    print(f"  Got {len(appts)} appointments")
    for a in appts[:5]:
        print(f"    {a.appointment_id} | {a.appointment_type} | {a.status} | {a.container_id}")
except APMApiError as e:
    print(f"  APMApiError: {e}")

print("\n=== Test: get_slots (no type - Apr 20) ===")
try:
    slots2 = client.get_slots("APMLA", "2026-04-20", "2026-04-21")
    print(f"  Got {len(slots2)} slots")
except APMApiError as e:
    print(f"  APMApiError: {e}")

print("\n=== Test: to_port_appointment ===")
from apm_client import APMAppointment
test_apt = APMAppointment(
    appointment_id="TEST-123",
    terminal="APMLA",
    slot_from="2026-04-20T10:00",
    slot_to="2026-04-20T12:00",
    truck="ABC123",
    container_id="MSKU1234567",
    appointment_type="IP",
    status="C",
    line_op="MSKU",
    cargo_ref="CR-456",
    equip_size="40",
    own_chassis="Y",
)
port_fmt = client.to_port_appointment(test_apt)
print(f"  {port_fmt}")