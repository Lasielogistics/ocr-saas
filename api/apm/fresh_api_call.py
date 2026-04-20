#!/usr/bin/env python3
"""
Termpoint TMS API - Fresh API Call
Based on Bruno collection: bruno/Termpoint-Tms APIs/

Auth flow:
1. OAuth2 client_credentials → Forgerock token
2. AuthenticateUser → Termpoint JWT
3. Use tokens for appointment APIs
"""

import json
import requests

# Credentials (STAGING - from apm keys.xlsx)
ADMIRAL_CONSUMER_KEY = "6hDTGeEAQIdlXMlpghyb4ETgUU7tp56m"
ADMIRAL_CLIENT_SECRET = "nrhk7tD18u4fTEDw"
APIGEE_CONSUMER_KEY = "6hDTGeEAQIdlXMlpghyb4ETgUU7tp56m"
TERMPOINT_AUTH_KEY = "bmP1alU4eDoVrYkD4SmrVWhZvFu3y5fuLBU/u3ZiVvU="

# Hosts (STAGING)
MAERSK_HOST = "api-stage.maersk.com"
TERMPOINT_HOST = "api-stage.apmterminals.com"


def get_iam_token() -> str:
    """Step 1: Get OAuth2 access token from IAM"""
    response = requests.post(
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
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise ValueError(f"No access_token in response: {data}")
    print(f"[OK] IAM token obtained")
    return token


def authenticate_user(forgerock_token: str) -> str:
    """Step 2: Authenticate with Termpoint to get JWT"""
    response = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/Login/AuthenticateUser",
        headers={
            "Content-Type": "application/json",
            "Consumer-Key": APIGEE_CONSUMER_KEY,
            "Authorization": f"Bearer {forgerock_token}",
        },
        json={"authenticationKey": TERMPOINT_AUTH_KEY},
    )
    response.raise_for_status()
    data = response.json()

    status_code = data.get("status", {}).get("StatusCode")
    if status_code != 200:
        raise ValueError(f"Auth failed with status {status_code}: {data}")

    token = data.get("responseBody", {}).get("ResponseData", {}).get("AccessToken")
    if not token:
        raise ValueError(f"No AccessToken in response: {data}")
    print(f"[OK] Termpoint JWT obtained")
    return token


def get_trucker_appointments(forgerock_token: str, termpoint_jwt: str) -> dict:
    """Get trucker appointments (from Bruno GetTruckerAppointments.bru)"""
    response = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/GetTruckerAppointments",
        headers={
            "Content-Type": "application/json",
            "Consumer-Key": APIGEE_CONSUMER_KEY,
            "Authorization": f"Bearer {forgerock_token}",
            "Termpoint-JWT": f"JWT {termpoint_jwt}",
        },
        json={
            "gateApptStart_DtTm": "2026-04-20T00:00:00",
            "gateApptEnd_DtTm": "2026-04-23T23:00:00",
            "apptType_Cd": "",
            "truckPlate_Nbr": "",
            "apptStatus_Cd": "",
            "cargoRef_Num": "",
            "container_Num": "",
        },
    )
    response.raise_for_status()
    return response.json()


def get_available_time_slots(forgerock_token: str, termpoint_jwt: str) -> dict:
    """Get available time slots (from Bruno GetAvailableTimeSlots.bru)"""
    response = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/GetAvailableTimeSlots",
        headers={
            "Content-Type": "application/json",
            "Consumer-Key": APIGEE_CONSUMER_KEY,
            "Authorization": f"Bearer {forgerock_token}",
            "Termpoint-JWT": f"JWT {termpoint_jwt}",
        },
        json={
            "gateAppt_Dt": "2026-04-20T00:00:00",
            "apptType_Cd": "IP",
            "gateAppt_Id": "",
            "gateApptStart_Tm": "",
            "container_Num": "",
            "cargoRef_Num": "",
            "con_Cd": "",
            "shippingLine_Cd": "",
            "reefer_Flg": "",
            "hazmat_Flg": "",
            "oD_Flg": "",
        },
    )
    response.raise_for_status()
    return response.json()


def post_create_appointment(forgerock_token: str, termpoint_jwt: str) -> dict:
    """Create an appointment (from Bruno PostCreateAppointment.bru)"""
    response = requests.post(
        f"https://{TERMPOINT_HOST}/termpoint-tms/api/MyAppointment/PostCreateAppointment",
        headers={
            "Content-Type": "application/json",
            "Consumer-Key": APIGEE_CONSUMER_KEY,
            "Authorization": f"Bearer {forgerock_token}",
            "Termpoint-JWT": f"JWT {termpoint_jwt}",
        },
        json=[{
            "gateApptStart_Tm": "23:00",
            "gateAppt_Dt": "2026-04-25T00:00:00",
            "driverId_Num": "",
            "driverOwnChs_Flg": "Y",
            "truckPlate_Nbr": "",
            "cargoRef_Num": "",
            "cargoRefType_Cd": "",
            "shippingLine_Cd": "",
            "container_Num": "MSKU6552574",
            "chassis_Num": "",
            "genset_Num": "",
            "con_Cd": "",
            "reefer_Flg": "",
            "hazmat_Flg": "",
            "oD_Flg": "",
            "vgmSubmitted_Flg": "",
            "seal1_Num": "",
            "seal2_Num": "",
            "apptType_Cd": "MD",
            "position_On_Truck": 0,
        }],
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    print("=== Termpoint TMS API ===")
    print(f"Target: {TERMPOINT_HOST}\n")

    # Auth flow
    forgerock_token = get_iam_token()
    termpoint_jwt = authenticate_user(forgerock_token)

    # Example: Get available time slots
    print("\n--- GetAvailableTimeSlots ---")
    result = get_available_time_slots(forgerock_token, termpoint_jwt)
    print(json.dumps(result, indent=2))

    # Example: Get trucker appointments
    print("\n--- GetTruckerAppointments ---")
    result = get_trucker_appointments(forgerock_token, termpoint_jwt)
    print(json.dumps(result, indent=2))
