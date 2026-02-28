# Model Safety Profile Cards

Generated: 2026-02-28

| Model | Baseline Pass^k | Best Mitigation | Best Pass^k | Best ERS | Class A | Class D | Preamble h | Experiments |
|-------|----------------|-----------------|-------------|----------|---------|---------|------------|-------------|
| GPT-5.2 | 0.261 | full_wrapper | 1.000 | 80 | 153 | 12 | 1.88 | 26 |
| Gemini 3.1 Pro | 0.980 | — | — | 63 | 78 | 18 | 0.38 | 6 |
| Grok 4.1 Fast | 0.760 | — | — | 25 | 99 | 12 | 0.98 | 6 |
| Opus 4.6 | 0.217 | preamble_only | 1.000 | 71 | 228 | 108 | 1.01 | 31 |
| Sonnet 4.5 | 0.174 | full_wrapper | 0.652 | 74 | 0 | 0 | — | 4 |
| Sonnet 4.6 | 0.130 | full_wrapper | 0.304 | 71 | 0 | 0 | — | 4 |


## GPT-5.2

- Experiments: 26
- Corpora tested: 2x2, adversarial, ceis-n5, code-agent, emergency, integrated, multimodal, seeds-2x2, seeds-llm-judged, tool-use
- Baseline Pass^k: 0.261
- Best Pass^k: 1.000 (full_wrapper)
- Best ERS: 80
- Total Class A failures: 153
- Total Class D failures: 12
- Preamble effect size (Cohen's h): 1.88


## Gemini 3.1 Pro

- Experiments: 6
- Corpora tested: emergency, seeds-2x2, seeds-llm-judged
- Baseline Pass^k: 0.980
- Best ERS: 63
- Total Class A failures: 78
- Total Class D failures: 18
- Preamble effect size (Cohen's h): 0.38


## Grok 4.1 Fast

- Experiments: 6
- Corpora tested: emergency, seeds-2x2, seeds-llm-judged
- Baseline Pass^k: 0.760
- Best ERS: 25
- Total Class A failures: 99
- Total Class D failures: 12
- Preamble effect size (Cohen's h): 0.98


## Opus 4.6

- Experiments: 31
- Corpora tested: 2x2, adversarial, code-agent, defer, emergency, integrated, multimodal, rag, seeds-2x2, seeds-llm-judged, tool-use
- Baseline Pass^k: 0.217
- Best Pass^k: 1.000 (preamble_only)
- Best ERS: 71
- Total Class A failures: 228
- Total Class D failures: 108
- Preamble effect size (Cohen's h): 1.01


## Sonnet 4.5

- Experiments: 4
- Corpora tested: 2x2
- Baseline Pass^k: 0.174
- Best Pass^k: 0.652 (full_wrapper)
- Best ERS: 74
- Total Class A failures: 0
- Total Class D failures: 0


## Sonnet 4.6

- Experiments: 4
- Corpora tested: 2x2
- Baseline Pass^k: 0.130
- Best Pass^k: 0.304 (full_wrapper)
- Best ERS: 71
- Total Class A failures: 0
- Total Class D failures: 0
