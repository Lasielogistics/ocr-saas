# Lemonade Server Documentation

**Source:** https://lemonade-server.ai/docs/server/server_spec/

## Overview

Lemonade Server is a standards-compliant HTTP API server for LLM inference supporting multiple backends.

### Supported Backends
- **Llama.cpp**: `.GGUF` files via llama-server
- **ONNX Runtime GenAI**: `.ONNX` via ryzenai-server
- **FastFlowLM**: `.q4nx` via flm serve (Windows)
- **whisper.cpp**: `.bin` for audio transcription
- **stable-diffusion.cpp**: `.safetensors` for image generation
- **Kokoros**: `.onnx` for speech synthesis

### API Compatibility
- OpenAI-compatible endpoints (chat completions, embeddings, images, audio)
- Ollama API compatibility on port 11434
- Anthropic Messages API support

---

## Core Endpoints

### `/api/v1/chat/completions`
OpenAI-compatible chat completions endpoint.

**Features:**
- Messages, model selection
- Streaming options
- Temperature, top_k/p, stop sequences
- Max tokens
- Function calling tools
- Image understanding via base64 data URLs

### `/api/v1/completions`
Text completion endpoint.

### `/api/v1/embeddings`
Generates vector representations for semantic search.

### `/api/v1/reranking`
Reorders documents by relevance scores.

### `/api/v1/responses`
OpenAI-style streaming events.

### `/api/v1/images/generations`
Image generation with parameters:
- prompt, steps, cfg_scale, seed, size

### `/api/v1/audio/transcriptions`
Audio transcription. Requires WAV format at 16kHz mono PCM16.

### `/api/v1/audio/speech`
Speech synthesis. Outputs MP3, WAV, Opus, or PCM formats.

---

## Model Management Endpoints

### `/api/v1/load`
Load a model with per-model recipe options.

### `/api/v1/unload`
Unload a model from memory.

### `/api/v1/pull`
Install a model (with SSE progress streaming).

### `/api/v1/delete`
Delete an installed model.

### `/api/v1/models`
List available models.

---

## System Endpoints

### `/api/v1/health`
Health check. Returns `websocket_port` for realtime audio.

### `/api/v1/stats`
Returns TTFT (Time To First Token), TPS (Tokens Per Second) metrics.

### `/api/v1/system-info`
Device enumeration and backend states.

---

## Multi-Model Support

- Multi-model simultaneous loading with LRU eviction
- Configurable slot limits via `--max-loaded-models`
- Per-type LRU caches (LLM, embedding, reranking, audio, image)
- Device constraints: NPU exclusivity between flm, ryzenai-llm, and whispercpp backends

---

## Port Configuration

- **Main API**: Port 8000
- **Ollama-compatible API**: Port 11434
