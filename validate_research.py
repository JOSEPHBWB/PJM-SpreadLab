"""Checks independent accounting identities, HAC calculation and temporal isolation."""
import json
import numpy as np
import pandas as pd
import research as r

# HAC of a mean equals Bartlett-weighted autocovariance using an explicit nested sum.
x=np.array([1.,-3.,4.,2.,-1.,5.,-2.])
lag=2;n=len(x);z=x-x.mean()
reference=(sum(z[i]*z[i] for i in range(n))+2*sum((1-k/(lag+1))*sum(z[i]*z[i-k] for i in range(k,n)) for k in range(1,lag+1)))/(n*n)
assert np.isclose(r.nw_mean(x,lag)['se']**2,reference)
assert r.mdd([-10.,5.,-20.,30.])==25.
assert r.es_loss([-100.,1.,2.,3.],.95)==100.

d=r.attach_costs(r.load_data())
p,a=r.predict(d)
# Future outcome and future fee perturbations cannot alter prior-period predictions/positions.
changed=d.copy()
future=changed.year==2025
changed.loc[future,'spread']+=1_000_000
for col in ['inc_unit_east','dec_unit_east','admin_segment']:
    changed.loc[future,col]+=1_000_000
p2,_=r.predict(changed)
cols=['pred_spread','pred_cost_inc','pred_cost_dec','tail_inc','tail_dec']
assert np.allclose(p.loc[p.year==2023,cols],p2.loc[p2.year==2023,cols])
q1=r.positions(p[p.year==2023]);q2=r.positions(p2[p2.year==2023])
assert all(np.array_equal(q1[k],q2[k]) for k in q1)
assert all(pd.Timestamp(v['train_max_local'])<pd.Timestamp(v['cutoff_exclusive']) for v in a)

# Manual cashflows: segment fee paid once per nonzero submitted segment, even at 0.1 MW.
toy=d.iloc[:3].copy().reset_index(drop=True)
q=np.array([1.,-1.,.1])
net,gross,cost=r.pnl(toy,q,extra=.5)
for i in range(3):
    unit=toy.iloc[i]['inc_unit_east' if q[i]>=0 else 'dec_unit_east']
    expected=abs(q[i])*(unit+.5)+toy.admin_segment.iloc[i]
    assert np.isclose(cost[i],expected)
assert np.allclose(net,gross-cost)
assert np.allclose(r.pnl(toy,np.zeros(3),invoices=5)[0],0)
assert np.isclose(r.pnl(toy,q,invoices=5)[2].sum()-r.pnl(toy,q)[2].sum(),5*toy.invoice_rate.iloc[0])

# Saved ledger reconciliation and non-anticipative refit dates.
result=json.loads((r.OUT/'results.json').read_text())
ledger=json.loads((r.OUT/'hourly_ledger.json').read_text())
for name,v in result['strategies'].items():
    rows=[row['strategies'][name] for row in ledger]
    assert np.isclose(sum(x['net'] for x in rows),v['net'])
    assert np.isclose(sum(abs(x['q']) for x in rows),v['mwh'])
    assert all(abs(x['net']-(x['gross']-x['cost']))<1e-8 for x in rows)
    assert max(abs(x['q']) for x in rows)<=1.
    assert np.isclose(sum(w['net'] for w in result['annual'][name].values()),v['net'])
print('PASS: HAC reference; risk metrics; future outcome/fee isolation; 36 refit cutoffs; fee scaling; invoice costs; hourly and annual reconciliation.')
