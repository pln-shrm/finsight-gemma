# plan.md: FinSight-Gemma build plan

**Pitch (one line):** Scan a filing, know what's actually in it. Gemma 4 reads charts and tables; deterministic code checks the math; every number links to its source page.

**Core principle:** *The model reads, code computes.* Everything numeric is plain, tested Python.

**Targets:** Best Open-Source AI Project **and** Best Use of Gemma 4 (one repo, one project).
Nobody can guarantee a win. What we control: a working demo, measured results, a clean spec-compliant repo.

---

## 0. Assumptions (edit these first)

| Item | Assumed | Change if different |
|---|---|---|
| Team | 1 to 3 people | split lanes in section 5 |
| Event length | about 10 working hours | use the 6-hour cut line in section 4 |
| Hardware | one laptop able to run `gemma4:e4b`; maybe a bigger model | `config.toml` |
| Network | Gemini API reachable on the day | local-only fallback + replay cache |

**Rules check (do before anything else):** read the event page for (a) whether pre-written code is allowed, (b) submission format (repo link, DEV post, video?), (c) whether the DigitalOcean sponsor integration is required or optional, (d) team size limits. The seed code in this repo (`src/finsight/{schemas,solver,lie_factor,forensics,dcf}.py` + tests) is a tested spec of the math. If pre-written code is not allowed, treat it as the specification and have Antigravity re-implement it during the event against the same tests; the tests are the contract.

---

## 1. What we are building (final scope)

Merged from the two idea sets:

1. **Harness** (`src/finsight/`): cascade router, backends (Gemini API + Ollama), Pydantic-constrained extraction, symbolic accounting solver with targeted retries, provenance resolver, call cache with replay.
2. **Spin Doctor**: chart forensics (Tufte lie factor, truncated axes, dual-axis flag), non-GAAP reconciliation footing and bloat, cash-conversion quality of earnings.
3. **Quant helpers**: DuPont 5-factor, Altman Z'' (and Z), Beneish M, Piotroski F, sensitivity matrix + Monte Carlo DCF.
4. **Agent Skill** (`skills/finsight-quant-analyst/`): spec-compliant, portable, self-describing.
5. **finsight-bench**: synthetic manipulated charts with exact ground truth + hand-labeled real pages; ablation table.
6. **Sourced report**: self-contained HTML, cropped source snippet beside every number.

Improvements over the original plans (see `decisions.md` for reasoning): provenance from the PDF text layer not model boxes; CV measures bar geometry, model only reads semantics; deterministic triage before any model call; `total_liabilities` optional (many 10-Ks omit it); non-GAAP table footing check; record/replay cache for a bulletproof demo; prompt-injection hardening; explicit abstention; honest benchmark instead of unmeasured claims.

---

## 2. Tiers and cut lines

| Tier | Contents | Rule |
|---|---|---|
| **T1 Must** | ingest + deterministic triage; Gemma extraction (cloud + local) with schema + solver retry; provenance; lie factor on charts; ratios/forensics; DCF; CLI `run`; SKILL.md valid; README | demo fails without these |
| **T2 Should** | HTML report with cropped citations; synthetic chart benchmark + ablation table; non-GAAP recon audit; replay cache; CV bar measurement | what separates us from other entries |
| **T3 Stretch** | Stage-1 small-model triage; MCP server wrapper; Indian filing polish; claim checker (MD&A text vs numbers); Streamlit UI; DigitalOcean deployment | only after T1+T2 are green |
| **Cut** | PIT factor backtester (single-company backtests are meaningless; needs a cross-section of filings and price data); live trading anything | do not build in the event |

**Freeze rule:** at H8 (of 10) no new features. H8 to H10 is benchmark, README, rehearsal, submission.

---

## 3. Pre-event prep (safe, no project code)

- [ ] Install Ollama; `ollama pull gemma4:e4b` (and `gemma4:26b` if hardware allows). Confirm tags with `ollama list`.
- [ ] Get a Gemini API key; confirm the Gemma 4 model ID from the models list (config says `gemma-4-31b-it`; verify).
- [ ] Download 4 to 6 **public** filings into `demo/filings/` (not committed): one US 10-K (e.g. NVIDIA), one earnings deck PDF, one Indian annual report extract (e.g. Infosys or Eternal/Zomato), one with a visibly messy chart.
- [ ] Find 1 widely known "misleading chart" example for the demo opener.
- [ ] Create the GitHub repo (public), pick Apache-2.0 via the license picker, add topic `hacktoberfest`.
- [ ] Install Antigravity, open the folder, confirm it picks up `AGENTS.md` and `.agents/skills`.

---

## 4. Timeline (10-hour version)

Gate = must pass before moving on. If a gate slips by more than 45 minutes, apply the cut in the last column.

| Phase | Time | Work | Gate | If late |
|---|---|---|---|---|
| **P0 Bootstrap** | 0:00 to 0:45 | repo, venv, `pytest` green, verify model IDs, smoke test one page image through both backends | both backends return a structured answer about a page image | local-only or cloud-only; note it |
| **P1 Ingest + triage** | 0:45 to 2:00 | PyMuPDF render + text layer; keyword page scoring; `triage.json`; cache | triage picks the statement pages of 3 filings correctly | skip small-model stage (already T3) |
| **P2 Extraction harness** | 2:00 to 4:30 | backend adapters with schema-constrained output; extraction prompts; solver retry loop (max 3); provenance resolver; cassette cache | one real filing: JSON validates, `verify` passes or fails with a meaningful residual | extract balance sheet + income statement only |
| **P3 Chart forensics** | 4:30 to 6:30 | chart extraction prompt; analytic lie factor; CV bar measurement; synthetic chart generator; non-GAAP recon extraction + footing | detector flags a synthetic truncated chart and passes a zero-baseline one | drop CV; keep analytic axis model |
| **P4 Analyze + report** | 6:30 to 7:45 | wire forensics + DCF to CLI; HTML report with crops | `finsight run` produces a report end to end | report as Markdown without crops |
| **P5 Bench + docs** | 7:45 to 9:00 | run benchmark, ablation table, README, skill validation, record cassettes | table in README matches `bench/results/` | fewer test cases; say so honestly |
| **P6 Freeze + submit** | 9:00 to 10:00 | rehearse demo 3x, record backup video, submission checklist | checklist in `docs/demo-and-submission.md` fully ticked | n/a |

