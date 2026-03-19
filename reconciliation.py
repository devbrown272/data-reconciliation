import pandas as pd
import numpy as np
import os
import logging
from datetime import datetime

# ── Setup ──────────────────────────────────────────────────────────────────────
os.makedirs('output', exist_ok=True)

logging.basicConfig(
    filename='reconciliation_log.txt',
    level=logging.INFO,
    format='%(asctime)s — %(levelname)s — %(message)s'
)

# ── Configuration ──────────────────────────────────────────────────────────────
VARIANCE_THRESHOLD_PCT = 2.0   # Flag any store where sources differ by more than 2%
REPORT_PERIOD          = 'FW2024-Q3'
NUM_STORES             = 12
SEED                   = 42


# ── Step 1: Generate Source A — Transaction-level extract ──────────────────────
def generate_source_a(num_stores, seed):
    """
    Source A simulates a transaction-level POS extract.
    This is the raw data — every sale recorded individually.
    Net sales = gross sales minus returned transaction amounts.
    """
    np.random.seed(seed)

    stores = [f'Store_{str(i).zfill(2)}' for i in range(1, num_stores + 1)]
    regions = ['North', 'South', 'East', 'West']
    store_region = {s: np.random.choice(regions) for s in stores}

    records = []
    for store in stores:
        n_transactions = np.random.randint(180, 420)
        for _ in range(n_transactions):
            gross   = round(np.random.uniform(40, 650), 2)
            returned = np.random.choice([0, 0, 0, 0, 1], p=[0.7, 0.1, 0.1, 0.05, 0.05])
            records.append({
                'store_id':   store,
                'region':     store_region[store],
                'gross_sale': gross,
                'returned':   returned
            })

    df = pd.DataFrame(records)
    df['net_sale'] = df.apply(
        lambda r: 0 if r['returned'] == 1 else r['gross_sale'], axis=1
    )

    source_a = df.groupby(['store_id', 'region']).agg(
        transactions      = ('gross_sale', 'count'),
        gross_sales       = ('gross_sale', 'sum'),
        returns           = ('returned',   'sum'),
        net_sales_source_a = ('net_sale',  'sum')
    ).reset_index().round(2)

    logging.info(f"Source A generated — {len(df):,} transactions across {num_stores} stores")
    print(f"  [source_a] {len(df):,} transactions generated across {num_stores} stores")
    return source_a


# ── Step 2: Generate Source B — Summary reporting system ──────────────────────
def generate_source_b(source_a, seed):
    """
    Source B simulates a summary report from a second system (e.g. SAP or a
    corporate dashboard). It reports net sales differently — returns are
    excluded from the transaction count but the sales amount uses a different
    return handling method, causing a systematic variance vs. Source A.

    This mirrors a real reconciliation problem: two systems using different
    business logic to define the 'same' metric.
    """
    np.random.seed(seed + 1)

    source_b = source_a[['store_id', 'region']].copy()

    # Source B uses a flat return deduction (average return value) rather than
    # actual transaction-level returns — common in summary reporting systems
    avg_return_value = 180.00
    source_b['net_sales_source_b'] = source_a.apply(
        lambda r: round(
            r['gross_sales'] - (r['returns'] * avg_return_value)
            + np.random.uniform(-50, 50),   # small system rounding noise
            2
        ), axis=1
    )

    # Introduce one missing store to simulate a data feed failure
    drop_idx = source_b.sample(1, random_state=seed).index
    source_b = source_b.drop(drop_idx).reset_index(drop=True)

    logging.info(f"Source B generated — {len(source_b)} stores (1 missing due to feed issue)")
    print(f"  [source_b] {len(source_b)} stores in summary system (1 missing)")
    return source_b


# ── Step 3: Reconcile ──────────────────────────────────────────────────────────
def reconcile(source_a, source_b, threshold):
    """
    Outer join both sources on store_id.
    Calculate variance and flag any store outside the threshold.
    Categorize the root cause of each discrepancy.
    """
    recon = pd.merge(source_a, source_b, on=['store_id', 'region'], how='outer')

    recon['variance_$']   = (recon['net_sales_source_b'] - recon['net_sales_source_a']).round(2)
    recon['variance_%']   = (
        recon['variance_$'] / recon['net_sales_source_a'] * 100
    ).round(1)

    def flag(row):
        if pd.isnull(row['net_sales_source_b']):
            return 'MISSING — not in Source B'
        if pd.isnull(row['net_sales_source_a']):
            return 'MISSING — not in Source A'
        if abs(row['variance_%']) > threshold:
            return 'REVIEW — variance exceeds threshold'
        return 'OK'

    def root_cause(row):
        if 'MISSING' in row['flag']:
            return 'Data feed failure — store absent from one system'
        if row['flag'] == 'REVIEW — variance exceeds threshold':
            return 'Return handling method differs between systems'
        return 'Within acceptable tolerance'

    recon['flag']       = recon.apply(flag, axis=1)
    recon['root_cause'] = recon.apply(root_cause, axis=1)

    flagged = recon[recon['flag'] != 'OK']
    logging.info(f"Reconciliation complete — {len(flagged)} stores flagged out of {len(recon)}")
    print(f"  [reconcile] {len(recon)} stores compared — {len(flagged)} flagged for review")
    return recon


