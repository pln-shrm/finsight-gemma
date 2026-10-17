# FinSight-Gemma

> Scan a filing, know what's actually in it. Gemma 4 reads the charts and tables; deterministic code checks the math; every number links back to its source page.

**Status:** hackathon build in progress. See `plan.md`. Fill in the sections below as they become true; do not claim anything the benchmark does not show.

## What it does
- Extracts financial statements and charts from PDFs using Gemma 4 (cloud via Gemini API, or fully local via Ollama).
- Verifies accounting identities, retries the model with exact residuals when they fail.
- Flags misleading charts (Tufte lie factor, truncated axes) and non-GAAP bloat.
- Computes DuPont, Altman Z'', Beneish M, Piotroski F, and a distribution-based DCF in plain Python.
- Ships as a Python harness **and** a portable Agent Skill (`skills/finsight-quant-analyst`).

## Why open weights
Filings can be confidential and analysts often work offline. `--backend local` never leaves the machine. (TODO: add measured local vs cloud accuracy from `bench/results/`.)

## Quickstart
```bash
pip install -e ".[dev]"
ollama pull gemma4:e4b          # and/or export GEMINI_API_KEY=...
finsight run demo/filings/<file>.pdf --workspace ./workspace
```

## Results
(TODO: paste the ablation table from `bench/results/summary.md`.)

## Agent Skill
Drop `skills/finsight-quant-analyst/` into any agent's skills directory (e.g. `.agents/skills/`). Spec-validated with `skills-ref`.

## License
Apache-2.0. Not investment advice.
