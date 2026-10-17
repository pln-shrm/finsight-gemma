# Demo script and submission checklist

## 90-second demo (rehearse 3 times)

| t | Screen | Say |
|---|---|---|
| 0:00 | Slide: a well-known misleading chart | "Analysts lose hours checking whether charts and tables agree. We automate that, and prove every number." |
| 0:10 | Terminal: `finsight run demo/filings/<deck-or-10k>.pdf` | "Gemma 4 reads the charts and tables. It does not do any math." |
| 0:25 | Harness log: first extraction fails an identity check, residual shown, retry fixes it | "When assets don't equal liabilities plus equity, we feed the exact residual back. Max three tries, then it refuses." |
| 0:40 | Report: Spin Doctor box: lie factor on a truncated chart; non-GAAP bloat; cash conversion | "This chart shows +5% as +50%. Lie factor 10. Here is the page and the crop." |
| 0:55 | Click a number: cropped source image beside it | "Every number links to its source." |
| 1:05 | DCF: sensitivity grid + histogram p10/p50/p90 | "No point estimates. A distribution, computed in plain Python." |
| 1:15 | Wi-Fi off, rerun with `--backend local` (or `--replay`) | "Same pipeline fully local on open weights. Nothing leaves the laptop." |
| 1:25 | Repo + benchmark table | "Open source, Apache-2.0, ships as a portable Agent Skill. Here are the measured results." |

**Fallbacks:** (1) `--replay` cached run; (2) pre-recorded screen capture (record at P5); (3) static `report.html` already generated. Test all three on the demo machine.

## Judges' likely questions (prepare answers)
- *Why not just prompt a big model to do it?* Unverifiable arithmetic, no provenance; we show failure cases from the ablation.
- *How accurate is the small local model?* Quote the benchmark table, including where it fails.
- *Is this accusing companies of fraud?* No: indicators with evidence; screening only.
- *What is original?* Harness (solver-driven retry, text-layer provenance, CV+VLM chart forensics, cache/replay), the skill, the benchmark.
- *Could this generalize?* Add unit rules/identities per jurisdiction via `references/`; ratios are pluggable.

## Prize criteria to evidence mapping

| Criterion | Evidence in repo |
|---|---|
| Open-source/open-weight AI important to how it works | Gemma 4 does all extraction; ablation shows project fails without it |
| Public GitHub repo + open-source license | repo URL, `LICENSE` (Apache-2.0), topic `hacktoberfest` |
| Agent skill complies with the open standard | `skills/finsight-quant-analyst`, `skills-ref validate` output pasted in README |
| Model harness: original implementation or meaningful changes | `src/finsight/` (backends, solver loop, provenance, cache); described in `docs/architecture.md` |
| Gemma 4: multimodal | charts and scanned tables read as images |
| Gemma 4: focused tool for productivity | filing audit for analysts/students |
| Gemma 4: rapid prototype via Gemini API | `GeminiBackend`, `--backend cloud` |
| Original project | commit history showing work during the event |

## README must contain
Pitch · 20-second demo GIF · architecture diagram · quickstart in at most 5 commands · why open weights · benchmark table (copied from results) · limitations (honest) · skill install · license + disclaimer.

## DEV post / writeup outline (`docs/WRITEUP.md`)
1. Problem. 2. Insight: model reads, code computes. 3. Harness design (retry-with-residual loop is the hook). 4. Chart forensics and lie factor. 5. Benchmark results incl. failures. 6. Local vs cloud. 7. How to use the skill. 8. What we would build next.

## Submission checklist
- [ ] Rules re-read; team and format confirmed
- [ ] Repo public; `LICENSE` present; `hacktoberfest` topic added
- [ ] `pytest` green on a clean clone; quickstart verified on a second machine
- [ ] `skills-ref validate skills/finsight-quant-analyst` passes
- [ ] Skill tested end to end inside Antigravity on a sample PDF
- [ ] `bench/results/summary.md` committed; README numbers match
- [ ] No secrets, `.env`, `.cache/`, or copyrighted filings committed
- [ ] Demo video recorded (backup); replay cache recorded
- [ ] README limitations + disclaimer included
- [ ] Writeup/DEV post published (if required) and linked
- [ ] Submission form filled with repo link, demo link, category choices
- [ ] Commit history shows incremental work
