# RAG knowledge base project shorthand commands.
# Usage:
#   make eval                               # run baseline eval (full pipeline, real LLM/Embed/Rerank)
#   make eval ARGS="--limit 5"              # small smoke: only first 5 testset items
#   make eval ARGS="--limit 5 --top-k 5"    # smoke + set retrieval top_k
#   make eval-dry-run                       # validate testset only, NO external calls

PYTHON ?= python

.PHONY: eval eval-dry-run help

help:
	@echo "eval            run retrieval baseline (real pipeline)"
	@echo "  args: --limit N (testset items)  --top-k N  --configs JSON  --dry-run"
	@echo "eval-dry-run    validate testset only (no API calls)"

# Real baseline run. Reuses app/services/evaluation_service.py + eval_testset.py.
eval:
	$(PYTHON) scripts/eval_runner.py $(ARGS)

# Dry-run: only stats + field validation, never touches retrieval/LLM/embed/rerank.
eval-dry-run:
	$(PYTHON) scripts/eval_runner.py --dry-run