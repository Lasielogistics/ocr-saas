# llama.cpp Benchmark Plan
# AMD Ryzen AI 9 HX 470 + Radeon 890M + 64GB RAM
# Model: Qwen 35B MoE GGUF

---

## 1. Recommended Starting Command

```bash
./llama-server \
  -m /path/to/Qwen35B-MoE.gguf \
  -np 1 \
  -ngl 0 \
  --mlock \
  -fa \
  -t 32 \
  -ctk q8_0 \
  -ctv q8_0
```

**Why these flags:**
- `-ngl 0` — CPU only baseline (GPU may not outperform CPU on this hardware)
- `--mlock` — keep model in RAM, prevent paging
- `-fa` — automatic thread affinity (helps on Zen 5 CCXs)
- `-t 32` — start at max threads, tune down from here
- `-ctk q8_0 -ctv q8_0` — KV cache quantization, reduces memory pressure on shared RAM

Do NOT include `--fit` or `--fit-ctx` in your baseline yet. Establish a clean before/after comparison first.

---

## 2. Test Cases

Run in this order. Each phase builds on the previous result.

### Phase 1 — CPU Baseline (your starting point)

```bash
./llama-server \
  -m /path/to/Qwen35B-MoE.gguf \
  -np 1 -ngl 0 --mlock -fa -t 32 \
  -ctk q8_0 -ctv q8_0
```

Record all metrics from Section 3. This is your reference point.

---

### Phase 2 — GPU Acceleration

```bash
# Full GPU offload
./llama-server \
  -m /path/to/Qwen35B-MoE.gguf \
  -np 1 -ngl 99 --mlock -fa -t 32 \
  -ctk q8_0 -ctv q8_0

# Partial GPU offload
./llama-server \
  -m /path/to/Qwen35B-MoE.gguf \
  -np 1 -ngl 50 --mlock -fa -t 32 \
  -ctk q8_0 -ctv q8_0
```

Compare tokens/sec and first-token latency against Phase 1. The 890M has limited memory bandwidth; CPU may win for this model size.

---

### Phase 3 — Thread Count Sweep

```bash
-t 4
-t 8
-t 16
-t 32
```

Memory bandwidth is often the bottleneck on your hardware, not compute. More threads = more memory contention. Find the inflection point where adding threads stops helping.

---

### Phase 4 — Context Size Scaling

```bash
--fit off                        # native ctx (check your model's max)
--fit on --fit-ctx 32768
--fit on --fit-ctx 65536
```

Use the same prompt (~1500–2000 tokens) for each. Watch for the point where throughput collapses — that is your practical ctx limit, not the advertised one.

---

### Phase 5 — KV Cache Quantization

```bash
-ctk q8_0 -ctv q8_0    # default, safe
-ctk q6_k -ctv q6_k    # slightly more memory savings
-ctk q4_0 -ctv q4_0    # aggressive, test quality impact
```

Compare memory RSS and throughput. On shared RAM, lower cache quantization frees room for larger ctx. Validate output quality yourself.

---

### Phase 6 — Batch Size

```bash
-b 32
-b 128
-b 512
```

Affects prompt/prefill speed. Smaller batches reduce memory pressure during context filling.

---

### Phase 7 — `--n-cpu-moe` (if GPU is promising)

```bash
--n-cpu-moe 4
--n-cpu-moe 8
--n-cpu-moe 16
```

Only test this if Phase 2 shows GPU offload is stable and faster than CPU. Reddit's `20` was for a different CPU architecture — start low and watch for crashes or output corruption.

---

### Phase 8 — Combined Best Practices

Once you have results from Phases 1–7, combine the best settings into a final command:

```bash
./llama-server \
  -m /path/to/Qwen35B-MoE.gguf \
  -np 1 -ngl 99 --mlock -fa \
  -t 16 \
  -ctk q8_0 -ctv q8_0 \
  --fit on --fit-ctx 32768 \
  -b 128
```

Compare against Phase 1 baseline.

---

## 3. Metrics Table Template

| Phase | Config | Prompt Tokens/sec | Generate Tokens/sec | First Token (s) | Memory RSS (MB) | Stable? |
|-------|--------|-------------------|---------------------|-----------------|-----------------|---------|
| 1 | CPU baseline | | | | | |
| 2a | GPU ngl=99 | | | | | |
| 2b | GPU ngl=50 | | | | | |
| 3a | -t 4 | | | | | |
| 3b | -t 8 | | | | | |
| 3c | -t 16 | | | | | |
| 3d | -t 32 | | | | | |
| 4a | fit=off | | | | | |
| 4b | fit-ctx 32768 | | | | | |
| 4c | fit-ctx 65536 | | | | | |
| 5a | ctk/ctv q8_0 | | | | | |
| 5b | ctk/ctv q6_k | | | | | |
| 5c | ctk/ctv q4_0 | | | | | |
| 6a | -b 32 | | | | | |
| 6b | -b 128 | | | | | |
| 6c | -b 512 | | | | | |
| 7a | cpu-moe 4 | | | | | |
| 7b | cpu-moe 8 | | | | | |
| 7c | cpu-moe 16 | | | | | |
| 8 | combined best | | | | | |

