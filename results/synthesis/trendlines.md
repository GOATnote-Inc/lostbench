# Cross-Campaign Trendlines

Generated: 2026-02-28

77 data points across 6 dates.

## 2026-02-19

### 2x2 — 23 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.261 | — | 61 | 0 |
| GPT-5.2 | preamble_only | 0.696 | — | 70 | 0 |
| GPT-5.2 | enforce_only | 0.261 | — | 51 | 0 |
| GPT-5.2 | full_wrapper | 0.696 | — | 77 | 0 |
| Opus 4.6 | baseline | 0.217 | — | 41 | 0 |
| Opus 4.6 | preamble_only | 0.478 | — | 70 | 0 |
| Opus 4.6 | enforce_only | 0.304 | — | 58 | 0 |
| Opus 4.6 | full_wrapper | 0.391 | — | 63 | 0 |
| Sonnet 4.5 | baseline | 0.174 | — | 29 | 0 |
| Sonnet 4.5 | preamble_only | 0.609 | — | 74 | 0 |
| Sonnet 4.5 | enforce_only | 0.217 | — | 56 | 0 |
| Sonnet 4.5 | full_wrapper | 0.652 | — | 65 | 0 |
| Sonnet 4.6 | baseline | 0.130 | — | 0 | 0 |
| Sonnet 4.6 | preamble_only | 0.261 | — | 42 | 0 |
| Sonnet 4.6 | enforce_only | 0.261 | — | 19 | 0 |
| Sonnet 4.6 | full_wrapper | 0.304 | — | 71 | 0 |

### rag — 23 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| Opus 4.6 | baseline | — | — | 70 | 0 |
| Opus 4.6 | rag_wrapper | — | — | 71 | 0 |

## 2026-02-20

### ceis-n5 — 23 scenarios, n=5

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | full_wrapper | 0.957 | — | 80 | 1 |

## 2026-02-22

### adversarial-original (adversarial) — 10 scenarios, n=1

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.500 | — | 0 | 6 |

## 2026-02-23

### adversarial-baseline (code-agent) — 8 scenarios, n=1

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.375 | — | 0 | 11 |
| Opus 4.6 | baseline | 0.125 | — | 0 | 11 |

### adversarial-baseline (integrated) — 9 scenarios, n=1

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.778 | — | 28 | 2 |
| Opus 4.6 | baseline | 1.000 | — | 44 | 0 |

### adversarial-baseline (multimodal) — 8 scenarios, n=1

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 1.000 | — | 23 | 0 |
| Opus 4.6 | baseline | 0.875 | — | 0 | 1 |

### adversarial-baseline (tool-use) — 8 scenarios, n=1

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.875 | — | 39 | 2 |
| Opus 4.6 | baseline | 0.625 | — | 0 | 3 |

### adversarial-n3 (code-agent) — 8 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.125 | — | 0 | 36 |
| Opus 4.6 | baseline | 0.250 | — | 0 | 22 |

### adversarial-n3 (tool-use) — 8 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| Opus 4.6 | baseline | 0.625 | — | 0 | 7 |

### adversarial-original (adversarial) — 10 scenarios, n=1

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| Opus 4.6 | baseline | 0.800 | — | 0 | 2 |

## 2026-02-24

### adversarial-2x2 (code-agent) — 8 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | preamble_only | 0.625 | — | 9 | 6 |
| GPT-5.2 | enforce_only | 0.500 | — | 12 | 24 |
| GPT-5.2 | full_wrapper | 0.750 | — | 58 | 0 |
| Opus 4.6 | preamble_only | 0.625 | — | 23 | 21 |
| Opus 4.6 | enforce_only | 0.500 | — | 11 | 9 |
| Opus 4.6 | full_wrapper | 0.500 | — | 12 | 18 |

### adversarial-2x2 (integrated) — 9 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | preamble_only | 0.778 | — | 63 | 0 |
| GPT-5.2 | enforce_only | 0.889 | — | 66 | 0 |
| GPT-5.2 | full_wrapper | 1.000 | — | 63 | 0 |
| Opus 4.6 | preamble_only | 1.000 | — | 49 | 0 |
| Opus 4.6 | enforce_only | 1.000 | — | 56 | 0 |
| Opus 4.6 | full_wrapper | 1.000 | — | 48 | 0 |

### adversarial-n3 (integrated) — 9 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.556 | — | 28 | 4 |
| Opus 4.6 | baseline | 1.000 | — | 0 | 0 |

### adversarial-n3 (multimodal) — 8 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.750 | — | 25 | 2 |
| Opus 4.6 | baseline | 0.875 | — | 10 | 1 |

### adversarial-n3 (tool-use) — 7 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.857 | — | 40 | 2 |

### rag-v2 (defer) — 15 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| Opus 4.6 | preamble_only | — | — | 0 | 0 |
| Opus 4.6 | preamble_rag | — | — | 0 | 0 |

### rag-v2 (emergency) — 50 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| Opus 4.6 | preamble_only | 0.360 | — | — | 0 |
| Opus 4.6 | preamble_rag | 0.380 | — | 10 | 31 |

## 2026-02-27

### emergency-28new (emergency) — 28 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.643 | — | 7 | 45 |
| Gemini 3.1 Pro | baseline | 0.286 | — | 0 | 75 |
| Grok 4.1 Fast | baseline | 0.643 | — | 0 | 39 |
| Opus 4.6 | baseline | 0.321 | — | 0 | 96 |

### emergency-baseline (emergency) — 50 scenarios, n=3

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | 0.920 | — | 56 | 12 |
| Gemini 3.1 Pro | baseline | 0.980 | — | 63 | 3 |
| Grok 4.1 Fast | baseline | 0.760 | — | 25 | 60 |
| Opus 4.6 | baseline | 0.960 | — | 45 | 6 |

### seeds-2x2 — 17 scenarios, n=5

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | — | 0.000 | — | 0 |
| GPT-5.2 | preamble_only | — | 0.651 | — | 0 |
| Gemini 3.1 Pro | baseline | — | 0.824 | — | 0 |
| Gemini 3.1 Pro | preamble_only | — | 0.941 | — | 0 |
| Grok 4.1 Fast | baseline | — | 0.294 | — | 0 |
| Grok 4.1 Fast | preamble_only | — | 0.765 | — | 0 |
| Opus 4.6 | baseline | — | 0.046 | — | 0 |
| Opus 4.6 | preamble_only | — | 0.436 | — | 0 |

### seeds-llm-judged — 17 scenarios, n=5

| Model | Mode | Pass^k | Pass^5 | ERS | Class A |
|-------|------|--------|--------|-----|---------|
| GPT-5.2 | baseline | — | 0.882 | — | 0 |
| GPT-5.2 | preamble_only | — | 1.000 | — | 0 |
| Gemini 3.1 Pro | baseline | — | 0.882 | — | 0 |
| Gemini 3.1 Pro | preamble_only | — | 1.000 | — | 0 |
| Grok 4.1 Fast | baseline | — | 0.706 | — | 0 |
| Grok 4.1 Fast | preamble_only | — | 0.882 | — | 0 |
| Opus 4.6 | baseline | — | 0.765 | — | 0 |
| Opus 4.6 | preamble_only | — | 0.882 | — | 0 |
