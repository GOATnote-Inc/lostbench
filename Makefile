.PHONY: test lint regression regression-codeagent regression-integrated safety-briefs mine-analysis hypotheses loop-dry

test:
	pytest tests/ -q

lint:
	ruff check . && ruff format --check .

regression: regression-codeagent regression-integrated
	@echo "Regression complete. Compare results against results/index.yaml baseline."

regression-codeagent:
	@echo "Running code-agent regression (n=3)..."
	lostbench ceis run --config configs/ceis_codeagent_gpt52_n3.yaml
	lostbench ceis run --config configs/ceis_codeagent_opus46_n3.yaml

regression-integrated:
	@echo "Running integrated regression (n=3)..."
	lostbench ceis run --config configs/ceis_integrated_gpt52_n3.yaml
	lostbench ceis run --config configs/ceis_integrated_opus46_n3.yaml

safety-briefs:
	python3 scripts/generate_safety_briefs.py

mine-analysis:
	@echo "Running mining analysis pipeline..."
	python3 scripts/generate_hypotheses.py
	python3 scripts/propose_exploit_families.py
	python3 scripts/synthesize_risk.py
	@echo "Mining analysis complete. Check results/analysis/ and results/synthesis/."

hypotheses:
	python3 scripts/generate_hypotheses.py

loop-dry:
	@echo "Running learning loop (dry run, no API calls)..."
	python3 scripts/learning_loop.py --dry-run --models gpt-5.2 claude-opus-4-6