**6-hour cut line:** analytic lie factor only (no CV), cloud backend primary + local smoke test, no HTML crops (page numbers only), benchmark = synthetic charts + 5 hand-labeled pages.

---

## 5. Lanes for a team of 2 or 3

| Lane | Owner | Owns |
|---|---|---|
| A: Harness | dev 1 | backends, extraction, retry loop, provenance, cache |
| B: Forensics + bench | dev 2 | charts, CV, synthetic generator, benchmark, non-GAAP |
| C: Product | dev 3 (or A/B after P3) | CLI, report, skill, README, demo script |

Solo: follow phases in order; do lane C last. Use Antigravity's parallel agents only on independent modules (see `docs/antigravity-prompts.md`).

---

## 6. Task list with acceptance criteria

IDs are referenced from `docs/antigravity-prompts.md`.

| ID | Task | Acceptance |
|---|---|---|
| T-01 | Verify environment, model IDs, 4K-context pitfall | `scripts/smoke_backends.py` prints one JSON answer per backend |
| T-02 | `ingest.py`: render pages to PNG, store text layer + word boxes | 150-page PDF ingested < 60 s; word boxes normalized 0..1 |
| T-03 | `triage.py`: keyword/regex scoring into classes IGNORE / FINANCIAL_STATEMENT / FOOTNOTE / CHART / NON_GAAP_RECON | on 3 sample filings, statement pages recalled with 100% (precision may be lower) |
| T-04 | `backends.py`: `Backend` protocol; `OllamaBackend`, `GeminiBackend`; schema-constrained JSON; image inputs | same call works on both; invalid JSON raises `ExtractionError` |
| T-05 | `cache.py`: content-hash cache + `--replay` | second run makes 0 network/model calls; replay works offline |
| T-06 | `provenance.py`: resolve `verbatim` to bbox via text layer; fallback to model bbox; adapter for model-native box formats | unit tests with a generated PDF; bbox inside page; `bbox_source` set correctly |
| T-07 | `extract.py`: orchestrate page groups, build prompts, validate against `Financials`, run solver, retry with `Report.retry_prompt()` (max 3) | injected corruption in a stub backend is repaired within 3 tries; ends with exit code 3 if not |
| T-08 | `charts.py`: chart extraction prompt to `ChartExtraction`; CV bar-height measurement; call `audit_bar_chart` | on synthetic set: flags truncated charts, passes faithful ones |
| T-09 | `bench/synth_charts.py`: matplotlib generator with ground-truth JSON | produces N charts with known axis_min and LF |
| T-10 | `bench/run_bench.py`: extraction accuracy, identity pass rate, detector P/R, latency, backend comparison | writes `bench/results/summary.md` + JSON |
| T-11 | `recon.py`: extract non-GAAP reconciliation tables; footing via solver; bloat via forensics | footing violation reported with page |
| T-12 | `cli.py` (Typer): `ingest, extract, charts, analyze, dcf, report, run, bench` with exit codes from `docs/architecture.md` | `finsight --help` lists all; `run` works end to end |
| T-13 | `report.py`: Jinja2 to self-contained HTML (base64 crops), flags box, DuPont table, DCF histogram | opens offline; each number has page + crop |
| T-14 | Skill packaging: validate with `skills-ref`; symlink in `.agents/skills`; test loading in Antigravity | validator passes; agent can follow SKILL.md on a sample PDF |
| T-15 | README, `docs/WRITEUP.md` (DEV post), demo video | claims match bench results |
| T-16 (T3) | MCP server exposing the same commands | one tool call returns `forensics.json` |

---

## 7. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Small model misreads dense tables/charts | high | cascade: big model for extraction; abstain on null; report accuracy honestly; crop to table region |
| Ollama context too small, silent truncation | high | explicit `num_ctx`; assert prompt tokens < limit |
| Model IDs differ from what we assumed | medium | config-driven, verify in P0 |
| Gemini API rate limit/outage on demo day | medium | replay cache + backup video |
| VRAM too small for 26B/31B locally | medium | `e4b` local as the privacy story, cloud for accuracy; report both |
| Scope creep | high | tiers + freeze rule + cut list |
| Scanned PDFs without text layer | medium | model bbox fallback flagged `bbox_source="model"`; demo uses digital PDFs |
| Prompt injection inside PDFs | low-medium | AGENTS.md rule 5; schema-only outputs; no tool calls from content |
| Accusing a company of manipulation | reputational | wording: "flags/indicators", disclaimers, show evidence only |

---

## 8. Progress log

Append one line per finished task: `YYYY-MM-DD HH:MM T-xx short note`.

- 2026-10-17 seed: schemas, solver, lie_factor, forensics, dcf + 29 passing tests; SKILL.md validated for frontmatter limits.
- 2026-10-17 18:06 T-02 ingest: PDF → page PNGs + text layer with normalized word bboxes, 12 tests green.
- 2026-10-17 18:15 T-03 triage: deterministic regex/keyword page scoring + unit detection, 9 tests green.
