# PJM SpreadLab

Research milestone closed on 2026-10-30. Read CLOSEOUT.md for final conclusions and accurate resume wording.

West Hub DA/RT spread research: historical cost reconstruction, tail risk and incremental signal value.

Start with outputs/PJM_2026_Frozen_Evaluation.html for the frozen v2 follow-on test. See outputs/PJM_Load_Signals.html for the load-signal pilot, or outputs/PJM_Cost_Risk_Signals.html (self-contained Chinese report with charts) or outputs/REPORT_zh.md. Full results and a per-hour ledger are in outputs/.

## Reproduce

Python 3, with numpy, pandas, scipy and matplotlib:

    python fetch_baseline.py
    python fetch_costs.py
    python analyze.py
    python research.py
    python validate_research.py
    python fetch_forecasts.py
    python fetch_actual_load.py
    python signals.py
    python validate_signals.py

Fetch scripts use PJM_API_KEY or prompt for a key. No credential is bundled. Existing cached files are reused; remove a cache explicitly to refresh. research_config.json records the fixed research rules. METHODS.md is handwritten and is not overwritten by report generation.

INC = DA - RT. DEC = RT - DA. Positions are signed INC MW; negative means DEC. One hour of 1 MW equals 1 MWh. Main P&L is a partial cost-adjusted scenario, not demonstrated executable final net profit. See methodology for regional fee stress, preliminary uplift, per-segment fees, invoice assumptions and historical-vintage limitations.

The sample has already been inspected; chronological evaluation is retrospective. No untouched holdout or full point-in-time backtest is claimed. The first milestone uses calendar signals. The next pilot adds timestamped load forecasts, revisions and an expected-error mechanism test; wind/solar history is unavailable from the 30-day-retention forecast endpoints.

Private research bundle includes PJM raw data. data/ and outputs/ are excluded by .gitignore; do not upload the private bundle to a public repository. The original BASELINE.md is retained as the first milestone, not the final analysis.

## Frozen 2026 evaluation

signal_v2_config.json, signal_v2_freeze.json and signal_v2_code_freeze.json record the pre-download freeze. check_2026_availability.py inspects counts/timestamps only; fetch_2026_once.py downloads the common complete period. signal_v2.py performs one evaluation and refuses to rerun if results already exist. The README does not instruct rerunning the one-shot evaluation. Audit existing outputs with validate_v2.py instead. 2026 DA outcomes had been used in other work, so this is not described as a completely untouched blind test.
