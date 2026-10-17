# Demo Assets and Public Filings

The filings in `demo/filings/` are public regulatory disclosures downloaded from SEC EDGAR and Indian BSE/NSE filings for research, auditing, and benchmark validation. (Files in `demo/filings/*.pdf` are gitignored to comply with repository size and distribution guidelines).

## Test Suite Categories

| Category | Filing | Year | Standard | Primary Audit Test Focus |
|---|---|---|---|---|
| **Category A: Clean Large-Cap Benchmark** | Apple Inc. (`A1_Apple_2024.pdf`) | 2024 | US GAAP | Baseline balance sheet conservation, clean cash conversion, standard footnotes |
| | Microsoft Corp (`A2_Microsoft_2024.pdf`) | 2024 | US GAAP | Multi-segment revenue reconciliation, high return on equity (DuPont 5-factor) |
| | Infosys Ltd (`A3_Infosys_2024.pdf`) | 2024 | Ind AS | INR Crores unit scaling, standalone vs. consolidated statement triage |
| **Category B: Capital Intensive / Auto** | Tesla Inc. (`B4_Tesla_2024.pdf`) | 2024 | US GAAP | Automotive gross margin adjustments, capex reconciliation, regulatory credits |
| | Ola Electric (`B5_Ola_2025.pdf`) | 2025 | Ind AS | Emerging EV IPO filing, R&D capitalization vs expense |
| | General Electric (`B6_General-Electric_2018.pdf`) | 2018 | US GAAP | Legacy long-term service contracts, restatements |
| **Category C: Non-GAAP Bloat & Growth** | WeWork Inc. (`C7_WeWork_2024.pdf`) | 2024 | US GAAP | Community-adjusted EBITDA bloat ratio, extreme operating lease liabilities |
| | Uber Technologies (`C8_Uber_2019.pdf`) | 2019 | US GAAP | S-1 IPO filing, stock-based compensation addbacks, negative cash conversion |
| | Salesforce Inc. (`C9_Salesforce_2024.pdf`) | 2024 | US GAAP | Subscription ARR metrics, non-GAAP operating margin reconciliations |
| **Category D: Historic Accounting Scandals** | Enron Corp (`D10_Enron_2000.PDF`) | 2000 | US GAAP | Special Purpose Entities (SPEs), mark-to-market prepay energy contracts |
| | Satyam Computer Services (`D11_Satyam_2008.PDF`) | 2008 | Indian GAAP | Fictitious cash balances, accrued interest vs actual bank cash |
| | Wirecard AG (`D12_Wirecard_2018.pdf`) | 2018 | IFRS | Third-party trustee cash balances (escrow), Beneish M-Score anomalies |
| | WorldCom Inc. (`D13_Worldcom_2001.pdf`) | 2001 | US GAAP | Line cost capitalization into PP&E rather than operating expense |
| **Category E: Retail & Financial Services** | Amazon.com Inc. (`E14_Amazon_2023.pdf`) | 2023 | US GAAP | AWS vs retail operating margin, finance lease capex adjustments |
| | Walmart Inc. (`E15_Walmart_2024.pdf`) | 2024 | US GAAP | Inventory turnover, working capital efficiency |
| | Microsoft Corp (`E16_Microsoft_2023.pdf`) | 2023 | US GAAP | Prior-year comparative figures for Piotroski F-score and Beneish M-score |
| | Bajaj Finserv (`E17_Bajaj-Finserv_2025.pdf`) | 2025 | Ind AS | Non-banking financial company (NBFC) exclusion logic for industrial ratios |
| **Category F: Boom & Bust Tech** | Peloton Interactive (`F18_Peloton_2021.pdf`) | 2021 | US GAAP | Supply chain inventory build-up, sudden demand collapse, Altman Z'' downgrade |
| | Snap Inc. (`F19_Snap_2022.pdf`) | 2022 | US GAAP | Heavy dilution via stock-based compensation, GAAP vs non-GAAP EBITDA gap |
| **Category G: Retail Distress & Chapter 11** | Sears Holdings (`G20_Sears_2017.pdf`) | 2017 | US GAAP | Chronic negative working capital, deep Altman Z'' distress zone (<1.1) |
| | Bed Bath & Beyond (`G21_Bed-Bath-Beyon_2022.pdf`) | 2022 | US GAAP | Severely negative equity, vendor debt distress, Altman Z'' crash |

## Running Audits on Demo Filings

```bash
# Ingest and audit any filing:
finsight run demo/filings/A1_Apple_2024.pdf --workspace ./workspace/apple --backend auto

# Run in strict confidential mode (100% on-device Ollama gemma4:e4b):
finsight run demo/filings/A3_Infosys_2024.pdf --workspace ./workspace/infosys --backend local --confidential
```
