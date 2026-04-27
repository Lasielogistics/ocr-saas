#!/bin/bash
# llama.cpp benchmark — AMD Ryzen AI 9 HX 470 + Radeon 890M + 64GB RAM
# Model: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf (Q4_K_XL, ~20GB)
# Server: localhost:8082 (GPU offload -ngl 99, ctx=32K, no KV cache quantization)
# NOTE: Server running WITHOUT -ctk/-ctv flags, so KV cache is default FP16

set -e

SERVER="http://localhost:8082"
MODEL="Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
OUT="/data/projects/tms/benchmark-results.md"

PROMPT='Write a Python async context manager that takes a database connection pool as an argument, acquires a connection on __aenter__, releases it on __aexit__, handles connection errors gracefully, includes type hints and a docstring.

class DatabaseManager:
    pass'

PROMPT_SHORT='def fibonacci(n: int) -> list[int]:'

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT"; }

init_md() {
    cat > "$OUT" << 'EOF'
# llama.cpp Benchmark Results

## Hardware
- CPU: AMD Ryzen AI 9 HX 470 (16C/32T Zen 5)
- iGPU: AMD Radeon 890M (RDNA 3.5, ~8.9 TFLOPS FP16)
- RAM: 64GB DDR5-5600 (~100 GB/s bandwidth)
- VRAM: 512MB stolen (iGPU shares RAM)

## Model
- Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf (~20GB file)
- MoE: 35B total params, ~3B active per token
- Quantization: Q4_K_XL

## Server flags (current running instance)
```
/llama.cpp/build-hip/bin/llama-server \
  -m /models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf \
  -c 32768 -tb 512 --host 0.0.0.0 --port 8082 -ngl 99
```
NOTE: No -ctk/-ctv at startup. KV cache is default FP16 (not quantized).
KV cache quantization has NOT been tested yet — this is the next step.

## Test Protocol
- All tests cold (no cache warming between tests)
- n_predict=256 unless noted
- Same coding prompt used for consistency

## Legend
- **Prompt t/s**: prompt/prefill throughput (cold start)
- **Gen t/s**: text generation throughput
- **TTFT**: time to first token in seconds
- **Cached**: tokens served from KV cache (0 = fully cold)

EOF
}

run_bench() {
    local label="$1"
    local prompt="$2"
    local n_predict="$3"
    local extra="${4:-}"   # e.g. '"extra_body":{"ctx_size":8192}'

    log "Running: $label"

    # Build JSON payload properly
    local json_payload
    json_payload=$(python3 -c "
import sys, json
model = '$MODEL'
prompt = '''$prompt'''
prompt = prompt.replace(\"'\", \"'\"*3)
n = $n_predict
extra = $extra
body = {'model': model, 'prompt': prompt, 'max_tokens': n}
if extra:
    body['extra_body'] = extra
print(json.dumps(body))
" 2>/dev/null)

    local result
    result=$(curl -s "$SERVER/v1/completions" \
        -H "Content-Type: application/json" \
        -d "$json_payload" 2>/dev/null)

    local prompt_ps pred_ms pred_ps cached
    prompt_ps=$(echo "$result" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(round(d['timings']['prompt_per_second'],1))
" 2>/dev/null || echo "ERR")
    pred_ms=$(echo "$result" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(round(d['timings']['predicted_ms'],1))
" 2>/dev/null || echo "ERR")
    pred_ps=$(echo "$result" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(round(d['timings']['predicted_per_second'],1))
" 2>/dev/null || echo "ERR")
    cached=$(echo "$result" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(d['timings']['cache_n'])
" 2>/dev/null || echo "?")

    if [ "$prompt_ps" = "ERR" ]; then
        log "  PARSE ERROR"
        echo "$result" | head -c 300 >> "$OUT"
        log ""
        return 1
    fi

    local ttft_s
    ttft_s=$(python3 -c "print(round($pred_ms/1000, 2))")

    printf "| %-35s | %7.1f | %7.1f | %6.2f | %6s |\n" \
        "$label" "$prompt_ps" "$pred_ps" "$ttft_s" "$cached" | tee -a "$OUT"
    log "  Prompt: ${prompt_ps} t/s | Gen: ${pred_ps} t/s | TTFT: ${ttft_s}s | Cached: ${cached}"
}

# ============ MAIN ============
init_md

printf "| %-35s | %7s | %7s | %6s | %6s |\n" "Test" "Prompt t/s" "Gen t/s" "TTFT" "Cached" | tee -a "$OUT"
printf "| %-35s | %7s | %7s | %6s | %6s |\n" "-----------------------------------" "--------" "--------" "------" "------" | tee -a "$OUT"

log "Warming up (2 requests)..."
for i in 1 2; do
    curl -s "$SERVER/v1/completions" -H "Content-Type: application/json" \
        -d '{"model":"'"$MODEL"'","prompt":"warmup","max_tokens":16}' > /dev/null 2>&1 || true
    sleep 0.5
done
sleep 1

log "Starting benchmark..."
echo ""

# === Phase 1: Baseline ===
run_bench "Baseline (ngl=99, ctx=32K)" "$PROMPT" 256

# === Phase 2: Context size ===
for ctx in 8192 16384 65536; do
    run_bench "ctx=${ctx}" "$PROMPT" 256 '{"ctx_size":'$ctx'}'
done

# === Phase 3: Generation length ===
run_bench "gen=512" "$PROMPT" 512
run_bench "gen=1024" "$PROMPT" 1024

# === Phase 4: Short prompt (burst coding) ===
run_bench "short-prompt (burst)" "$PROMPT_SHORT" 256

# === Phase 5: n_predict sweep (responsiveness) ===
for np in 16 32 64 128 256; do
    run_bench "n_predict=$np" "$PROMPT" $np
done

# === Phase 6: Cache hit test ===
log "Running cache hit test..."
sleep 1
C1=$(curl -s "$SERVER/v1/completions" -H "Content-Type: application/json" \
    -d '{"model":"'"$MODEL"'","prompt":"Cache test for KV cache benchmarking.","max_tokens":128}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['timings']['cache_n'])" 2>/dev/null || echo "?")
sleep 0.3
C2=$(curl -s "$SERVER/v1/completions" -H "Content-Type: application/json" \
    -d '{"model":"'"$MODEL"'","prompt":"Cache test for KV cache benchmarking.","max_tokens":128}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['timings']['cache_n'])" 2>/dev/null || echo "?")
printf "| %-35s | %7s | %7s | %6s | %6s |\n" "cache-cold" "-" "-" "-" "$C1" | tee -a "$OUT"
printf "| %-35s | %7s | %7s | %6s | %6s |\n" "cache-warm (repeat)" "-" "-" "-" "$C2" | tee -a "$OUT"
log "  Cache: cold=$C1 tokens, warm=$C2 tokens"

log "Benchmark complete."
echo ""
log "Results: $OUT"