# ── Step 4: Build findings summary ────────────────────────────────────────────
def build_findings(recon, threshold):
    """
    Produce a plain-English findings summary — the kind of output you'd
    actually deliver to a HelpDesk escalation or field leader inquiry.
    """
    total        = len(recon)
    ok           = len(recon[recon['flag'] == 'OK'])
    missing      = len(recon[recon['flag'].str.contains('MISSING')])
    review       = len(recon[recon['flag'] == 'REVIEW — variance exceeds threshold'])
    total_var    = recon['variance_$'].abs().sum().round(2)
    max_var_store = recon.loc[recon['variance_%'].abs().idxmax(), 'store_id'] \
                    if not recon['variance_%'].isna().all() else 'N/A'

    findings = f"""
RECONCILIATION FINDINGS — {REPORT_PERIOD}
{'='*55}
Run date:        {datetime.now().strftime('%Y-%m-%d %H:%M')}
Variance threshold: {threshold}%

SUMMARY
-------
Total stores compared:     {total}
Stores within tolerance:   {ok}
Stores flagged for review: {review}
Stores missing from feed:  {missing}
Total absolute variance:   ${total_var:,.2f}
Highest variance store:    {max_var_store}

ROOT CAUSES IDENTIFIED
----------------------
1. RETURN HANDLING MISMATCH (affects {review} stores)
   Source A uses actual transaction-level return amounts.
   Source B uses a flat average return deduction of $180.00.
   This causes a systematic variance in stores with high return
   rates or large-value returns.

   Recommendation: Standardize return treatment across both systems,
   or document the difference clearly so field users understand
   why the two reports will never match exactly.

2. MISSING DATA FEED ({missing} store(s))
   One store is absent from Source B entirely, indicating a data
   feed failure between the POS system and the reporting platform.

   Recommendation: Investigate the ETL pipeline for the affected
   store. Add a row-count validation to the feed process so missing
   stores are caught automatically before reports are distributed.

NEXT STEPS
----------
- Share findings with the BA team for Source B logic review
- Escalate feed failure to data engineering
- Add automated variance alerting for future periods
"""
    print(findings)
    logging.info("Findings summary generated")
    return findings


# ── Step 5: Export ─────────────────────────────────────────────────────────────
def export(recon, findings, output_path, findings_path):
    """
    Export the reconciliation detail to Excel and the findings to a text file.
    Both are ready to attach to a HelpDesk ticket or share with stakeholders.
    """
    cols = [
        'store_id', 'region', 'transactions', 'gross_sales', 'returns',
        'net_sales_source_a', 'net_sales_source_b',
        'variance_$', 'variance_%', 'flag', 'root_cause'
    ]
    recon_out = recon[[c for c in cols if c in recon.columns]]

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        recon_out.to_excel(writer, sheet_name='Reconciliation Detail', index=False)

        summary = recon.groupby('flag').size().reset_index()
        summary.columns = ['Status', 'Store Count']
        summary.to_excel(writer, sheet_name='Flag Summary', index=False)

    with open(findings_path, 'w') as f:
        f.write(findings)

    logging.info(f"Report exported to {output_path}")
    logging.info(f"Findings exported to {findings_path}")
    print(f"  [export]   Reconciliation report → {output_path}")
    print(f"  [export]   Findings summary      → {findings_path}")


# ── Main Runner ────────────────────────────────────────────────────────────────
def run():
    print(f"\n── Data Reconciliation Pipeline — {REPORT_PERIOD} ──")
    logging.info(f"═══ Reconciliation run started — {REPORT_PERIOD} ═══")
    start = datetime.now()

    try:
        source_a = generate_source_a(NUM_STORES, SEED)
        source_b = generate_source_b(source_a, SEED)
        recon    = reconcile(source_a, source_b, VARIANCE_THRESHOLD_PCT)
        findings = build_findings(recon, VARIANCE_THRESHOLD_PCT)

        ts            = start.strftime('%Y%m%d_%H%M')
        output_path   = f'output/reconciliation_report_{ts}.xlsx'
        findings_path = f'output/findings_{ts}.txt'
        export(recon, findings, output_path, findings_path)

        elapsed = round((datetime.now() - start).total_seconds(), 2)
        logging.info(f"═══ Complete in {elapsed}s ═══")
        print(f"\n── Complete in {elapsed}s ────────────────────────────\n")

    except Exception as e:
        logging.error(f"Reconciliation failed: {e}")
        print(f"\n  [ERROR] {e}\n")
        raise


if __name__ == '__main__':
    run()