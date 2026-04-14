# Voice AI Android App — Lemonade Server Integration

## Context

User wants an Android app that:
- Logs in via Supabase Auth
- Provides voice input → AI on lemonade server → voice output
- Reads container data from Supabase
- Writes a todo list to Supabase
- All AI runs on lemonade's NPU via Ollama to save CPU/IGPU resources

**Server IPs:** `192.168.50.100` (local) / `100.121.68.113` (Tailscale)
**Existing server:** lasie-dispatch server at port 9000 (ai_chat_server.py)
**Ollama:** Running at `localhost:11434` on lemonade
**Supabase:** `https://bsaffwfvnnyaihmrmqwt.supabase.co`

---

## Architecture

```
Android App (Kotlin/Compose)
    │
    │ 1. Login (Supabase Auth)
    ▼
Supabase Auth
    │
    │ 2. Voice recording + TTS playback
    ▼
LEMONADE SERVER (192.168.50.100:9000)
    ├── POST /stt           ← new: audio → text (Whisper)
    ├── POST /chat          ← existing: text AI chat → text
    ├── POST /tts           ← new: text → audio (XTTS/Coqui)
    └── POST /todo          ← new: CRUD todo items in Supabase
           │
           ▼
    Ollama (NPU) + XTTS/Coqui TTS
           │
           ▼
    Supabase (containers READ, todos WRITE)
```

---

## Part 1: Lemonade Server Extensions

### New endpoint: `POST /stt` — Speech-to-Text
- Accept: audio file (multipart/form-data), model name (default: `whisper-base`)
- Run Whisper locally on lemonade (CPU, but Whisper is efficient)
- Return: transcribed text

### New endpoint: `POST /tts` — Text-to-Speech
- Accept: JSON `{"text": "...", "model": "xtts"}`
- Run XTTSv2 or Coqui TTS on lemonade (GPU/NPU)
- Return: audio file (MP3/WAV)

### New endpoint: `POST /todo` — Todo CRUD
- `GET /todo` — list todos for authenticated user
- `POST /todo` — create todo (`{title, description, completed}`)
- `PUT /todo/{id}` — update todo
- `DELETE /todo/{id}` — delete todo
- Table: `todos` (id, title, description, completed, user_id, created_at, updated_at)

---

## Part 2: Android App (Kotlin + Jetpack Compose)

### Stack
- **Language:** Kotlin
- **UI:** Jetpack Compose with Material 3
- **Auth:** Supabase Kotlin Client (email/password, Google)
- **Networking:** Retrofit + OkHttp (streaming for chat)
- **Voice:** Android SpeechRecognizer (input) + TextToSpeech (fallback playback)
- **DI:** Hilt
- **Architecture:** MVVM + Clean Architecture

### Screens
1. **LoginScreen** — Supabase Auth (email/password or Google Sign-In)
2. **HomeScreen** — Main voice chat interface
3. **ContainersScreen** — Read-only container list from Supabase
4. **TodoScreen** — Todo list (CRUD via /todo endpoint)
5. **SettingsScreen** — Server URL config, logout

### Voice Flow
1. User presses mic button → Android SpeechRecognizer records → text
2. Text sent to `/chat` → streaming AI response text
3. AI response sent to `/tts` → audio returned → Android MediaPlayer plays
4. (Alt: Use device TTS as fallback if server TTS fails)

### Supabase Tables
```sql
-- Todos table (needs to be created)
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

---

## Part 3: Implementation Steps

### Step 1: Server Extensions (lemonade server)
1. Add `POST /stt` endpoint — use `openai-whisper` or `faster-whisper` via Ollama API or direct
2. Add `POST /tts` endpoint — use XTTSv2 or Coqui (check what's installed)
3. Add `POST /todo` + `GET /todo` + `PUT /todo/{id}` + `DELETE /todo/{id}` endpoints
4. Create `todos` table in Supabase
5. Update CORS origins to include Android app origin

### Step 2: Android Project Setup
1. Create Kotlin Android project with Compose + Hilt
2. Configure Supabase client with Auth + Database
3. Add server URL setting (default: `http://192.168.50.100:9000`)
4. Build LoginScreen with Supabase Auth
5. Build HomeScreen with voice chat (mic button + chat bubbles)
6. Build ContainersScreen with Supabase direct query
7. Build TodoScreen with CRUD operations
8. Build SettingsScreen

### Step 3: Voice Integration
1. Implement speech-to-text using Android SpeechRecognizer Intent
2. Send transcribed text to `/chat`
3. Implement `/tts` call → play returned audio via MediaPlayer
4. Fallback: use Android TextToSpeech if `/tts` fails

---

## Critical Files

### Server (lemonade)
- `/data/projects/lasie-dispatch/server/ai_chat_server.py` — extend with /stt, /tts, /todo endpoints

### Android
- New project at `/data/android-voice-app/` (or similar location)
- Gradle wrapper + build.gradle.kts
- `app/src/main/java/com/lemonade/voice/` — main package
- `app/src/main/java/com/lemonade/voice/data/` — repositories, API client
- `app/src/main/java/com/lemonade/voice/domain/` — use cases
- `app/src/main/java/com/lemonade/voice/ui/` — screens, viewmodels

---

## Verification

1. Server: `curl http://192.168.50.100:9000/health`
2. Server: `curl -X POST http://192.168.50.100:9000/todo` with test data
3. Android: Run on emulator/device, login, test voice button, test todo CRUD
4. Check Supabase dashboard for todos table rows
