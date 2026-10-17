# Indian exchange filings (BSE/NSE) notes

- Accounting standard is usually **Ind-AS** (converged with IFRS). Set `meta.standard = "IND_AS"`.
- Units: **lakhs** (1e5) and **crores** (1e7) are both common, sometimes within one document. 1 crore = 100 lakhs. A 100x mismatch between two statements is the classic extraction error; the verifier reports it as a "lakhs vs crores" hint.
- Filings usually contain both **standalone** and **consolidated** statements. Extract consolidated by default and record `meta.basis`. Never mix bases across statements.
- Fiscal year ends 31 March. Label `period_end` accordingly (e.g. 2026-03-31 is FY26).
- Quarterly results are often filed as a single result sheet with Q4, Q3, prior-year Q4 and full-year columns. Pick the column that matches `period_type` and double-check the header.
- "Exceptional items" and "other comprehensive income" lines can break the retained-earnings roll-forward; treat that check as a warning.
- Investor decks often show "Adjusted EBITDA" or "PAT" in crores while the statutory table is in lakhs; always compare after normalizing with `SCALE_FACTORS`.
