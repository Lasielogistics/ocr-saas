#!/usr/bin/env python3
"""Tuning-focused benchmark: batch size, KV cache quantization, GPU layers.
Tests the key parameters from the Ollama/llama.cpp throughput research.
"""
import urllib.request, json, time, sys

# Servers - update these to match your running instances
# Run `ss -tlnp | grep 808` to see active ports
# Add new tuned servers as you start them on different ports
# GPU MEMORY CONSTRAINT: tb=512 max for Vulkan/890M (tb=1024+ fails to load)
# Verified: tb=4096 ngl=99 → ErrorDeviceLost; tb=1024 ngl=33 → failed to fit params
# KV cache quantization (-ctk/-ctv q8_0): BROKEN — generates 1-2 tokens then EOS
SERVERS = {
    # Currently running: Vulkan binary, ngl=33, tb=512, t=16
    "Vulkan ngl=33 tb=512 t=16":  "http://localhost:8086",
    # To test CPU baseline: /home/talha/llama.cpp/build/bin/llama-server ... -ngl 0 -t 16 --port 8083
    # "CPU ngl=0 t=16":          "http://localhost:8083",
    # HIP/patched (if container running on 8080 or 8088):
    # "HIP ngl=99 tb=512 t=32":  "http://localhost:8088",
}
MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"

PROMPT = ("Write a Python async context manager that takes a database connection pool as an argument, "
          "acquires a connection on __aenter__, releases it on __aexit__, handles connection errors "
          "gracefully, includes type hints and a docstring.\n\nclass DatabaseManager:\n    pass")

PROMPT_SHORT = "def fibonacci(n: int) -> list[int]:"

def bench(url, prompt, n_predict, extra_body=None):
    payload = {"model": MODEL, "prompt": prompt, "max_tokens": n_predict}
    if extra_body:
        payload["extra_body"] = extra_body

    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"{url}/v1/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            d = json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

    elapsed = time.time() - t0
    t = d["timings"]
    u = d.get("usage", {})
    prompt_ps = t["prompt_per_second"]
    gen_ps = t["predicted_per_second"]
    ttft_ms = t["predicted_ms"]
    n_pred = t.get("predicted_n", u.get("completion_tokens", "?"))
    cached = t.get("cache_n", 0)
    prompt_tokens = u.get("prompt_tokens", t.get("prompt_n", "?"))

    # True gen time correction for the metric bug
    if ttft_ms < 500 and n_pred and int(n_pred) > 1:
        true_gen_s = elapsed - (prompt_tokens / prompt_ps)
        true_gen_ps = int(n_pred) / true_gen_s if true_gen_s > 0 else gen_ps
    else:
        true_gen_ps = gen_ps

    return {
        "prompt_ps": round(prompt_ps, 1),
        "gen_ps": round(true_gen_ps, 1),
        "ttft": round(ttft_ms/1000, 2),
        "wall": round(elapsed, 2),
        "cached": cached,
        "n_pred": n_pred,
    }

def fmt_row(name, r):
    if r is None or "error" in r:
        return f"{name:<35} |  ERROR  "
    return (f"{name:<35} | P:{r['prompt_ps']:5.0f} G:{r['gen_ps']:5.1f} "
            f"TTFT:{r['ttft']:5.2f}s W:{r['wall']:5.2f}s cached:{r['cached']}")

def run_sweep(label, prompt, n_predict, servers, extra_body=None):
    print(f"\n{'='*80}")
    print(f"SWEEP: {label} (n_predict={n_predict})")
    print(f"{'='*80}")
    results = {}
    for srv_name, url in servers.items():
        print(f"  {srv_name}...", end=" ", flush=True)
        r = bench(url, prompt, n_predict, extra_body)
        results[srv_name] = r
        if "error" in r:
            print(f"ERROR: {r['error']}")
        else:
            print(f"P:{r['prompt_ps']:5.0f} G:{r['gen_ps']:5.1f} TTFT:{r['ttft']:5.2f}s W:{r['wall']:5.2f}s")
        time.sleep(0.3)
    return results

# ---- Warmup ----
print("Warming up all servers...")
for srv_name, url in SERVERS.items():
    try:
        req = urllib.request.Request(
            f"{url}/v1/completions",
            data=json.dumps({"model": MODEL, "prompt": "warmup", "max_tokens": 8}).encode(),
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=60):
            print(f"  {srv_name}: warm OK")
    except Exception as e:
        print(f"  {srv_name}: warm FAILED ({e})")
    time.sleep(0.3)
time.sleep(2)

# ---- Test Matrix ----
all_results = []

# Phase 1: Batch size sweep — SKIP: tb>512 fails on 890M (GPU memory)
# Verified: tb=4096 ngl=99 → ErrorDeviceLost; tb=1024 ngl=33 → mem error
# Only tb=512 works. This is a hard ceiling on this iGPU.

