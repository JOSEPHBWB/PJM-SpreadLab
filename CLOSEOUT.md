# PJM SpreadLab — research closeout

Status: closed research milestone, 2026-10-30. The retained conclusion is that the tested calendar and timestamped load-forecast signals did not establish a robust trading edge after modeled costs. All unsuccessful controls and original outcome tails are retained.

## Final cost and premium wording

For unconditional INC, the full 2023–2025 historical baseline averaged $0.503/MWh in modeled costs and $0.950/MWh in gross DA–RT spread. The 2026 January–September common forecast-covered sample averaged $2.306/MWh in modeled costs and $0.450/MWh in gross spread. These periods and sample scopes differ; the comparison is descriptive, not a matched-sample causal estimate.

Do not describe $0.50/MWh as the 2023-only cost: the 2023 figure is $0.276/MWh. The broad increase is mainly from operating-reserve charges rather than administrative fees. These are reconstructed costs using public historical rates and stated assumptions, not exact final participant invoices.

## Frozen follow-on result

The v2 policy and implementation were hashed before this project downloaded numeric 2026 spread outcomes. The common complete source period was January–September 2026, with 6,528 forecast-covered evaluation hours. Monthly expanding fits followed a 90-day label embargo. Primary absolute-loss INC/no-trade returned -$11,085 after modeled costs; unconditional INC returned -$12,119; equal-total-volume INC outperformed the primary by $89, with the paired interval spanning zero. The squared-loss INC control returned -$3,823. This does not establish an edge or superiority of robust loss.

Use “a 2026 follow-on evaluation with rules fixed in advance.” Do not say “pre-registered” without formal registration. Do not describe the market period as completely untouched: 2026 DA prices had been used in other work. Full publication-time, cost, execution and inference qualifications remain in METHODS.md.

## Resume wording

Built a cost-aware PJM Western Hub INC/DEC backtest using timestamped load forecasts and reconstructed admin/uplift charges; quantified modeled costs rising from ~$0.50/MWh (2023–25) to ~$2.31/MWh (Jan–Sep 2026), and found no robust net edge from tested signals, including a 2026 evaluation with rules fixed in advance.

## Final artifacts

- outputs/PJM_2026_Frozen_Evaluation.html: final frozen-policy results and assessment.
- outputs/PJM_Load_Signals.html: load-signal pilot and post-hoc direction/load-quintile diagnostics.
- outputs/PJM_Cost_Risk_Signals.html: cost and tail-risk baseline.
- METHODS.md: assumptions and limitations.
- signal_v2_config.json, signal_v2_freeze.json, signal_v2_code_freeze.json: fixed protocol and hashes.
- outputs/signal_v2_results.json, outputs/signal_v2_hourly_ledger.json: numerical outcomes and audit trail.

Any future strategy change should be a new research version assessed on later data under a newly fixed protocol. This completed study should retain its negative results.
