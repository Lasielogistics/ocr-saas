import httpx, json
from apm_client import APMClient
client = APMClient()
headers = client._headers()
url = f'{client.APM_HOST}/termpoint-tms/api/MyAppointment/GetAvailableTimeSlots'
payload = {
    'gateAppt_Dt': '2026-04-20',
    'gateApptEnd_DtTm': '2026-04-21',
    'apptType_Cd': 'IP',
    'gateAppt_Id': '',
    'gateApptStart_Tm': '',
    'container_Num': '',
    'cargoRef_Num': '',
    'con_Cd': 'APMLA',
    'shippingLine_Cd': '',
    'reefer_Flg': '',
    'hazmat_Flg': '',
    'oD_Flg': '',
}
with httpx.Client(timeout=30) as c:
    resp = c.post(url, json=payload, headers=headers)
text = resp.text
print('resp.text repr:', repr(text[:200]))
print('First char:', repr(text[0]))
print('Is it a JSON string (starts with quote)?', text.startswith('"'))
# Double decode
d1 = json.loads(text)
print('After first json.loads, type:', type(d1), '| value:', str(d1)[:200])
if isinstance(d1, str):
    d2 = json.loads(d1)
    print('After second json.loads, type:', type(d2), '| keys:', list(d2.keys()) if isinstance(d2, dict) else d2)