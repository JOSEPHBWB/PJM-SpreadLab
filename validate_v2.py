"""Audit saved v2 results without refitting or reevaluating strategies."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'signal_v2_config.json').read_text());freeze=json.loads((ROOT/'signal_v2_freeze.json').read_text());code=json.loads((ROOT/'signal_v2_code_freeze.json').read_text())
assert hashlib.sha256((ROOT/'signal_v2_config.json').read_bytes()).hexdigest()==freeze['config_sha256']
assert hashlib.sha256((ROOT/'signal_v2.py').read_bytes()).hexdigest()==code['signal_v2_py_sha256']
for name,digest in code['dependencies'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
r=json.loads((ROOT/'outputs/signal_v2_results.json').read_text());rows=json.loads((ROOT/'outputs/signal_v2_hourly_ledger.json').read_text())
assert len(rows)==r['evaluation_hours']
audit={a['month']:a for a in r['training_audit']}
for a in audit.values():assert pd.Timestamp(a['last_train_target'])<pd.Timestamp(a['cutoff_exclusive'])
for row in rows:
 assert pd.Timestamp(row['assumed_available_utc'])<=pd.Timestamp(row['decision_utc'])
 month=pd.Timestamp(row['utc']).tz_convert('America/New_York').strftime('%Y-%m')
 expected=float(row['median_spread_prediction']>audit[month]['expected_inc_cost']+cfg['extra_entry_buffer_usd_mwh'])
 assert row['strategies']['Load absolute INC']['q']==expected
 for name in ['Load absolute INC','Calendar absolute INC','Load squared INC']:assert row['strategies'][name]['q'] in [0.,1.]
for name,v in r['strategies'].items():
 ls=[row['strategies'][name]for row in rows]
 assert np.isclose(sum(x['net']for x in ls),v['net'])
 assert np.isclose(sum(abs(x['q'])for x in ls),v['mwh'])
 assert all(np.isclose(x['net'],x['gross']-x['cost'])for x in ls)
 assert np.isclose(sum(m['net']for m in r['monthly'][name].values()),v['net'])
print('PASS: frozen config/code/dependency hashes; chronology; decision-time availability; primary threshold replay; INC-only constraints; hourly/monthly accounting. No models refitted.')
