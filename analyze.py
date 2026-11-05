import json, math, statistics
from pathlib import Path
from datetime import datetime,timedelta
ROOT=Path(__file__).resolve().parent
allrows=[]
lines=['# PJM SpreadLab — first baseline','', 'Source: PJM rt_da_monthly_lmps, pnode_id=51288 (WESTERN HUB).', 'Prices are settlements-verified total LMP, including congestion and losses.', '', 'Assumption: 1 MW cleared every hour, price taker, gross energy settlement only. Fees, uplift, credit, bid rejection and execution effects are excluded. This is a historical exposure baseline, not demonstrated executable profit.', '', 'INC = DA - RT; DEC = RT - DA. Positive DA-RT mean is a descriptive historical premium, not proof of a causal risk premium.', '', '| Year | Hours | Mean DA-RT ($/MWh) | Gross INC ($) | Gross DEC ($) | INC max drawdown ($) | Worst INC hour ($) | Worst DEC hour ($) |', '|---|---:|---:|---:|---:|---:|---:|---:|']
def drawdown(xs):
    nav=peak=dd=0
    for x in xs:
        nav+=x;peak=max(peak,nav);dd=max(dd,peak-nav)
    return dd
for year in range(2022,2026):
    body=json.loads((ROOT/'data'/f'western_hub_{year}.json').read_text())
    rows=sorted(body['items'],key=lambda r:r['datetime_beginning_utc'])
    expected=8784 if year%4==0 else 8760
    assert len(rows)==expected,(year,len(rows),expected)
    times=[datetime.fromisoformat(r['datetime_beginning_utc']) for r in rows]
    assert len(set(times))==expected
    assert all(b-a==timedelta(hours=1) for a,b in zip(times,times[1:]))
    assert all(r['pnode_name']=='WESTERN HUB' and int(r['pnode_id'])==51288 for r in rows)
    for r in rows:
        for market in ['da','rt']:
            price=r[f'total_lmp_{market}']
            assert price is not None and math.isfinite(price)
            parts=sum(r[f'{part}_{market}'] for part in ['system_energy_price','congestion_price','marginal_loss_price'])
            assert abs(parts-price)<0.00002
        r['inc_gross']=r['total_lmp_da']-r['total_lmp_rt'];r['dec_gross']=-r['inc_gross']
    xs=[r['inc_gross'] for r in rows]
    lines.append(f'| {year} | {len(rows)} | {statistics.mean(xs):.3f} | {sum(xs):,.2f} | {-sum(xs):,.2f} | {drawdown(xs):,.2f} | {min(xs):,.2f} | {-max(xs):,.2f} |')
    allrows.extend(rows)
lines+=['', 'QA: expected 35,064 hourly records; UTC uniqueness and uninterrupted hourly continuity checked within each year; node identity, finite prices and price-component reconciliation checked. EPT timestamps are retained for local hour analysis, but UTC is the unique key to preserve repeated DST hours.', '', '## Next analysis', '', '1. Attribute gross returns and losses by local hour, month and year; inspect worst days and tail concentration.', '2. Freeze a chronological split before signal selection: use earlier years for development and later years for out-of-sample evaluation; do not treat the all-year baseline as independent confirmation.', '3. Build only features available before the relevant DA bidding deadline; settlement-verified prices are outcome labels and cannot automatically be used as timely lag features.', '4. Compare conditional trading with both unconditional directions and no trade, then add actual fees, uplift, credit and clearing constraints.', '', 'References:', '- https://dataminer2.pjm.com/feed/rt_da_monthly_lmps', '- https://www.pjm.com/markets-and-operations/etools/data-miner-2', '- https://www.pjm.com/Glossary.aspx?p=1', '']
(ROOT/'BASELINE.md').write_text('\n'.join(lines))
(ROOT/'data'/'western_hub_2022_2025.json').write_text(json.dumps(allrows))
print('\n'.join(lines[:15]))
