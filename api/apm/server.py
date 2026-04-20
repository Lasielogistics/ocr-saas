#!/usr/bin/env python3
"""
Pure Python HTTP server for TERMPoint TMS Web Client
Uses only stdlib + requests (no Flask needed)
"""

import json
import re
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# Credentials (PRODUCTION)
ADMIRAL_CONSUMER_KEY = "6hDTGeEAQIdlXMlpghyb4ETgUU7tp56m"
ADMIRAL_CLIENT_SECRET = "nrhk7tD18u4fTEDw"
APIGEE_CONSUMER_KEY = "6hDTGeEAQIdlXMlpghyb4ETgUU7tp56m"
APIGEE_CONSUMER_SECRET = "nrhk7tD18u4fTEDw"
TERMPOINT_AUTH_KEY = "0CZ44ZVYfUFTqG2svDQuPEAIDSD5MPWksRA0MiB9BT0ZwhKKDH1eaRBGuQnoQN8A"

MAERSK_HOST = "api.maersk.com"
TERMPOINT_HOST = "api.apmterminals.com"


def get_auth_tokens():
    """Get both IAM and Termpoint tokens"""
    iam_resp = requests.post(
        f"https://{MAERSK_HOST}/oauth2/access_token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={
            "grant_type": "client_credentials",
            "client_id": ADMIRAL_CONSUMER_KEY,
            "client_secret": ADMIRAL_CLIENT_SECRET,
        },
        timeout=15,
    )
    iam_resp.raise_for_status()
    forgerock_token = iam_resp.json().get("access_token")

    auth_resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/Login/AuthenticateUser",
        headers={
            "Content-Type": "application/json",
            "Consumer-Key": APIGEE_CONSUMER_KEY,
            "Authorization": f"Bearer {forgerock_token}",
        },
        json={"authenticationKey": TERMPOINT_AUTH_KEY},
        timeout=15,
    )
    auth_resp.raise_for_status()
    auth_data = auth_resp.json()
    status_code = auth_data.get("status", {}).get("StatusCode")
    if status_code != 200:
        raise Exception(f"Auth failed: {auth_data}")
    jwt = auth_data.get("responseBody", {}).get("ResponseData", {}).get("AccessToken")
    terminal = auth_data.get("responseBody", {}).get("ResponseData", {}).get("User", {}).get(" trucking_company", "Pier 400")
    return forgerock_token, jwt, terminal


def _tms_headers(fr, jwt):
    return {
        "Content-Type": "application/json",
        "Consumer-Key": APIGEE_CONSUMER_KEY,
        "Authorization": f"Bearer {fr}",
        "Termpoint-JWT": f"JWT {jwt}",
    }


def _flatten_appointments(appts_raw):
    appts = []
    for entry in appts_raw:
        for g in entry.get("GateAppointment", []):
            appts.append({
                "gateAppt_Id": g.get("GateAppt_Id"),
                "gateAppt_Num": g.get("GateAppt_Num"),
                "gateAppt_Dt": g.get("GateAppt_Dt", "")[:10],
                "gateApptStart_Tm": g.get("Slot_Tm", ""),
                "container_Num": g.get("Container_Num"),
                "apptType_Cd": g.get("ApptType_Cd"),
                "apptStatus_Cd": g.get("ApptStatus_Cd"),
                "driverId_Num": g.get("DriverID_Num"),
                "driver_Nm": g.get("Driver_Nm"),
                "truckPlate_Nbr": g.get("TruckPlate_Nbr"),
                "shippingLine_Cd": g.get("Line_Id"),
                "con_Cd": g.get("Con_Cd"),
            })
    return appts


# ─── Endpoints ────────────────────────────────────────────────────────────────

def handle_auth():
    fr, jwt, terminal = get_auth_tokens()
    return {"iam_token": fr, "jwt": jwt, "terminal": terminal}


