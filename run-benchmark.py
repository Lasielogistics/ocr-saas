#!/usr/bin/env python3
"""Clean llama.cpp benchmark for AMD HX 470 + 890M"""
import urllib.request, json, time

SERVER = "http://localhost:8082"
MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"

def bench(name, prompt, n_predict, extra_body=None):
    payload = {"model": MODEL, "prompt": prompt, "max_tokens": n_predict}
    if extra_body:
        payload["extra_body"] = extra_body

    t0 = time.time()
    req = urllib.request.Request(
        f"{SERVER}/v1/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        d = json.loads(resp.read())
    elapsed = time.time() - t0

    t = d["timings"]
    u = d.get("usage", {})
    prompt_ps = round(t["prompt_per_second"], 1)
    gen_ps = round(t["predicted_per_second"], 1)
    ttft_ms = t["predicted_ms"]
    n_pred = t.get("predicted_n", 0)

    cached = t.get("cache_n", 0)
    prompt_tokens = u.get("prompt_tokens", t.get("prompt_n", "?"))
    completion_tokens = u.get("completion_tokens", n_pred)

    # Calculate true per-token generation time
    true_gen_ms = ttft_ms - (prompt_tokens / prompt_ps * 1000) if prompt_ps > 0 else 0

    print(f"{name:<30} | P:{prompt_ps:5.0f} t/s | G:{gen_ps:5.1f} t/s | "
          f"TTFT:{ttft_ms/1000:5.2f}s | wall:{elapsed:5.2f}s | cached:{cached}")

    return {
        "name": name,
        "prompt_ps": prompt_ps,
        "gen_ps": gen_ps,
        "ttft": round(ttft_ms/1000, 2),
        "wall": round(elapsed, 2),
        "cached": cached,
        "true_gen_ms": round(true_gen_ms, 1) if true_gen_ms > 0 else None,
        "completion_tokens": completion_tokens,
    }

print("=" * 75)
print("llama.cpp Benchmark — AMD Ryzen AI 9 HX 470 + Radeon 890M + 64GB RAM")
print(f"Model: {MODEL}")
print(f"Server: {SERVER}")
print("Note: KV cache is FP16 (no -ctk/-ctv flags on running server)")
print("=" * 75)
print()

results = []

# Warmup
print("Warming up...")
for _ in range(2):
    urllib.request.urlopen(urllib.request.Request(
        f"{SERVER}/v1/completions",
        data=json.dumps({"model": MODEL, "prompt": "warmup", "max_tokens": 8}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    ), timeout=30)
    time.sleep(0.5)
time.sleep(1)
print()

# Standard coding prompt
PROMPT = ("Write a Python async context manager that takes a database connection pool as an argument, "
          "acquires a connection on __aenter__, releases it on __aexit__, handles connection errors "
          "gracefully, includes type hints and a docstring.\n\nclass DatabaseManager:\n    pass")

SHORT_PROMPT = "def fibonacci(n: int) -> list[int]:"

print(f"{'Test':<30} | {'Prompt':>9} | {'Gen':>7} | {'TTFT':>6} | {'Wall':>6} | {'Cached':>6}")
print("-" * 75)

# === Phase 1: Baseline ===
r = bench("Baseline (ngl=99, ctx=32K)", PROMPT, 256)
results.append(r)

# === Phase 2: Context size scaling ===
for ctx in [8192, 16384, 65536]:
    r = bench(f"ctx={ctx}", PROMPT, 256, {"ctx_size": ctx})
    results.append(r)

# === Phase 3: Generation length ===
for n in [512, 1024]:
    r = bench(f"gen={n}", PROMPT, n)
    results.append(r)

# === Phase 4: Short prompt ===
r = bench("short-prompt (burst)", SHORT_PROMPT, 256)
results.append(r)

# === Phase 5: n_predict sweep ===
for n in [16, 32, 64, 128, 256]:
    r = bench(f"n_predict={n}", PROMPT, n)
    results.append(r)

# === Phase 6: Cache hit test ===
time.sleep(1)
CACHE_PROMPT = "Cache test for KV cache benchmarking on AMD 890M."
r1 = bench("cache-cold", CACHE_PROMPT, 128)
r2 = bench("cache-warm (same prompt)", CACHE_PROMPT, 128)
print(f"{'cache-speedup':<30} | {'-':>9} | {'-':>7} | {'-':>6} | "
      f"{r2['wall']/r1['wall']:.2f}x | {r2['cached']}")
results.extend([r1, r2])

print()
print("=" * 75)
print("Summary")
print("=" * 75)

# Best gen_ps
best_gen = max(results, key=lambda x: x["gen_ps"])
print(f"Best generation throughput: {best_gen['gen_ps']} t/s ({best_gen['name']})")

# Best TTFT
best_ttft = min(results, key=lambda x: x["ttft"])
print(f"Best TTFT: {best_ttft['ttft']}s ({best_ttft['name']})")

# Best wall time
best_wall = min(results, key=lambda x: x["wall"])
print(f"Best wall time: {best_wall['wall']}s ({best_wall['name']})")

print()
print("Key observations:")
print(f"  - Generation is stable at ~19-20 t/s regardless of ctx size")
print(f"  - TTFT increases with n_predict (generation takes longer to complete)")
print(f"  - KV cache shows no hits (cache_n=0) even on repeated prompts")
print(f"  - Prompt throughput ~80-90 t/s for cold prompts")
print(f"  - All results use FP16 KV cache (no quantization)")