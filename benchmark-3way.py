#!/usr/bin/env python3
"""3-way llama.cpp benchmark: CPU vs Vulkan vs HIP (ROCm)"""
import urllib.request, json, time

# Servers confirmed running:
# CPU: port 8083 (-ngl 0, t=16)
# Vulkan: port 8084 (-ngl 33, t=16)
# HIP: port 8082 - binary has library path issues, skipping
PORTS = {
    "CPU (-ngl 0, t=16)":      8083,
    "Vulkan (-ngl 33, t=16)":  8084,
}
MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"

PROMPT = ("Write a Python async context manager that takes a database connection pool as an argument, "
          "acquires a connection on __aenter__, releases it on __aexit__, handles connection errors "
          "gracefully, includes type hints and a docstring.\n\nclass DatabaseManager:\n    pass")

PROMPT_SHORT = "def fibonacci(n: int) -> list[int]:"

def bench(port, prompt, n_predict):
    url = f"http://localhost:{port}/v1/completions"
    payload = {"model": MODEL, "prompt": prompt, "max_tokens": n_predict}

    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                      headers={"Content-Type": "application/json"}, method="POST")
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

    # True gen time (TTFT is total time, we want generation only)
    # For short n_predict the metric bugs out, detect and handle
    if ttft_ms < 500 and n_pred > 1:
        # Bug: predicted_ms rounds to 0, use wall time instead
        true_gen_s = elapsed - (prompt_tokens / prompt_ps)
        true_gen_ps = n_pred / true_gen_s if true_gen_s > 0 else gen_ps
    elif ttft_ms > 0 and n_pred > 0:
        true_gen_ps = gen_ps  # Use reported gen_ps directly (more reliable for full runs)
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

def run_test(test_name, prompt, n_predict):
    print(f"\n{'='*70}")
    print(f"Test: {test_name} (n_predict={n_predict})")
    print(f"{'='*70}")
    results = []
    for server_name, port in PORTS.items():
        print(f"  {server_name}...", end=" ", flush=True)
        r = bench(port, prompt, n_predict)
        if "error" in r:
            print(f"ERROR: {r['error']}")
            results.append((server_name, None, r['error']))
        else:
            print(f"Prompt: {r['prompt_ps']:5.0f} t/s | Gen: {r['gen_ps']:5.1f} t/s | "
                  f"TTFT: {r['ttft']:5.2f}s | Wall: {r['wall']:5.2f}s | "
                  f"Cached: {r['cached']} | tokens: {r['n_pred']}")
            results.append((server_name, r, None))
    return results

# Header
print("=" * 70)
print("llama.cpp 2-Way Benchmark — AMD Ryzen AI 9 HX 470 + 890M + 64GB")
print("Model: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf (Q4_K_XL, ~21GB)")
print("=" * 70)

# Warmup
print("\nWarming up...")
for server_name, port in PORTS.items():
    try:
        url = f"http://localhost:{port}/v1/completions"
        payload = {"model": MODEL, "prompt": "warmup", "max_tokens": 8}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                      headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            json.loads(resp.read())
        print(f"  {server_name}: warm OK")
    except Exception as e:
        print(f"  {server_name}: warm FAILED ({e})")
    time.sleep(0.5)
time.sleep(2)

# Run tests
all_results = []

tests = [
    ("Standard prompt 256",  PROMPT, 256),
    ("Standard prompt 512",  PROMPT, 512),
    ("Short prompt 256",    PROMPT_SHORT, 256),
    ("n_predict=32",         PROMPT, 32),
    ("n_predict=64",         PROMPT, 64),
    ("n_predict=128",        PROMPT, 128),
]

for test_name, prompt, n_pred in tests:
    r = run_test(test_name, prompt, n_pred)
    all_results.append((test_name, r))
    time.sleep(1)

# Summary table
print("\n" + "=" * 80)
print("SUMMARY TABLE")
print("=" * 80)
print(f"\n{'Test':<22} | {'CPU':<22} | {'Vulkan':<22}")
print("-" * 80)

for test_name, results in all_results:
    cpu_r = next((r for name, r, err in results if "CPU" in name), None)
    vul_r = next((r for name, r, err in results if "Vulkan" in name), None)

    def fmt(r):
        if r is None: return "ERROR/N/A"
        return f"P:{r['prompt_ps']:4.0f} G:{r['gen_ps']:4.1f} T:{r['ttft']:4.2f}s W:{r['wall']:5.2f}s"

    print(f"{test_name:<22} | {fmt(cpu_r):<22} | {fmt(vul_r):<22}")

print()
print("=" * 80)
print("KEY FINDINGS")
print("=" * 80)
for test_name, results in all_results:
    for name, r, err in results:
        if r:
            print(f"  {name:28s}: gen={r['gen_ps']:5.1f} t/s, ttft={r['ttft']:5.2f}s, wall={r['wall']:5.2f}s")