# Accounting checks and what failures usually mean

| Code | Check | Severity | Typical cause |
|---|---|---|---|
| BALANCE_SHEET_IDENTITY | Assets = Liabilities + Equity (or = Total L&E when printed) | error | wrong column or year, non-controlling interest missing from equity, unit mix-up |
| BALANCE_SHEET_COMPONENTS | Liabilities + Equity = Total L&E | error | equity excludes NCI |
| COMPONENT_EXCEEDS_TOTAL | Current assets, PP&E, cash, receivables <= total assets | error | column misalignment, unit scale |
| CASH_BRIDGE | Opening cash + CFO + CFI + CFF + FX = closing cash | warning | restricted cash, assets held for sale |
| RETAINED_EARNINGS | RE_t = RE_(t-1) + NI - dividends | warning | buybacks, OCI reclasses |
| CROSS_STATEMENT_SCALE | abs(net income) <= 3 x revenue | warning | statements in different units |
| RECONCILIATION_FOOTING | GAAP + adjustments = non-GAAP | error | missing or mis-signed adjustment |
| SEGMENT_SUM | Segments + eliminations = consolidated | error | missing "other/corporate" row |

Many US 10-Ks do not print "Total liabilities"; the solver then uses "Total liabilities and equity" instead.
Sign convention: `capex` and `dividends_paid` are positive magnitudes; `cfo/cfi/cff/fx_effect` keep reported signs.
