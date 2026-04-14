from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parents[1]
CHAT_DIR = Path(os.getenv("CHAT_DIR", "/chat"))
CHAT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

origins_raw = os.getenv("LOG_ORIGINS", "http://localhost:3000,http://192.168.50.30:3000")
origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["POST", "OPTIONS", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Supabase setup from environment
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://bsaffwfvnnyaihmrmqwt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Lemonade server configuration
LEMONADE_API_BASE = os.getenv("LEMONADE_API_BASE", "http://lemonade-server.ai/api/v1")
DEFAULT_MODEL = os.getenv("LEMONADE_MODEL", "qwen3:1.7b")


class LogEntry(BaseModel):
    session_id: str
    role: str
    content: str
    model: Optional[str] = None
    source: Optional[str] = None
    ts: Optional[float] = None
    response_time: Optional[float] = None
    prompt_tokens: Optional[int] = None
    generated_tokens: Optional[int] = None
    tokens_per_second: Optional[float] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = DEFAULT_MODEL


def is_container_related_query(query: str) -> bool:
    """Check if the query is related to containers or logistics operations."""
    container_keywords = [
        "container", "containers", "pickup", "delivery", "driver", "vessel",
        "cargo", "shipping", "lfd", "appointment", "schedule", "status",
        "reference", "ref#", "company", "ampak", "watco", "kocu", "mrsu",
        "whsu", "oocu", "one eagle", "wan hai"
    ]
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in container_keywords)


def get_containers_context(query: str, limit: int = 5) -> str:
    """Query Supabase containers and build context for the model."""
    try:
        response = supabase.table("containers").select("*").limit(limit).execute()

        if not response.data:
            return "No container data available."

        context = "Available container information:\n\n"
        for container in response.data:
            container_num = container.get("container_number", "N/A")
            status = container.get("status", "N/A")
            company = container.get("Company", "N/A")
            ref = container.get("Ref#", "N/A")
            pickup_driver = container.get("Pick Up Driver", "N/A")
            delivery_driver = container.get("Delivery Driver", "N/A")
            vessel = container.get("Vessel/Voyage", "N/A")
            lfd = container.get("LFD", "N/A")

            context += f"Container {container_num}:\n"
            context += f"  Status: {status}\n"
            context += f"  Company: {company}\n"
            context += f"  Reference: {ref}\n"
            context += f"  Vessel: {vessel}\n"
            context += f"  LFD: {lfd}\n"
            context += f"  Pickup Driver: {pickup_driver}\n"
            context += f"  Delivery Driver: {delivery_driver}\n\n"

        return context
    except Exception as e:
        return f"Error fetching container data: {str(e)}"


def build_system_prompt() -> str:
    """Build system prompt for the AI model."""
    from datetime import datetime
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p PST")

    return f"""You are a helpful logistics assistant for a container shipping company.
Current time: {current_time}

You have access to container data and can provide:
- Container status updates
- Driver assignments and waiting times
- Vessel and appointment information
- Pickup/delivery scheduling suggestions
- Performance metrics and recommendations

Be concise and helpful. When asked about containers, reference the specific data provided.
Answer only what is asked without adding unsolicited suggestions or information."""


async def call_lemonade_with_context(
    messages: list[dict],
    model: str,
    lemonade_url: str,
    context: str,
) -> list[str]:
    """Call Lemonade OpenAI-compatible API and yield chunks."""
    import httpx

    # Inject context into the user's message only if context is not empty
    if messages and context:
        last_user_msg_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                last_user_msg_idx = i
                break

        if last_user_msg_idx is not None:
            messages[last_user_msg_idx]["content"] = (
                f"Here's the latest container data:\n\n{context}\n\n"
                f"User question: {messages[last_user_msg_idx]['content']}"
            )

    # Add system prompt
    system_message = {"role": "system", "content": build_system_prompt()}
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, system_message)

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{lemonade_url}/chat/completions",
            json={"model": model, "messages": messages, "stream": True},
        ) as response:
            async for line in response.aiter_lines():
                line = line.strip()
                if line:
                    # Lemonade uses OpenAI-compatible SSE format
                    yield f"data: {line}\n\n"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest):
    """Chat endpoint that integrates Supabase data with Lemonade."""
    messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

    user_query = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_query = msg["content"]
            break

    context = ""
    if is_container_related_query(user_query):
        context = get_containers_context(user_query)

    return StreamingResponse(
        call_lemonade_with_context(messages, request.model, LEMONADE_API_BASE, context),
        media_type="application/octet-stream",
    )


