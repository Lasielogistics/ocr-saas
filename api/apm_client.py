"""
APM Terminals TERMPoint API Client
Two-step auth: Maersk OAuth → Termpoint JWT
"""

import os
import time
from typing import Optional
from dataclasses import dataclass
import httpx


@dataclass
class APMSlot:
    terminal: str
    slot_from: str
    slot_to: str
    appointment_type: str
    available: int


@dataclass
class APMAppointment:
    appointment_id: str
    terminal: str
    slot_from: Optional[str]
    slot_to: Optional[str]
    truck: Optional[str]
    container_id: Optional[str]
    appointment_type: str
    status: str
    line_op: Optional[str]
    cargo_ref: Optional[str]
    equip_size: Optional[str]
    own_chassis: Optional[str]


class APMApiError(Exception):
    pass


class APMClient:
    """Client for APM Terminals TERMPoint API using two-step auth."""

    # Auth endpoints
    MAERSK_HOST = os.getenv("MAERSK_HOST", "https://api.maersk.com")
    APM_HOST = os.getenv("APM_HOST", "https://api.apmterminals.com")

    # Credentials
    ADMIRAL_KEY = os.getenv("ADMIRAL_CONSUMER_KEY", "")
    ADMIRAL_SECRET = os.getenv("ADMIRAL_CLIENT_SECRET", "")
    APIGEE_KEY = os.getenv("APIGEE_CONSUMER_KEY", "6hDTGeEAQIdlXMlpghyb4ETgUU7tp56m")
    APIGEE_SECRET = os.getenv("APIGEE_CONSUMER_SECRET", "nrhk7tD18u4fTEDw")
    FORGEROCK_TOKEN = os.getenv("FORGEROCK_TOKEN", "")  # Optional: provide pre-obtained ForgeRock token directly

    def __init__(self):
        self._forgerock_token: Optional[str] = None
        self._forgerock_expires_at: float = 0
        self._termpoint_jwt: Optional[str] = None
        self._termpoint_jwt_expires_at: float = 0
        # Track if we're using production auth (no ForgeRock needed)
        self._production_auth = "api-stage" not in self.APM_HOST

    def _get_forgerock_token(self) -> str:
        """Step 1: Get Maersk OAuth / ForgeRock token."""
        # Production mode: ForgeRock token may not be needed
        if self._production_auth and not self.FORGEROCK_TOKEN and not self.ADMIRAL_KEY:
            return ""

        # Use pre-configured token if available (bypasses Maersk OAuth)
        if self.FORGEROCK_TOKEN:
            self._forgerock_token = self.FORGEROCK_TOKEN
            self._forgerock_expires_at = time.time() + 86400  # trust it for 24h
            return self._forgerock_token

        if self._forgerock_token and time.time() < self._forgerock_expires_at - 60:
            return self._forgerock_token

        if not self.ADMIRAL_KEY or not self.ADMIRAL_SECRET:
            raise APMApiError("ADMIRAL_CONSUMER_KEY / ADMIRAL_CLIENT_SECRET not configured")

        url = f"{self.MAERSK_HOST}/oauth2/access_token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.ADMIRAL_KEY,
            "client_secret": self.ADMIRAL_SECRET,
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(url, data=data)

        if response.status_code != 200:
            raise APMApiError(f"Maersk auth failed ({response.status_code}): {response.text}")

        token = response.json().get("access_token")
        if not token:
            raise APMApiError("No access_token in Maersk response")

        self._forgerock_token = token
        # Maersk tokens typically expire in 7200s (2h)
        self._forgerock_expires_at = time.time() + 7200
        return token

    def _get_termpoint_jwt(self) -> str:
        """Step 2: Get Termpoint JWT using ForgeRock token."""
        if self._termpoint_jwt and time.time() < self._termpoint_jwt_expires_at - 60:
            return self._termpoint_jwt

        if not self.APIGEE_KEY:
            raise APMApiError("APIGEE_CONSUMER_KEY not configured")

        forgerock = self._get_forgerock_token()

        url = f"{self.APM_HOST}/termpoint-tms/api/Login/AuthenticateUser"
        headers = {
            "Consumer-Key": self.APIGEE_KEY,
            "Content-Type": "application/json",
        }
        if forgerock:
            headers["Authorization"] = f"Bearer {forgerock}"

        payload = {"authenticationKey": None}

        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            raise APMApiError(f"Termpoint auth failed ({response.status_code}): {response.text}")

        json_data = response.json()
        # Response structure: { "res": { "getBody": { "ResponseData": { "AccessToken": "..." } } } }
        try:
            token = json_data["res"]["getBody"]["ResponseData"]["AccessToken"]
        except (KeyError, TypeError):
            # Try flat structure
            token = json_data.get("res", {}).get("AccessToken", "")
            if not token:
                raise APMApiError(f"Could not parse Termpoint JWT from: {json_data}")

        self._termpoint_jwt = token
        # Termpoint JWTs typically expire in ~1h
        self._termpoint_jwt_expires_at = time.time() + 3600
        return token

    def _headers(self) -> dict:
        """Build headers for authenticated API requests."""
        headers = {
            "Consumer-Key": self.APIGEE_KEY,
            "Termpoint-JWT": f"JWT {self._get_termpoint_jwt()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        forgerock = self._get_forgerock_token()
        if forgerock:
            headers["Authorization"] = f"Bearer {forgerock}"
        return headers

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated API request."""
        url = f"{self.APM_HOST}/termpoint-tms/api{path}"
        headers = self._headers()

        with httpx.Client(timeout=30) as client:
            response = client.request(method, url, headers=headers, **kwargs)

        if response.status_code >= 400:
            raise APMApiError(f"API error {response.status_code}: {response.text}")

        return response.json() if response.text else {}

    # ─── Appointments ───────────────────────────────────────────

    def get_slots(
        self,
        terminal: str,
        from_date: str,
        to_date: str,
        appointment_type: Optional[str] = None,
    ) -> list[APMSlot]:
        """Get available time slots for a terminal."""
        payload = {
            "gateAppt_Dt": from_date,
            "gateApptEnd_DtTm": to_date,
            "apptType_Cd": appointment_type or "",
            "gateAppt_Id": "",
            "gateApptStart_Tm": "",
            "container_Num": "",
            "cargoRef_Num": "",
            "con_Cd": "",
            "shippingLine_Cd": "",
            "reefer_Flg": "",
            "hazmat_Flg": "",
            "oD_Flg": "",
        }
        data = self._request("POST", "/MyAppointment/GetAvailableTimeSlots", json=payload)
        slots = []
        items = data.get("res", {}).get("getBody", {}).get("ResponseData", [])
        for item in items:
            slots.append(APMSlot(
                terminal=terminal,
                slot_from=item.get("slotFrom", ""),
                slot_to=item.get("slotTo", ""),
                appointment_type=item.get("appointmentType", ""),
                available=item.get("available", 0),
            ))
        return slots

    def list_appointments(
        self,
        terminal: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> list[APMAppointment]:
        """List appointments for a terminal."""
        # Default to ~30 day window if not specified
        from_dt = from_date or "2026-03-01T00:00:00"
        to_dt = to_date or "2026-04-30T23:00:00"
        payload = {
            "gateApptStart_DtTm": from_dt,
            "gateApptEnd_DtTm": to_dt,
            "apptType_Cd": "",
            "truckPlate_Nbr": "",
            "apptStatus_Cd": "",
            "cargoRef_Num": "",
            "container_Num": "",
        }
        data = self._request("POST", "/MyAppointment/GetTruckerAppointments", json=payload)
        appointments = []
        items = data.get("res", {}).get("getBody", {}).get("ResponseData", [])
        for item in items:
            appointments.append(self._parse_appointment(item, terminal))
        return appointments

    def get_appointment(self, terminal: str, appointment_id: str) -> APMAppointment:
        """Get specific appointment details."""
        data = self._request("POST", "/MyAppointment/GetGateAppointmentDetails",
                             json={"gateAppt_Id": appointment_id})
        item = data.get("res", {}).get("getBody", {}).get("ResponseData", {})
        return self._parse_appointment(item, terminal)

    def create_appointment(
        self,
        terminal: str,
        slot_from: str,
        slot_to: str,
        appointment_type: str,
        container_id: Optional[str] = None,
        truck: Optional[str] = None,
        line_op: Optional[str] = None,
        cargo_ref: Optional[str] = None,
        equip_size: Optional[str] = None,
        own_chassis: Optional[str] = None,
    ) -> APMAppointment:
        """Create a new appointment."""
        # Parse date and time from slot_from (ISO format: 2026-04-03T14:00)
        date_part = slot_from.split("T")[0] if "T" in slot_from else slot_from
        time_part = slot_from.split("T")[1].replace(":", "")[:4] if "T" in slot_from else slot_from

        payload = [{
            "gateApptStart_Tm": time_part[:4],
            "gateAppt_Dt": f"{date_part}T00:00:00",
            "driverId_Num": "",
            "driverOwnChs_Flg": "Y" if own_chassis else "N",
            "truckPlate_Nbr": truck or "",
            "cargoRef_Num": cargo_ref or "",
            "cargoRefType_Cd": "",
            "shippingLine_Cd": line_op or "",
            "container_Num": container_id or "",
            "chassis_Num": "",
            "genset_Num": "",
            "con_Cd": terminal,
            "reefer_Flg": "",
            "hazmat_Flg": "",
            "oD_Flg": "",
            "vgmSubmitted_Flg": "",
            "seal1_Num": "",
            "seal2_Num": "",
            "apptType_Cd": appointment_type,
            "position_On_Truck": 0,
        }]
        data = self._request("POST", "/MyAppointment/PostCreateAppointment", json=payload)
        item = data.get("res", {}).get("getBody", {}).get("ResponseData", {})
        return self._parse_appointment(item, terminal)

    def cancel_appointment(self, terminal: str, appointment_id: str) -> bool:
        """Cancel an appointment."""
        payload = [{"gateAppt_Id": appointment_id, "apptStatusCd": "CA"}]
        self._request("POST", "/MyAppointment/PostCancelAppointment", json=payload)
        return True

    def _parse_appointment(self, item: dict, terminal: str) -> APMAppointment:
        """Parse APM appointment data into APMAppointment dataclass."""
        return APMAppointment(
            appointment_id=str(item.get("gateAppt_Id", item.get("appointmentId", ""))),
            terminal=terminal,
            slot_from=item.get("gateAppt_Dt", ""),
            slot_to=item.get("gateAppt_EndDtTm", ""),
            truck=item.get("truckPlate_Nbr"),
            container_id=item.get("container_Num"),
            appointment_type=item.get("apptType_Cd", ""),
            status=item.get("apptStatus_Cd", ""),
            line_op=item.get("shippingLine_Cd"),
            cargo_ref=item.get("cargoRef_Num"),
            equip_size=item.get("equipSize_Cd"),
            own_chassis=item.get("driverOwnChs_Flg"),
        )

    def to_port_appointment(self, apt: APMAppointment, company_name: str = "Lasielogistics") -> dict:
        """Convert APMAppointment to port_appointments table format."""
        return {
            "apm_appointment_id": apt.appointment_id,
            "apm_slot": apt.slot_from,
            "apm_truck": apt.truck,
            "apm_type": apt.appointment_type,
            "apm_status": apt.status,
            "container_id": apt.container_id,
            "line_op": apt.line_op,
            "cargo_ref": apt.cargo_ref,
            "equip_size": apt.equip_size,
            "own_chassis": apt.own_chassis,
            "terminal": apt.terminal,
            "company_name": company_name,
        }


# Singleton instance
apm_client = APMClient()
