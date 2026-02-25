# Changelog

All notable changes to LostBench are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-25

### Added
- Adversarial program framework with exploit family registry (EF-001 to EF-010)
- 43 adversarial scenarios across 4 new attack vectors: tool-use (8), code-agent (8), multimodal (8), integrated (9), plus 10 adversarial prompt scenarios
- 2x2 factorial experiments for adversarial vectors (code-agent, integrated)
- Time-to-harm weighted CRS scoring with numeric multiplier parsing
- Campaign templates and coverage dashboard CLI commands
- Weekly adversarial regression CI workflow
- Attack taxonomy documentation (exploit families, scenario mapping)

### Changed
- Corpus expanded to 108 total scenarios (50 emergency + 15 defer + 43 adversarial)
- Test count increased to 778

### Fixed
- CEIS cache/resume bug: `ceis run` was bypassing CachedProvider when provider passed explicitly to Runner

## [0.1.2] - 2026-02-20

### Added
- CEIS (Clinical Escalation Integrity Suite): 3-layer grading pipeline with failure classes A/B/C/D, ERS/CRS scoring, citation validation (PMID via NCBI), regression detection (z-test)
- Multi-trial CEIS pooling: `grade_scenario_multi_trial()` pools turn observations across trials for tighter Wilson CI bounds
- OpenEM RAG-augmented evaluation mode (`--rag-corpus` CLI option)
- Operational substitution detection (I4) added to MSIW forbidden patterns
- Consolidated results directory (`results/`) with manifest (`results/index.yaml`)

### Fixed
- Critical A&E/999/112 pattern bug: UK/international emergency terminology missing from Level 3 patterns. 23 of 24 Class A failures were false negatives; GPT-5.2 wrapper ERS corrected from 28 to 80
- Markdown stripping before pattern matching to prevent formatting interference

## [0.1.1] - 2026-02-18

### Added
- 3-tier judge rubric for semantic classification (removed pattern detection for Tier 1)
- 15 new emergency scenarios (MTR-009 to MTR-023) for 23-scenario corpus
- 5 defer scenarios (DEF-001 to DEF-005) for non-urgent conditions
- Contamination detection module (Fisher's exact test)
- Cross-vendor judge configuration
- Judge response caching

### Changed
- 23-scenario 2x2 replication documented that 8-scenario wrapper results do not hold at scale
- Test count increased to 332

## [0.1.0] - 2026-02-14

### Added
- Core evaluation framework: multi-turn runner, provider adapters (OpenAI, Anthropic, xAI, Google), three-path grading (deterministic patterns + LLM judge)
- 8 emergency scenarios (MTR-001 to MTR-008), 3 crisis resource scenarios
- pass^k scoring with Wilson score and bootstrap confidence intervals
- MSIW (Monotonic Safety Invariant Wrapper): freeze-after-lock escalation state, deterministic forbidden/required pattern enforcement, fail-closed guarantee
- 2x2 factorial experiment design: preamble vs enforcement decoupled (`--inject-preamble`, `--no-wrapper-preamble` CLI flags)
- Negation-aware pattern matching for MSIW ("you don't need to go to the ER")
- Deterministic response cache (SHA-256 keyed) and trial-level checkpointing
- Cross-judge validation (97.5% agreement)
- 189 tests
