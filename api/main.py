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

from invoices_api.auth import router as auth_router
from invoices_api.invoices import router as invoices_router

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

app.include_router(auth_router)
app.include_router(invoices_router)

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


@app.get("/api/metrics")
async def get_metrics():
    """Live server metrics for the TMS dashboard."""
    import re
    import datetime

    def kb_to_gb(kb):
        return round(int(kb) * 1024 / 1073741824, 1)

    # CPU from /proc/stat
    def get_cpu_pct():
        try:
            with open('/host/proc/stat') as f:
                line = f.readline()
            fields = line.split()
            # user nice idle
            user = int(fields[1])
            nice = int(fields[2])
            system = int(fields[3])
            idle = int(fields[4])
            iowait = int(fields[5])
            irq = int(fields[6])
            softirq = int(fields[7])
            total = user + nice + system + idle + iowait + irq + softirq
            active = total - idle - iowait
            if not hasattr(get_cpu_pct, '_prev'):
                get_cpu_pct._prev = (total, active)
                return 0.0
            prev_total, prev_active = get_cpu_pct._prev
            get_cpu_pct._prev = (total, active)
            if total - prev_total == 0:
                return 0.0
            return round(100.0 * (active - prev_active) / (total - prev_total), 1)
        except:
            return 0.0

    cpu_pct = get_cpu_pct()

    # CPU model + cores
    try:
        with open('/host/proc/cpuinfo') as f:
            cpuinfo = f.read()
        model_match = re.search(r'model name\s+:\s+(.+)', cpuinfo)
        cpu_model = model_match.group(1).split('@')[0].strip() if model_match else 'N/A'
        cores = len(re.findall(r'processor\s+:', cpuinfo))
    except:
        cpu_model = 'N/A'
        cores = 0

    # Mem
    with open('/host/proc/meminfo') as f:
        mem = f.read()
    m = dict(re.findall(r'(\w+):\s+(\d+)', mem))
    mem_total = int(m.get('MemTotal', 0)) // 1024
    mem_avail = int(m.get('MemAvailable', 0)) // 1024
    mem_used = mem_total - mem_avail

    # Load avg
    with open('/host/proc/loadavg') as f:
        load = f.read().split()[:3]
    loadavg = [float(x) for x in load]

    # Uptime
    with open('/host/proc/uptime') as f:
        uptime_s = float(f.read().split()[0])
    days = int(uptime_s // 86400)
    hours = int((uptime_s % 86400) // 3600)
    mins = int((uptime_s % 3600) // 60)
    boot_time = datetime.datetime.now() - datetime.timedelta(seconds=int(uptime_s))
    since = boot_time.strftime('%Y-%m-%d %H:%M')

    # containerd + dockerd CPU% (from /proc)
    def get_proc_cpu_pct(name):
        try:
            for proc_dir in ['/usr/bin/containerd', '/usr/sbin/dockerd', '/usr/bin/containerd-shim-runc-v2']:
                # find PIDs
                import glob
                for piddir in glob.glob(f'/proc/[0-9]*/'):
                    try:
                        with open(piddir + 'cmdline', 'rb') as f:
                            cmd = f.read().decode('utf-8', errors='ignore').replace('\x00', ' ')
                        if name in cmd:
                            pid = piddir.split('/')[-2]
                            with open(f'/proc/{pid}/stat') as f:
                                st = f.read().split()
                            utime = int(st[13])
                            stime = int(st[14])
                            starttime = int(st[21])
                            with open('/proc/uptime') as f:
                                uptime = float(f.read().split()[0])
                            with open('/proc/stat') as f:
                                sys_cpu = f.readline()
                            sys_fields = sys_cpu.split()
                            sys_total = sum(int(x) for x in sys_fields[1:])
                            sys_idle = int(sys_fields[4])
                            # simple rate
                            return round((utime + stime) / (uptime * 100), 1)
                    except:
                        continue
            return 0.0
        except:
            return 0.0

    # simpler approach: run ps via subprocess but fall back gracefully
    def ps_pct(cmdline_contains):
        try:
            import subprocess
            out = subprocess.check_output(
                f"ps aux | grep '{cmdline_contains}' | grep -v grep | awk '{{print $3}}'",
                shell=True, text=True, stderr=subprocess.DEVNULL, timeout=5
            ).strip()
            if out:
                return float(out.split('\n')[0])
        except:
            pass
        return 0.0

    def ps_etime(cmdline_contains):
        try:
            import subprocess
            out = subprocess.check_output(
                f"ps aux | grep '{cmdline_contains}' | grep -v grep | awk '{{print $10}}'",
                shell=True, text=True, stderr=subprocess.DEVNULL, timeout=5
            ).strip()
            return out.split('\n')[0] if out else 'N/A'
        except:
            return 'N/A'

    containerd_pct = ps_pct('/usr/bin/containerd')
    dockerd_pct = ps_pct('/usr/sbin/dockerd')
    containerd_etime = ps_etime('/usr/bin/containerd')
    dockerd_etime = ps_etime('/usr/sbin/dockerd')

    # Docker containers via socket
    containers = []
    running_count = 0
    try:
        import socket, json as _json, re
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect('/var/run/docker.sock')
        req = b'GET /v1.41/containers/json?all=true HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'
        sock.sendall(req)
        resp = b''
        while True:
            try:
                d = sock.recv(4096)
                if not d:
                    break
                resp += d
            except:
                break
        sock.close()
        body = resp.decode('utf-8', errors='ignore')
        # Extract JSON body after headers
        json_str = body.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in body else body
        json_str = json_str.strip()
        # Handle chunked transfer encoding
        te_match = re.search(r'transfer-encoding:\s*chunked', body, re.IGNORECASE)
        if te_match:
            chunks = []
            pos = 0
            data = json_str
            while pos < len(data):
                nl = data.find('\r\n', pos)
                if nl == -1 or nl == pos:
                    break
                size_hex = data[pos:nl].strip()
                if not size_hex:
                    break
                try:
                    size = int(size_hex, 16)
                except ValueError:
                    break
                if size == 0:
                    break
                chunk_start = nl + 2
                chunk_end = chunk_start + size
                chunks.append(data[chunk_start:chunk_end])
                pos = chunk_end
            json_str = ''.join(chunks)
        container_list = _json.loads(json_str)
        for c in container_list:
                names = c.get('Names', [])
                name = names[0].lstrip('/') if names else c.get('Id', '')[:12]
                state = c.get('State', '')
                status = c.get('Status', '')
                health = 'healthy' if c.get('Health', {}).get('Status') == 'healthy' else \
                         'starting' if 'starting' in status.lower() else \
                         'unhealthy' if state in ('dead', 'exited') else 'running'
                containers.append({
                    'name': name,
                    'status': state if state else 'unknown',
                    'health': health,
                    'cpu_pct': 'n/a',
                    'mem_pct': 'n/a',
                })
                if state == 'running':
                    running_count += 1
    except Exception as e:
        containers = []

    total_containers = len(containers)

    # Docker mem total
    try:
        import subprocess
        out = subprocess.check_output('docker info --format "{{.MemTotal}}"',
                                       shell=True, text=True, stderr=subprocess.DEVNULL, timeout=5)
        mem_total_docker = round(int(out.strip()) / 1048576, 1)
    except:
        mem_total_docker = 0.0

    try:
        import subprocess
        out = subprocess.check_output(
            'docker stats --no-stream --format "{{.MemUsage}}"',
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=5
        )
        used_mb = 0.0
        for line in out.strip().split('\n'):
            m = re.match(r'([0-9.]+)\s*(\w?i?B)', line)
            if m:
                val, unit = float(m.group(1)), m.group(2)
                used_mb += val * 1024 if 'Gi' in unit else val
        mem_used_docker = round(used_mb, 1)
    except:
        mem_used_docker = 0.0

    # Disks
    disks = []
    try:
        import subprocess
        df = subprocess.check_output(
            'df -P | grep "^/dev"', shell=True, text=True, stderr=subprocess.DEVNULL
        ).splitlines()
        for line in df:
            parts = line.split()
            if len(parts) >= 6:
                total_kb = int(parts[1])
                used_kb = int(parts[2])
                mount = parts[-1]
                disks.append({'mount': mount, 'total': kb_to_gb(total_kb), 'used': kb_to_gb(used_kb)})
    except:
        pass

    return {
        "cpu": {"pct": cpu_pct, "cores": cores, "model": cpu_model},
        "mem": {"total": kb_to_gb(mem_total), "used": kb_to_gb(mem_used), "avail": kb_to_gb(mem_avail)},
        "loadavg": loadavg,
        "uptime": {"days": days, "hours": hours, "mins": mins, "since": since},
        "docker": {
            "containerd_pct": round(containerd_pct, 1),
            "dockerd_pct": round(dockerd_pct, 1),
            "containerd_etime": containerd_etime,
            "dockerd_etime": dockerd_etime,
            "running": running_count,
            "total": total_containers,
            "mem_used": mem_used_docker,
            "mem_total": mem_total_docker,
        },
        "containers": containers,
        "disks": disks,
    }


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