def handle_slots(body):
    date = body.get("date", "")
    appt_type = body.get("type", "IP")
    container = body.get("container", "")
    fr, jwt, _ = get_auth_tokens()

    resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/GetAvailableTimeSlots",
        headers=_tms_headers(fr, jwt),
        json={
            "gateAppt_Dt": f"{date}T00:00:00",
            "apptType_Cd": appt_type,
            "gateAppt_Id": "",
            "gateApptStart_Tm": "",
            "container_Num": container,
            "cargoRef_Num": "",
            "con_Cd": "",
            "shippingLine_Cd": "",
            "reefer_Flg": "",
            "hazmat_Flg": "",
            "oD_Flg": "",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    available_slots = data.get("responseBody", {}).get("ResponseData", {}).get("AvailableSlots", [])
    return {
        "slots": [{"time": s.get("Slot_Tm", ""), "id": s.get("SlotSchedule_Id", "")} for s in available_slots],
        "terminal": data.get("responseBody", {}).get("TerminalInfo", {}).get("MTO_Nm", ""),
    }


def handle_appointments(body):
    from_date = body.get("from", "")
    to_date = body.get("to", "")
    fr, jwt, _ = get_auth_tokens()

    resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/GetTruckerAppointments",
        headers=_tms_headers(fr, jwt),
        json={
            "gateApptStart_DtTm": f"{from_date}T00:00:00",
            "gateApptEnd_DtTm": f"{to_date}T23:00:00",
            "apptType_Cd": "",
            "truckPlate_Nbr": "",
            "apptStatus_Cd": "",
            "cargoRef_Num": "",
            "container_Num": "",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    appts_raw = data.get("responseBody", {}).get("ResponseData", {}).get("TruckVisitAppointment", [])
    return {
        "appointments": _flatten_appointments(appts_raw),
        "terminal": data.get("responseBody", {}).get("TerminalInfo", {}).get("MTO_Nm", ""),
    }


def handle_create(body):
    date = body.get("date", "")
    appt_type = body.get("type", "MD")
    time = body.get("time", "23:00")
    container = body.get("container", "")
    own_chassis = body.get("ownChassis", "Y")
    position = body.get("position", 0)

    fr, jwt, _ = get_auth_tokens()

    resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/PostCreateAppointment",
        headers=_tms_headers(fr, jwt),
        json=[{
            "gateApptStart_Tm": time,
            "gateAppt_Dt": f"{date}T00:00:00",
            "driverId_Num": "",
            "driverOwnChs_Flg": own_chassis,
            "truckPlate_Nbr": "",
            "cargoRef_Num": "",
            "cargoRefType_Cd": "",
            "shippingLine_Cd": "",
            "container_Num": container,
            "chassis_Num": "",
            "genset_Num": "",
            "con_Cd": "",
            "reefer_Flg": "",
            "hazmat_Flg": "",
            "oD_Flg": "",
            "vgmSubmitted_Flg": "",
            "seal1_Num": "",
            "seal2_Num": "",
            "apptType_Cd": appt_type,
            "position_On_Truck": int(position),
        }],
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    appts_raw = data.get("responseBody", {}).get("ResponseData", {}).get("TruckVisitAppointment", [])
    appts = _flatten_appointments(appts_raw)
    appt_id = appts[0].get("gateAppt_Id", "") if appts else ""
    return {"appointmentId": appt_id, "appointments": appts}


def handle_cancel(body):
    """Cancel one or more appointments by GateAppt_Id"""
    ids = body.get("gateApptIds", [])
    if not ids:
        raise Exception("gateApptIds is required (array of numbers)")
    fr, jwt, _ = get_auth_tokens()

    resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/PostCancelAppointment",
        headers=_tms_headers(fr, jwt),
        json=[{"gateAppt_Id": int(id)} for id in ids],
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    msgs = data.get("responseBody", {}).get("UserMessages", [])
    return {
        "success": True,
        "messages": [{"no": m.get("MessageNo"), "desc": m.get("MessageDescription"), "severity": m.get("MessageSeverity")} for m in msgs],
        "data": data,
    }


def handle_manage(body):
    """Update an appointment (reassign driver/truck/slot)"""
    gate_id = body.get("gateAppt_Id")
    if not gate_id:
        raise Exception("gateAppt_Id is required")
    fr, jwt, _ = get_auth_tokens()

    payload = {"gateAppt_Id": int(gate_id)}
    # Optional update fields
    for field in ["driverId_Num", "truckPlate_Nbr", "gateApptStart_Tm", "gateAppt_Dt", "driverOwnChs_Flg", "apptType_Cd"]:
        if body.get(field):
            payload[field] = body[field]

    resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/PostManageAppointment",
        headers=_tms_headers(fr, jwt),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    appts_raw = data.get("responseBody", {}).get("ResponseData", {}).get("TruckVisitAppointment", [])
    appts = _flatten_appointments(appts_raw)
    msgs = data.get("responseBody", {}).get("UserMessages", [])
    return {
        "appointments": appts,
        "messages": [{"no": m.get("MessageNo"), "desc": m.get("MessageDescription"), "severity": m.get("MessageSeverity")} for m in msgs],
    }


def handle_container_availability(body):
    """Check availability for import containers"""
    container_nums = body.get("containerNums", [])
    if not container_nums:
        raise Exception("containerNums is required (array of container numbers)")
    fr, jwt, _ = get_auth_tokens()

    resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/GetContainerAvailability",
        headers=_tms_headers(fr, jwt),
        json=[{"Container_Num": c} for c in container_nums],
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    containers = data.get("responseBody", {}).get("ResponseData", [])
    msgs = data.get("responseBody", {}).get("UserMessages", [])
    return {
        "containers": containers,
        "messages": [{"no": m.get("MessageNo"), "desc": m.get("MessageDescription"), "severity": m.get("MessageSeverity")} for m in msgs],
    }


def handle_empty_availability(body):
    """Get empty appointment availability (MD/MP)"""
    date = body.get("date", "")
    appt_type = body.get("type", "MD")
    if not date:
        raise Exception("date is required (yyyy-mm-dd)")
    fr, jwt, _ = get_auth_tokens()

    resp = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/GetEmptyAppointmentAvailability",
        headers=_tms_headers(fr, jwt),
        json={
            "gateAppt_Dt": date,
            "apptType_Cd": appt_type,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    slots = data.get("responseBody", {}).get("ResponseData", {}).get("RG_EmptyApptAvailability", [])
    msgs = data.get("responseBody", {}).get("UserMessages", [])
    return {
        "slots": [{
            "id": s.get("ApptSlotSchedule_Id"),
            "time": s.get("Slot_Tm", ""),
            "total": s.get("TotalNbrOfSlots"),
            "appointments": s.get("TotalNbrOfAppts"),
            "available": s.get("TotalNbrOfAvailableSlots"),
        } for s in slots],
        "messages": [{"no": m.get("MessageNo"), "desc": m.get("MessageDescription"), "severity": m.get("MessageSeverity")} for m in msgs],
    }


# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.log_time()}] {args[0]}")

    def log_time(self):
        import time
        return time.strftime("%H:%M:%S")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/termpoint_web.html" or self.path == "/termpoint.html":
            self.path = "/termpoint_web.html"
        try:
            with open(f".{self.path}", "rb") as f:
                body = f.read()
            ext = self.path.split(".")[-1]
            ctype = {"html": "text/html", "css": "text/css", "js": "application/javascript"}.get(ext, "text/plain")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(404, "File not found")

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len) if content_len else b"{}"
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        path = urllib.parse.urlparse(self.path).path

        try:
            if path == "/auth":
                result = handle_auth()
            elif path == "/slots":
                result = handle_slots(data)
            elif path == "/appointments":
                result = handle_appointments(data)
            elif path == "/create":
                result = handle_create(data)
            elif path == "/cancel":
                result = handle_cancel(data)
            elif path == "/manage":
                result = handle_manage(data)
            elif path == "/container-availability":
                result = handle_container_availability(data)
            elif path == "/empty-availability":
                result = handle_empty_availability(data)
            else:
                self.send_json({"error": f"Unknown endpoint: {path}"}, 404)
                return
            self.send_json(result)
        except requests.HTTPError as e:
            try:
                err_data = e.response.json()
                msgs = err_data.get("responseBody", {}).get("UserMessages", [])
                error = msgs[0].get("MessageDescription", str(err_data)) if msgs else str(err_data)
            except Exception:
                error = str(e)
            self.send_json({"error": error}, 400)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)


if __name__ == "__main__":
    print("=== TERMPoint TMS Web Server ===")
    print("Open: http://localhost:8000")
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()
