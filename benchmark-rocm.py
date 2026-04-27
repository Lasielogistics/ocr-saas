#!/usr/bin/env python3
"""ROCm llama.cpp benchmark with server restart between tests.
Restarts the llama-build container between each test to ensure cold-start accuracy.
"""
import urllib.request, json, time, subprocess, sys, os

MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
PORT = 8088
BASE_URL = f"http://localhost:{PORT}"

PROMPT = ("Write a Python async context manager that takes a database connection pool as an argument, "
          "acquires a connection on __aenter__, releases it on __aexit__, handles connection errors "
          "gracefully, includes type hints and a docstring.\n\nclass DatabaseManager:\n    pass")

PROMPT_SHORT = "def fibonacci(n: int) -> list[int]:"

CONTAINER = "llama-build"
SERVER_CMD = (
    "./llama-server -m /models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf "
    "-c 32768 -tb 512 --host 0.0.0.0 --port 8080 -ngl -1 --mlock -t 32"
)

def exec_in_container(cmd):
    """Run command inside container."""
    r = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", cmd],
        capture_output=True, text=True, timeout=30)
    return r

def wait_for_server(timeout=60):
    """Wait for server to become responsive."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/v1/models",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except:
            pass
        time.sleep(2)
    return False

def restart_server():
    """Kill server, restart container, wait for server to be ready."""
    print(f"  [restart] stopping container...")
    subprocess.run(["docker", "stop", CONTAINER], capture_output=True, timeout=30)
    time.sleep(2)
    print(f"  [restart] starting container...")
    r = subprocess.run(["docker", "start", CONTAINER], capture_output=True, timeout=30)
    if r.returncode != 0:
        print(f"  [restart] FAILED: {r.stderr}")
        return False
    # Wait for container to be fully up
    time.sleep(3)
    # Wait for server to load model
    print(f"  [restart] waiting for model to load (~45s)...")
    if not wait_for_server(90):
        print(f"  [restart] server did not respond in time")
        return False
    print(f"  [restart] ready")
    return True

def get_mem_mb():
    try:
        r = exec_in_container("free -m | awk '/Mem:/{print $3}'")
        return int(r.stdout.strip())
    except:
        return None

def bench(prompt, n_predict, extra_body=None):
    payload = {"model": MODEL, "prompt": prompt, "max_tokens": n_predict}
    if extra_body:
        payload["extra_body"] = extra_body

    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/v1/completions",
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
    gen_tok = u.get("completion_tokens", 0)
    prompt_s = u.get("prompt_tokens", 1) / t["prompt_per_second"] if t["prompt_per_second"] > 0 else 0
    true_gen_s = elapsed - prompt_s
    true_gps = gen_tok / true_gen_s if true_gen_s >= 0.5 else (gen_tok / elapsed if elapsed > 0 else 0)

    return {
        "prompt_ps": round(t["prompt_per_second"], 1),
        "gen_ps": round(true_gps, 1),
        "ttft": round(t["predicted_ms"] / 1000, 3),
        "wall": round(elapsed, 2),
        "cached": t.get("cache_n", 0),
        "prompt_tok": u.get("prompt_tokens", "?"),
        "gen_tok": gen_tok,
    }

def run_test(label, prompt, n_predict, extra=None, restart=True):
    print(f"\n  --- {label} ---")
    if restart:
        if not restart_server():
            return {"label": label, "error": "server restart failed"}
        time.sleep(2)
    else:
        print(f"  [no restart]")

    mem_before = get_mem_mb()
    print(f"  [run]  ", end="", flush=True)
    r = bench(prompt, n_predict, extra)
    r["label"] = label
    mem_after = get_mem_mb()

    if "error" not in r:
        print(f"P:{r['prompt_ps']:5.0f} G:{r['gen_ps']:5.1f} "
              f"TTFT:{r['ttft']:5.2f}s W:{r['wall']:5.2f}s "
              f"gen:{r['gen_tok']}t cached:{r['cached']} RAM:{mem_before}MB")
    else:
        print(f"ERROR: {r['error']}")
    return r

# ========================
# MAIN
# ========================
print("="*75)
print("ROCm llama.cpp Benchmark (Cold Restarts)")
print(f"Container: {CONTAINER} | Port: {PORT}")
print("Model: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf")
print("Strategy: Full container restart between each test (cold start)")
print("="*75)

results = []

# Phase 1: Confirm cold baseline
print("\n" + "="*75)
print("PHASE 1: Cold Baseline")
print("="*75)
results.append(run_test("COLD ngl=-1 tb=512", PROMPT, 256, None, restart=True))

# Phase 2: Batch size (server restart between each)
print("\n" + "="*75)
print("PHASE 2: num_batch sweep")
print("="*75)
for nb in [256, 512, 1024, 2048]:
    results.append(run_test(f"num_batch={nb}", PROMPT, 256,
                             {"num_batch": nb}, restart=True))

# Phase 3: Context size
print("\n" + "="*75)
print("PHASE 3: Context size sweep")
print("="*75)
for ctx in [4096, 8192, 16384, 32768]:
    results.append(run_test(f"ctx={ctx}", PROMPT, 256,
                             {"ctx_size": ctx}, restart=True))

# Phase 4: Generation length
print("\n" + "="*75)
print("PHASE 4: Generation length")
print("="*75)
for n in [64, 128, 256, 512]:
    results.append(run_test(f"gen={n}", PROMPT, n, None, restart=True))

# Phase 5: Short prompt
print("\n" + "="*75)
print("PHASE 5: Short prompt")
print("="*75)
results.append(run_test("short-prompt", PROMPT_SHORT, 256, None, restart=True))

# ========================
# SUMMARY
# ========================
print("\n" + "="*75)
print("SUMMARY")
print("="*75)
print(f"{'Test':<25} | {'P t/s':>6} | {'G t/s':>6} | {'TTFT':>7} | {'Wall':>6} | {'GenT':>5}")
print("-"*75)
for r in results:
    if "error" not in r:
        print(f"{r['label']:<25} | {r['prompt_ps']:6.0f} | {r['gen_ps']:6.1f} | "
              f"{r['ttft']:6.2f}s | {r['wall']:6.2f}s | {r['gen_tok']:>5}")
    else:
        print(f"{r['label']:<25} | ERROR")
print()

valid = [r for r in results if "error" not in r]
if valid:
    best_gen = max(valid, key=lambda x: x["gen_ps"])
    best_ttft = min(valid, key=lambda x: x["ttft"])
    best_wall = min(valid, key=lambda x: x["wall"])
    print(f"Best gen:   {best_gen['gen_ps']} t/s ({best_gen['label']})")
    print(f"Best TTFT:  {best_ttft['ttft']}s ({best_ttft['label']})")
    print(f"Best wall:  {best_wall['wall']}s ({best_wall['label']})")
