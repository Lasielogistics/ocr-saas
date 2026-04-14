# Android Voice App — Lemonade Server Integration

## Context

Android app that:
- Logs in via Supabase Auth
- Voice input → AI on lemonade server (Ollama on NPU) → voice output
- Reads container data from Supabase
- Writes a todo list to Supabase
- All AI runs on lemonade's NPU via Ollama to save CPU/IGPU resources

## Key Info
- **Supabase URL:** `https://bsaffwfvnnyaihmrmqwt.supabase.co`
- **Server IPs:** `192.168.50.100` (local) / `100.121.68.113` (Tailscale)
- **Ollama:** `localhost:11434` on lemonade
- **Existing server:** `/data/projects/lasie-dispatch/server/ai_chat_server.py`

## Architecture

```
Android App (Kotlin/Compose)
    │
    │ 1. Login (Supabase Auth)
    ▼
Supabase Auth
    │
    │ 2. Voice: mic → /stt → /chat → /tts → playback
    ▼
LEMONADE SERVER (192.168.50.100:9000)
    ├── POST /stt        ← new: Whisper audio→text
    ├── POST /chat       ← existing
    ├── POST /tts        ← new: text→audio
    └── POST /todo       ← new: CRUD todos
           │
           ▼
    Ollama (NPU) + XTTS TTS
           │
           ▼
    Supabase (containers READ, todos WRITE)
```

## Server Endpoints to Add

### POST /stt — Speech-to-Text
- Input: audio file (multipart/form-data)
- Model: Whisper (faster-whisper or openai-whisper)
- Return: `{"text": "transcribed text"}`

### POST /tts — Text-to-Speech
- Input: `{"text": "...", "model": "xtts"}`
- Model: XTTSv2 or Coqui on lemonade GPU
- Return: audio file (MP3)

### Todo CRUD
- `GET /todo` — list todos for user
- `POST /todo` — create todo
- `PUT /todo/{id}` — update todo
- `DELETE /todo/{id}` — delete todo

### Supabase Schema
```sql
CREATE TABLE todos (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  completed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Android App Structure

### Screens
1. **LoginScreen** — Supabase Auth (email/password, Google)
2. **HomeScreen** — Voice chat with mic button + chat bubbles
3. **ContainersScreen** — Read-only container list from Supabase
4. **TodoScreen** — Todo list (CRUD via /todo)
5. **SettingsScreen** — Server URL, logout

### Voice Flow
1. User presses mic → Android SpeechRecognizer → text
2. Text sent to `/chat` → streaming AI response
3. AI response sent to `/tts` → audio → MediaPlayer playback
4. Fallback: Android TextToSpeech if `/tts` fails

## Implementation Order

1. Server: Add /stt, /tts, /todo endpoints
2. Server: Create todos table in Supabase
3. Android: Create project with Compose + Hilt + Supabase client
4. Android: LoginScreen
5. Android: HomeScreen with voice chat
6. Android: ContainersScreen
7. Android: TodoScreen
8. Android: SettingsScreen

## Full Plan
`/data/projects/tms/android/PLAN.md`
