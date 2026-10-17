# Forensic formulas and limitations

All screens are indicators. None applies cleanly to banks, insurers or NBFCs; skip them for financials.

## DuPont 5-factor (end-of-period balances)
ROE = (NI/EBT) x (EBT/EBIT) x (EBIT/Revenue) x (Revenue/Assets) x (Assets/Equity). The product must equal NI/Equity; the tool checks this.

## Altman Z'' (default; no market cap needed)
Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4
X1 = (current assets - current liabilities)/total assets; X2 = retained earnings/total assets; X3 = EBIT/total assets; X4 = book equity/total liabilities.
Zones: > 2.6 safe, 1.1 to 2.6 grey, < 1.1 distress.
Original Z (public manufacturers, needs market cap): 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4(market cap/total liabilities) + 1.0 X5(revenue/assets). Zones: > 2.99, 1.81 to 2.99, < 1.81.

## Beneish M-score (8 variables)
M = -4.84 + 0.920 DSRI + 0.528 GMI + 0.404 AQI + 0.892 SGI + 0.115 DEPI - 0.172 SGAI + 4.679 TATA - 0.327 LVGI.
Default flag threshold -1.78 (-2.22 is a more sensitive alternative). Needs current and prior-year values. This implementation omits marketable securities in AQI and uses net income as the proxy for income from continuing operations. A neutral flat company scores about -2.48.

## Piotroski F-score (simplified)
Nine binary signals: ROA > 0, CFO > 0, ROA improving, CFO > NI, leverage falling, current ratio improving, no dilution, gross margin improving, asset turnover improving. Uses end-of-period assets; signals lacking data are excluded from `evaluable`.

## Non-GAAP bloat
(non-GAAP - GAAP) / |GAAP|. Flag above 25%. Always verify the reconciliation table foots (GAAP + adjustments = non-GAAP) before trusting it.

## Tufte lie factor
LF = (relative change shown in the graphic) / (relative change in the data). Acceptable range 0.95 to 1.05. For bars drawn from a truncated axis minimum m, heights are proportional to (value - m), so LF is computed analytically from the printed values and the axis minimum.

## DCF
Free cash flow = NOPAT - (change in revenue / sales-to-capital). Growth and margin fade linearly to terminal values. Terminal value uses g and terminal ROIC (default = WACC). Output is a WACC x g matrix plus Monte Carlo percentiles. The distribution reflects assumption uncertainty only.