@app.post("/log")
async def log(entry: LogEntry, request: Request) -> dict[str, str]:
    timestamp = entry.ts or time.time()
    record = entry.model_dump()
    record["ts"] = timestamp
    record["ip"] = request.client.host if request.client else None
    day = time.strftime("%Y-%m-%d", time.localtime(timestamp))
    logfile = CHAT_DIR / f"{day}.jsonl"
    with logfile.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return {"status": "logged"}


# Appointment models
class AppointmentBase(BaseModel):
    title: str
    start_time: str
    end_time: str
    container_id: Optional[str] = None
    driver_name: Optional[str] = None
    appointment_type: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "scheduled"
    color: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(BaseModel):
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    container_id: Optional[str] = None
    driver_name: Optional[str] = None
    appointment_type: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None


@app.get("/appointments")
async def get_appointments(start: Optional[str] = None, end: Optional[str] = None) -> dict:
    """Get appointments within date range"""
    try:
        response = supabase.table("appointments").select("*").execute()

        if response.data:
            events = []
            for apt in response.data:
                event = {
                    "id": apt.get("id"),
                    "title": apt.get("title", ""),
                    "start": apt.get("start_time"),
                    "end": apt.get("end_time"),
                    "allDay": False,
                    "backgroundColor": apt.get("color", "#1f6feb"),
                    "borderColor": apt.get("color", "#1f6feb"),
                    "extendedProps": {
                        "container_id": apt.get("container_id"),
                        "driver_name": apt.get("driver_name"),
                        "appointment_type": apt.get("appointment_type"),
                        "location": apt.get("location"),
                        "notes": apt.get("notes"),
                        "status": apt.get("status"),
                    }
                }
                events.append(event)

            return {"success": True, "events": events}
        else:
            return {"success": True, "events": []}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/appointments")
