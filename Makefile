.PHONY: test lint regression regression-codeagent regression-integrated

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
