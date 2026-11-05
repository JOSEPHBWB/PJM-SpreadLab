"""Verify version selection, temporal outcome isolation and accounting."""
import json
import numpy as np
import pandas as pd
import research as R
import signals as S

prices=R.attach_costs(R.load_data())
d,qa=S.build_features(prices)
assert qa['raw_forecast_rows']>200000
available=d[d.available]
assert (available.assumed_available<=available.decision).all()
assert (available.issue<available.utc).all()
assert np.isfinite(available[S.CAL+S.LOAD]).all().all()
assert all('actual' not in x and 'error' not in x for x in S.CAL+S.LOAD)
# Prove that changing evaluation outcomes cannot change predictions or costs used for decisions.
small=d[d.local<pd.Timestamp('2023-02-01')].copy()
first,audit=S.backtest(small)
changed=small.copy();test=changed.year==2023
for col in ['spread','actual_gw','error_gw','inc_unit_east','dec_unit_east','admin_segment']:
    changed.loc[test,col]+=1_000_000
second,_=S.backtest(changed)
cols=['pred_calendar','pred_ridge','pred_load','pred_error','pred_error_spread','ci','cd']
a=first.loc[test,cols].to_numpy();b=second.loc[test,cols].to_numpy()
assert np.allclose(a,b,equal_nan=True)

results=json.loads((R.OUT/'signal_results.json').read_text())
ledger=json.loads((R.OUT/'signal_hourly_ledger.json').read_text())
assert len(ledger)==sum(v['covered'] for y,v in qa['coverage_by_year'].items() if int(y)>=2023)
for row in ledger:
    assert pd.Timestamp(row['assumed_available_utc'])<=pd.Timestamp(row['decision_utc'])
for name,v in results['strategies'].items():
    rows=[row['strategies'][name] for row in ledger]
    assert np.isclose(sum(x['net'] for x in rows),v['net'])
    assert np.isclose(sum(abs(x['q']) for x in rows),v['mwh'])
    assert all(np.isclose(x['net'],x['gross']-x['cost']) for x in rows)
    assert np.isclose(sum(m['net'] for m in results['annual'][name].values()),v['net'])
print('PASS: issue-before-cutoff; finite pre-decision features; target-outcome and fee isolation; historical refit cutoffs; hourly and annual accounting.')