async def create_appointment(appointment: AppointmentCreate) -> dict:
    """Create new appointment"""
    try:
        appointment_dict = appointment.model_dump()

        if not appointment_dict.get("color"):
            type_colors = {
                "pickup": "#0052cc",
                "delivery": "#10b981",
                "other": "#6b778c"
            }
            appointment_dict["color"] = type_colors.get(appointment_dict.get("appointment_type", ""), "#6b778c")

        appointment_dict["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        appointment_dict["updated_at"] = appointment_dict["created_at"]

        response = supabase.table("appointments").insert([appointment_dict]).execute()

        if response.data:
            return {"success": True, "appointment": response.data[0]}
        else:
            return {"success": False, "error": "Failed to create appointment"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.put("/appointments/{appointment_id}")
async def update_appointment(appointment_id: str, appointment: AppointmentUpdate) -> dict:
    """Update appointment"""
    try:
        update_dict = {k: v for k, v in appointment.model_dump().items() if v is not None}
        update_dict["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

        response = supabase.table("appointments").update(update_dict).eq("id", appointment_id).execute()

        if response.data:
            return {"success": True, "appointment": response.data[0]}
        else:
            return {"success": False, "error": "Failed to update appointment"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/appointments/{appointment_id}")
async def delete_appointment(appointment_id: str) -> dict:
    """Delete appointment"""
    try:
        response = supabase.table("appointments").delete().eq("id", appointment_id).execute()
        return {"success": True, "message": "Appointment deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# APM Terminals API endpoints
from apm_client import apm_client, APMApiError


@app.get("/apm/health")
async def apm_health() -> dict:
    """Verify APM API connectivity"""
    try:
        apm_client._get_termpoint_jwt()
        return {"success": True, "status": "connected", "terminals": ["SEGOT", "USLAX", "USMOB", "USPEB", "ITVDL"]}
    except APMApiError as e:
        return {"success": False, "status": "error", "error": str(e)}


@app.get("/apm/slots")
async def get_apm_slots(
    terminal: str,
    from_date: str,
    to_date: str,
    appointment_type: Optional[str] = None,
) -> dict:
    """Get available time slots from APM API"""
    try:
        slots = apm_client.get_slots(terminal, from_date, to_date, appointment_type)
        return {
            "success": True,
            "slots": [
                {
                    "terminal": s.terminal,
                    "slotFrom": s.slot_from,
                    "slotTo": s.slot_to,
                    "appointmentType": s.appointment_type,
                    "available": s.available,
                }
                for s in slots
            ],
        }
    except APMApiError as e:
        return {"success": False, "error": str(e)}


@app.get("/apm/appointments")
async def get_apm_appointments(
    terminal: str = "USLAX",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict:
    """List appointments from APM API"""
    try:
        appointments = apm_client.list_appointments(terminal, from_date, to_date)
        return {
            "success": True,
            "appointments": [
                {
                    "appointmentId": a.appointment_id,
                    "terminal": a.terminal,
                    "slotFrom": a.slot_from,
                    "slotTo": a.slot_to,
                    "truck": a.truck,
                    "containerId": a.container_id,
                    "appointmentType": a.appointment_type,
                    "status": a.status,
                    "lineOperator": a.line_op,
                    "cargoReference": a.cargo_ref,
                    "equipmentSize": a.equip_size,
                    "ownChassis": a.own_chassis,
                }
                for a in appointments
            ],
        }
    except APMApiError as e:
        return {"success": False, "error": str(e)}


@app.get("/apm/appointments/{appointment_id}")
async def get_apm_appointment(terminal: str, appointment_id: str) -> dict:
    """Get specific appointment from APM API"""
    try:
        apt = apm_client.get_appointment(terminal, appointment_id)
        return {
            "success": True,
            "appointment": {
                "appointmentId": apt.appointment_id,
                "terminal": apt.terminal,
                "slotFrom": apt.slot_from,
                "slotTo": apt.slot_to,
                "truck": apt.truck,
                "containerId": apt.container_id,
                "appointmentType": apt.appointment_type,
                "status": apt.status,
                "lineOperator": apt.line_op,
                "cargoReference": apt.cargo_ref,
                "equipmentSize": apt.equip_size,
                "ownChassis": apt.own_chassis,
            },
        }
    except APMApiError as e:
        return {"success": False, "error": str(e)}


class APMAppointmentCreate(BaseModel):
    terminal: str
    slot_from: str
    slot_to: str
    appointment_type: str
    container_id: Optional[str] = None
    truck: Optional[str] = None
    line_op: Optional[str] = None
    cargo_ref: Optional[str] = None
    equip_size: Optional[str] = None
    own_chassis: Optional[str] = None


@app.post("/apm/appointments")
async def create_apm_appointment(data: APMAppointmentCreate) -> dict:
    """Create new appointment via APM API"""
    try:
        apt = apm_client.create_appointment(
            terminal=data.terminal,
            slot_from=data.slot_from,
            slot_to=data.slot_to,
            appointment_type=data.appointment_type,
            container_id=data.container_id,
            truck=data.truck,
            line_op=data.line_op,
            cargo_ref=data.cargo_ref,
            equip_size=data.equip_size,
            own_chassis=data.own_chassis,
        )
        return {"success": True, "appointment": {
            "appointmentId": apt.appointment_id,
            "terminal": apt.terminal,
            "status": apt.status,
        }}
    except APMApiError as e:
        return {"success": False, "error": str(e)}


class APMAppointmentUpdate(BaseModel):
    slot_from: Optional[str] = None
    slot_to: Optional[str] = None
    truck: Optional[str] = None


@app.put("/apm/appointments/{appointment_id}")
async def update_apm_appointment(
    terminal: str,
    appointment_id: str,
    data: APMAppointmentUpdate,
) -> dict:
    """Update appointment via APM API"""
    try:
        apt = apm_client.update_appointment(
            terminal=terminal,
            appointment_id=appointment_id,
            slot_from=data.slot_from,
            slot_to=data.slot_to,
            truck=data.truck,
        )
        return {"success": True, "appointment": {
            "appointmentId": apt.appointment_id,
            "status": apt.status,
        }}
    except APMApiError as e:
        return {"success": False, "error": str(e)}


@app.delete("/apm/appointments/{appointment_id}")
async def cancel_apm_appointment(terminal: str, appointment_id: str) -> dict:
    """Cancel appointment via APM API"""
    try:
        apm_client.cancel_appointment(terminal, appointment_id)
        return {"success": True, "message": "Appointment cancelled"}
    except APMApiError as e:
        return {"success": False, "error": str(e)}


@app.post("/apm/sync")
async def sync_apm_appointments(terminal: str = "USLAX") -> dict:
    """Sync APM appointments to Supabase port_appointments table"""
    try:
        appointments = apm_client.list_appointments(terminal)
        synced = 0
        for apt in appointments:
            port_apt = apm_client.to_port_appointment(apt)
            supabase.table("port_appointments").upsert(
                port_apt,
                on_conflict="terminal,apm_appointment_id",
            ).execute()
            synced += 1
        return {"success": True, "synced": synced, "terminal": terminal}
    except APMApiError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}