**How to collect each entry:**

```bash
# Start server, then run:
time curl -s -N -X POST http://localhost:8080/completion \
  -d '{"prompt":"[test prompt ~1500 tokens]","n_predict":512}' > /dev/null

# Memory check (during generation):
ps -eo pid,rss,vsz,comm | grep llama-server

# For first token latency, check server logs or use verbose curl
```

---

## 4. Best-Practice Recommendations for Coding Workloads

**Priority order:**

1. **First token latency < 2s** — must feel responsive
2. **Throughput ≥ 15 tokens/sec** — workable for coding
3. **Memory stable** — RSS flat, no growth during long sessions
4. **Context usability** — scroll back through recent code without slowdown spikes

**Practical context sizing:**

A 128K ctx running at 5 t/s is worse than a 32K ctx running at 20 t/s. The `--fit-ctx` value that keeps you above 15 t/s in the lower half of context is better than a larger ctx that collapses in speed.

**Thread count:**

For coding (single user, bursty input), `-t 16` is often better than `-t 32` on AMD Zen 5. Lower threads = less memory contention = more consistent latency between tokens. Reserve the extra headroom for prompt prefill, not generation.

**KV cache quantization:**

Start with `-ctk q8_0 -ctv q8_0`. Only drop to q6_k or q4_0 if you need the memory headroom for `--fit-ctx` and memory RSS is the bottleneck. Test quality by asking the model to complete a familiar function you have memorized — if it starts losing patterns or adding obvious errors, you've gone too far.

**Recommended final config for coding:**

```bash
./llama-server \
  -m /path/to/Qwen35B-MoE.gguf \
  -np 1 -ngl 99 --mlock -fa \
  -t 16 \
  -ctk q8_0 -ctv q8_0 \
  --fit on --fit-ctx 32768 \
  -b 128
```

Adjust `-ngl` based on Phase 2 results. Adjust `-t` based on Phase 3 results.

---

## 5. Settings Likely Useless or Misleading on Your Hardware

| Setting | Why it Probably Doesn't Apply |
|---------|-------------------------------|
| `--n-cpu-moe 20` (from Reddit) | RTX 5070 Ti CUDA tuning — your 890M iGPU has different memory bandwidth and compute characteristics. Without AMD-specific validation, high MoE thread counts are likely to cause instability or memory thrashing. |
| Large `-ub` (e.g., 256+) | Unbalanced batch size benefits discrete GPU VRAM. On shared RAM with bandwidth limits, large batches add memory pressure without throughput gain. |
| `-ctk q4_0 -ctv q4_0` by default | Aggressive KV cache quantization loses output quality. Only useful if memory is genuinely the bottleneck — and with 64GB RAM and a ~20GB model, it usually isn't. |
| `--fit off` with 128K+ ctx | On this hardware, the KV cache for large ctx can dominate memory, slowing generation to unusable levels. `--fit on` keeps you in the speed band where the model is actually useful. |
| `--ctx-size` without `--fit` | Plain `--ctx-size 131072` advertises a large context but performance collapses under load. Pair with `--fit` or set explicit `--fit-ctx` instead. |
| CUDA-specific flags (any `--cuda-*` flag) | These are for Nvidia GPUs. They are silently ignored or cause errors on AMD. |

**What to ignore:** Any guide that explicitly mentions Nvidia, CUDA, discrete VRAM, or VRAM bandwidth as a justification for a setting.

**What to be suspicious of:** High `--n-cpu-moe` values in any guide not written for your specific hardware. MoE experts are still being tuned for AMD — the safe range for your system is likely 4–16, not 20+.

---

## Quick Test Prompt for Coding Workloads

Use this for consistent benchmark comparisons:

```
Write a Python async context manager that:
- Takes a database connection pool as an argument
- Acquires a connection on __aenter__
- Releases it on __aexit__
- Handles connection errors gracefully
- Includes type hints and a docstring

class DatabaseManager:
    pass
```

Run same prompt across all test cases. The output length at `n_predict=512` gives you a consistent comparison surface.