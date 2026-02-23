# Results Rules

## Manifest
- `results/index.yaml` is the single source of truth for all result directories
- When creating new result directories, update `results/index.yaml`

## Directory Naming
- Format: `results/{experiment-type}/{model}-{mode}/`
- Experiment types: `2x2`, `ceis-n5`, `ceis-regrade`, `rag`
- Model names: lowercase, hyphenated (e.g., `gpt-5.2`, `opus46`)
- Modes: `baseline`, `wrapper`, `preamble`, `enforce-only`

## Cached Results
- NEVER edit files in existing result directories
- Results are immutable once written — create new directories for new runs
- To regrade existing results, use `scripts/regrade_ceis.py` — it writes to a new output directory
