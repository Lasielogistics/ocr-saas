import httpx, json

forgerock = 'eyJ0eXAiOiJKV1QiLCJraWQiOiJHRkFMUWtWTzFvNFc3YXpweWJ6RjhrOE4wdEk9IiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiI2aERUR2VFQVFJZGxYTWxwZ2h5YjRFVGdVVTd0cDU2bSIsImN0cyI6Ik9BVVRIMl9TVEFURUxFU1NfR1JBTlQiLCJhdWRpdFRyYWNraW5nSWQiOiI0NzM0MGQ4Zi1iODlhLTQ1ZTQtOTRlMi05MDEyMmMxZGUzOGYtNDcyNDQ4NzEiLCJzdWJuYW1lIjoiNmhEVEdlRUFRSWRsWE1scGdoeWI0RVRnVVU3dHA1Nm0iLCJpc3MiOiJodHRwczovL2lhbS5tYWVyc2suY29tL2FjbS9vYXV0aDIvbWF1IiwidG9rZW5OYW1lIjoiYWNjZXNzX3Rva2VuIiwidG9rZW5fdHlwZSI6IkJlYXJlciIsImF1dGhHcmFudElkIjoiQkdpU3I4eFJnSmFXU3NQT2lmOV9WaXAtWkJ3IiwiYXVkIjoiNmhEVEdlRUFRSWRsWE1scGdoeWI0RVRnVVU3dHA1Nm0iLCJuYmYiOjE3NzY2NDYyMjQsImdyYW50X3R5cGUiOiJjbGllbnRfY3JlZGVudGlhbHMiLCJzY29wZSI6WyJvcGVuaWQiXSwiYXV0aF90aW1lIjoxNzc2NjQ2MjI0LCJyZWFsbSI6Ii9tYXUiLCJleHAiOjE3NzY2NTM0MjQsImlhdCI6MTc3NjY0NjIyNCwiZXhwaXJlc19pbiI6NzIwMCwianRpIjoiME5GNURpYUVUVENLTDhHSTVzU1ZMd1Z4NEJRIn0.Er9a4rBcPC96sSiqEoDjriVfwKY2yYobc1eX78EI9osPlw9rDEmnCmkC7VI4WtuKBNaLrM-AVODybadadr9wBwtDP_1a3hbEmvE2f7j2Jz7GHjiWVRnHSTG4n2MNcgMNBcw1osBt5k_4E7l_hmJfjn61QwY1d4vW9iWcd4vJ7HNxSBUt5acGToZZ75aF-lXD9lRWeXuP1awORwgWPp6Ti_E_Ws_1K10uiySfxMdebMVcomT6dtGeUUWtCMTkYzXSMy6_4NSdaopvjrhocbbtRMglHKUSGm47t-uxrWMOmoo4drJvsdZw5FY0aGE5r0XvSWUOD8gPTeIjnFdwtoQV1w'
auth_key = '0CZ44ZVYfUFTqG2svDQuPEAIDSD5MPWksRA0MiB9BT0ZwhKKDH1eaRBGuQnoQN8A'

# Test 1: Health or root endpoint
print("=== Test 1: Root endpoint ===")
try:
    with httpx.Client(timeout=15) as c:
        r = c.get('https://api.apmterminals.com/')
    print('Status:', r.status_code, r.text[:200])
except Exception as e:
    print('Error:', e)

# Test 2: Auth endpoint
print("\n=== Test 2: AuthenticateUser ===")
url = 'https://api.apmterminals.com/termpoint-tms/api/Login/AuthenticateUser'
headers = {
    'Consumer-Key': '6hDTGeEAQIdlXMlpghyb4ETgUU7tp56m',
    'Authorization': f'Bearer {forgerock}',
    'Content-Type': 'application/json',
}
payload = {'authenticationKey': auth_key}
with httpx.Client(timeout=15) as c:
    r = c.post(url, json=payload, headers=headers)
print('Status:', r.status_code, r.text[:300])

# Test 3: Appointments without JWT (just Consumer-Key)
print("\n=== Test 3: GetTruckerAppointments (no JWT) ===")
url3 = 'https://api.apmterminals.com/termpoint-tms/api/MyAppointment/GetTruckerAppointments'
headers3 = {'Consumer-Key': '6hDTGeEAQIdlXMlpghyb4ETgUU7tp56m', 'Content-Type': 'application/json'}
payload3 = {'gateApptStart_DtTm': '2026-04-01T00:00:00', 'gateApptEnd_DtTm': '2026-04-20T23:00:00', 'apptType_Cd': '', 'truckPlate_Nbr': '', 'apptStatus_Cd': '', 'cargoRef_Num': '', 'container_Num': '', 'con_Cd': 'APMLA'}
with httpx.Client(timeout=15) as c:
    r3 = c.post(url3, json=payload3, headers=headers3)
print('Status:', r3.status_code, r3.text[:300])