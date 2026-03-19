# Data Reconciliation Pipeline

A Python script that simulates and resolves the most common escalation a BA reporting team receives: two systems reporting different sales totals for the same stores and period.

Built to demonstrate the diagnostic pattern used in financial reporting environments — trace the discrepancy from output back to source, identify the root cause, and deliver a clear findings summary.

---

## The scenario

Two data sources report net sales for 12 stores in fiscal week period FW2024-Q3:

- **Source A** — a transaction-level POS extract. Net sales = gross sales minus actual returned transaction amounts, calculated at the individual transaction level.
- **Source B** — a summary report from a corporate reporting system. Net sales uses a flat average return deduction ($180.00 per return) rather than actual return values.

The two sources will never match exactly — but the question is: which stores are outside acceptable tolerance, and why?

---

## What it does

1. **Generates Source A** — 3,000+ synthetic transactions across 12 stores with realistic gross sales and return patterns
2. **Generates Source B** — a summary report using different return logic, plus one store missing due to a simulated feed failure
3. **Reconciles** — outer joins both sources, calculates variance $ and % for every store, flags any store outside the 2% threshold
4. **Diagnoses** — categorizes each discrepancy by root cause: return handling mismatch vs. missing data feed
5. **Exports** — a detailed Excel reconciliation report and a plain-English findings summary ready to deliver to a stakeholder

---

## Output

Running the script produces two files in the `output/` folder:

| File | Contents |
|---|---|
| `reconciliation_report_[timestamp].xlsx` | Two sheets: full store-level detail with variance flags, and a flag summary by status |
| `findings_[timestamp].txt` | Plain-English findings summary with root causes, recommendations, and next steps |

Sample terminal output:
```
── Data Reconciliation Pipeline — FW2024-Q3 ──
  [source_a] 3,171 transactions generated across 12 stores
  [source_b] 11 stores in summary system (1 missing)
  [reconcile] 12 stores compared — 5 flagged for review

RECONCILIATION FINDINGS — FW2024-Q3
=====================================================
Total stores compared:     12
Stores within tolerance:   7
Stores flagged for review: 4
Stores missing from feed:  1
Total absolute variance:   $18,189.56
Highest variance store:    Store_03

── Complete in 0.41s ────────────────────────────
```

---

## How to run

```bash
pip install -r requirements.txt
python reconciliation.py
```

---

## Project structure

```
03-reconciliation/
├── reconciliation.py        # Main script
├── requirements.txt         # Dependencies
├── reconciliation_log.txt   # Auto-generated run log
├── output/                  # Auto-generated reports
└── README.md
```

---

## Configuration

At the top of `reconciliation.py`, four parameters control the scenario:

| Parameter | Default | Description |
|---|---|---|
| `VARIANCE_THRESHOLD_PCT` | 2.0 | Flag threshold — stores outside this % are flagged for review |
| `REPORT_PERIOD` | FW2024-Q3 | Label for the reporting period |
| `NUM_STORES` | 12 | Number of stores in the dataset |
| `SEED` | 42 | Random seed for reproducibility |

Changing `VARIANCE_THRESHOLD_PCT` to 5.0 reduces flagged stores. Tightening it to 1.0 increases sensitivity. This mirrors how a real BA team would tune alert thresholds based on business tolerance.

---

## Root causes identified

**1. Return handling mismatch**
The most common source of inter-system variance in retail reporting. Source A calculates returns at the transaction level using actual return amounts. Source B applies a flat average deduction. Stores with high return rates or large individual returns show the largest variance.

Resolution: Standardize return logic across both systems, or document the difference so field users understand why the two reports differ by design.

**2. Missing data feed**
One store is absent from Source B entirely — its sales feed failed to reach the reporting system. Without a row-count validation on the feed, this would go undetected until a field leader escalated.

Resolution: Add automated row-count and store-count validation to the ETL process. Any period where the expected number of stores is not present should trigger an alert before the report is distributed.

---

## Design decisions

**Outer join instead of inner join** — using an inner join would silently drop the missing store and undercount the total variance. An outer join surfaces every discrepancy including missing records, which is what a real reconciliation requires.

**Configurable threshold** — hardcoding 2% into the logic would make the script brittle. Exposing it as a named constant at the top of the file means the threshold can be adjusted per business need without touching the core logic.

**Plain-English findings output** — the Excel report is for the BA team. The findings text file is for the field leader or HelpDesk ticket. Two different audiences need two different formats from the same analysis.

**Logging every run** — `reconciliation_log.txt` captures a full audit trail. In a production environment where this runs on a schedule, the log is the only record of what the data looked like at the time of each run.

---

## What I would add next

- **Email delivery** — automatically attach the findings and Excel report to a HelpDesk ticket or distribution list on completion
- **Threshold alerting** — if total absolute variance exceeds a dollar threshold (e.g. $50,000), trigger a priority escalation separate from the standard findings
- **Historical comparison** — track variance by store across multiple periods to identify stores that are systematically misaligned vs. one-time anomalies
- **Real data connection** — replace the synthetic data generators with actual SQL queries or API calls to the source systems

---

## About this project

This script models the diagnostic workflow a BA reporting team uses when field leaders escalate a "my numbers don't match" ticket. The pattern — join, compare, flag, diagnose, document — applies to any two-source reconciliation regardless of the underlying systems.

The same approach I used here is what I would apply to reconciling SAP BusinessObjects reports against Tableau extracts or POS data against corporate dashboards.