# Phase 2: Context size sweep (num_ctx)
print("\n\n### Phase 2: Context Size Sweep ###")
for ctx in [4096, 8192, 16384, 32768]:
    r = run_sweep(f"ctx={ctx}", PROMPT, 256, SERVERS,
                   extra_body={"ctx_size": ctx})
    all_results.append(("ctx="+str(ctx), r))
    time.sleep(1)

# Phase 3: KV cache quantization via extra_body (if supported)
# Note: requires server started with -ctk q8_0 -ctv q8_0 etc.
# The extra_body approach may not override server-side KV cache settings
print("\n\n### Phase 3: Generation Length Sweep ###")
for n in [128, 256, 512]:
    r = run_sweep(f"gen={n}", PROMPT, n, SERVERS)
    all_results.append(("gen="+str(n), r))
    time.sleep(1)

# Phase 4: Short prompt burst
print("\n\n### Phase 4: Short Prompt (burst coding) ###")
r = run_sweep("short-prompt", PROMPT_SHORT, 256, SERVERS)
all_results.append(("short-prompt", r))
time.sleep(1)

# Phase 5: Cache hit test
print("\n\n### Phase 5: KV Cache Hit Test ###")
CACHE_PROMPT = "Cache test for KV cache benchmarking on AMD 890M."
for srv_name, url in SERVERS.items():
    print(f"\n  {srv_name}:")
    r1 = bench(url, CACHE_PROMPT, 128)
    print(f"    cold:  P:{r1['prompt_ps']:5.0f} G:{r1['gen_ps']:5.1f} cached:{r1['cached']}")
    time.sleep(0.3)
    r2 = bench(url, CACHE_PROMPT, 128)
    print(f"    warm:  P:{r2['prompt_ps']:5.0f} G:{r2['gen_ps']:5.1f} cached:{r2['cached']}")
    if r1['wall'] > 0 and r2['wall'] > 0:
        print(f"    speedup: {r1['wall']/r2['wall']:.2f}x")
    time.sleep(0.3)

# ---- Summary ----
print("\n\n" + "="*80)
print("SUMMARY TABLE")
print("="*80)
header = f"{'Test':<30}"
for srv_name in SERVERS:
    header += f" | {srv_name:<25}"
print(header)
print("-"*80)

for test_name, results in all_results:
    row = f"{test_name:<30}"
    for srv_name in SERVERS:
        r = results.get(srv_name, {})
        if not r or "error" in r:
            row += " | ERR/N/A                "
        else:
            row += f" | G:{r['gen_ps']:4.1f} T:{r['ttft']:4.2f}s     "
    print(row)

print("\n" + "="*80)
print("ACTUAL FINDINGS & RECOMMENDED SERVER FLAGS (HX 470 + 890M)")
print("="*80)
print("""
# Confirmed working servers:
# - 8086: Vulkan, ngl=33, tb=512, t=16 (host binary)
# - 8088: HIP/patched, ngl=99, tb=512, t=32 (if container running)

# === KEY FINDINGS FROM TESTING ===
# 1. tb=512 is the HARD CEILING — batch >512 fails on 890M
#    - tb=1024 ngl=33 → "failed to fit params to free device memory"
#    - tb=4096 ngl=99 → ErrorDeviceLost
#    - KV cache quantization does NOT free enough memory
#
# 2. KV CACHE QUANTIZATION (-ctk/-ctv q8_0) IS BROKEN
#    - Server with ctk/ctv generates 1-2 tokens then returns EOS immediately
#    - DO NOT use -ctk/-ctv flags on this Vulkan binary
#
# 3. KV cache has ZERO hits (cache_n=0) even on repeated prompts
#    - llama.cpp KV cache appears non-functional on this setup
#
# 4. ctx_size has NO meaningful impact on throughput
#    - ctx=4K/8K/16K/32K all → ~15-19 t/s gen (stable)
#
# 5. ngl=99 (HIP) → ~19.4 t/s; ngl=33 (Vulkan) → ~15.5 t/s
#    - Full GPU offload is ~25% faster if HIP binary is available
#
# === FINAL RECOMMENDED SERVER FLAGS ===
# Vulkan (ngl=33, partial offload):
/home/talha/llama.cpp/build-vulkan/bin/llama-server \\
  -m /home/talha/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf \\
  -c 32768 -tb 512 \\
  --host 0.0.0.0 --port 8086 \\
  -ngl 33 --mlock -t 16

# HIP/patched (full offload, best performance):
/tmp/llama-hip-fix/llama-server \\
  -m /home/talha/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf \\
  -c 32768 -tb 512 \\
  --host 0.0.0.0 --port 8088 \\
  -ngl 99 --mlock -t 32

# === NOTES ===
# - ROCm 7.x does NOT support Polaris/HX 470 (gfx900)
# - Vulkan is the only reliable GPU path; HIP is patched/unofficial
# - CPU (-ngl 0) is competitive: ~16 t/s gen
# - The 890M is memory-bandwidth-bound, not compute-bound
""")
