# finsight-bench: evaluation plan

Goal: replace claims with measurements. Publish whatever we get, including failures.

## Suites

### A. Synthetic chart suite (exact ground truth, built in T-09)
`bench/synth_charts.py` generates N (suggest 60) matplotlib bar charts:
- axis_min in {0, 50%, 80%, 90%, 95% of the smallest bar}; 2 to 6 bars; data labels printed on bars; varied colors, fonts, sizes, gridlines.
- Variants: faithful (axis_min=0) vs truncated; with and without printed values; 10 with a secondary axis (expected: flagged as dual-axis, not scored).
- Ground truth JSON per image: `{axis_min, values, labels, true_lie_factor_pairs, should_flag}` where `should_flag = |LF-1| > 0.05` for any adjacent pair (computed with `lie_factor_from_axis`).

### B. Real chart/table set (hand-labeled, 20 to 50 items if time allows)
- Sources: public earnings decks and annual reports (US and Indian). Do not commit copyrighted pages; commit only labels and a download script/list.
- Per item: statement fields (about 15) with page and value; for charts: axis_min, printed values, whether truncated.
- Include 3 to 5 known misleading charts and 3 to 5 clean ones.

### C. Injected-error suite (solver/harness test)
Take verified financials, perturb one field (swap columns, scale by 100x, drop a digit), feed through a stub backend that returns the corrupted JSON first and the correct one after a targeted prompt. Measures repair rate and retries.

## Metrics

| Metric | Definition |
|---|---|
| Field accuracy | extracted value within 0.5% of ground truth (per field and per document) |
| Abstain rate | fields returned null; reported separately from wrong values |
| Identity pass rate | share of documents passing all error-level checks, before vs after retry |
| Mean retries | per document |
| Chart read accuracy | axis_min exact, printed values exact |
| Detector precision / recall | `flag` vs `should_flag` on suites A and B |
| Lie-factor error | abs(measured LF - true LF) when both defined (analytic vs CV) |
| Latency, calls, tokens | per document, per backend |
| Local vs cloud | same suites on `gemma4:e4b` local and Gemini API Gemma 4 |

## Ablation table (fill in `bench/results/summary.md`)

| Configuration | Field acc. | Identity pass | Retries | Detector P/R |
|---|---|---|---|---|
| A. Model, free-form JSON | | | | |
| B. + schema-constrained + Pydantic | | | | |
| C. + solver retry loop | | | | |
| D. + cascade triage (token cost only) | | | | |
| Local e4b vs cloud (best config) | | | | |

## Rules
- Fixed seeds, temperature 0, record model IDs and versions in the results file.
- Label ground truth before running models (no peeking).
- Report failures with 3 concrete examples and why they failed.
- Any README number must be copy-pasted from `bench/results/summary.md`.
