# PJM SpreadLab — first baseline

Source: PJM rt_da_monthly_lmps, pnode_id=51288 (WESTERN HUB).
Prices are settlements-verified total LMP, including congestion and losses.

Assumption: 1 MW cleared every hour, price taker, gross energy settlement only. Fees, uplift, credit, bid rejection and execution effects are excluded. This is a historical exposure baseline, not demonstrated executable profit.

INC = DA - RT; DEC = RT - DA. Positive DA-RT mean is a descriptive historical premium, not proof of a causal risk premium.

| Year | Hours | Mean DA-RT ($/MWh) | Gross INC ($) | Gross DEC ($) | INC max drawdown ($) | Worst INC hour ($) | Worst DEC hour ($) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 8760 | -1.162 | -10,179.06 | 10,179.06 | 38,784.45 | -3,588.51 | -366.85 |
| 2023 | 8760 | 1.289 | 11,287.47 | -11,287.47 | 2,352.35 | -577.92 | -278.18 |
| 2024 | 8784 | 0.587 | 5,156.48 | -5,156.48 | 6,668.94 | -413.13 | -236.84 |
| 2025 | 8760 | 0.975 | 8,540.33 | -8,540.33 | 8,508.85 | -1,477.43 | -318.52 |

QA: expected 35,064 hourly records; UTC uniqueness and uninterrupted hourly continuity checked within each year; node identity, finite prices and price-component reconciliation checked. EPT timestamps are retained for local hour analysis, but UTC is the unique key to preserve repeated DST hours.

## Next analysis

1. Attribute gross returns and losses by local hour, month and year; inspect worst days and tail concentration.
2. Freeze a chronological split before signal selection: use earlier years for development and later years for out-of-sample evaluation; do not treat the all-year baseline as independent confirmation.
3. Build only features available before the relevant DA bidding deadline; settlement-verified prices are outcome labels and cannot automatically be used as timely lag features.
4. Compare conditional trading with both unconditional directions and no trade, then add actual fees, uplift, credit and clearing constraints.

References:
- https://dataminer2.pjm.com/feed/rt_da_monthly_lmps
- https://www.pjm.com/markets-and-operations/etools/data-miner-2
- https://www.pjm.com/Glossary.aspx?p=1
