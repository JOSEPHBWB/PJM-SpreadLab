"""Download the fixed common period after rule/code freeze; resume cache only on transfer failure."""
import calendar,getpass,hashlib,json,os,time,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
freeze=json.loads((ROOT/'signal_v2_freeze.json').read_text());assert freeze['config_sha256']==hashlib.sha256((ROOT/'signal_v2_config.json').read_bytes()).hexdigest()
code=json.loads((ROOT/'signal_v2_code_freeze.json').read_text());assert code['signal_v2_py_sha256']==hashlib.sha256((ROOT/'signal_v2.py').read_bytes()).hexdigest()
assert not (ROOT/'outputs/signal_v2_results.json').exists(),'Evaluation already completed'
manifest=json.loads((ROOT/'data/availability_2026.json').read_text());m=int(manifest['common_end_month'][5:]);last=calendar.monthrange(2026,m)[1];end=f'{m:02d}/{last:02d}/2026 23:59'
key=os.environ.get('PJM_API_KEY') or getpass.getpass('PJM API key: ')
queries=[('rt_da_monthly_lmps',{'pnode_id':51288,'datetime_beginning_ept':'01/01/2026 00:00to'+end},ROOT/'data/western_hub_2026.json')]
for half,start,stop in [(1,'01/01/2026 00:00','06/30/2026 23:59'),(2,'07/01/2026 00:00',end)]:
 queries.append(('load_frcstd_hist',{'forecast_area':'RTO','forecast_hour_beginning_ept':start+'to'+stop,'fields':'evaluated_at_utc,forecast_hour_beginning_utc,forecast_area,forecast_load_mw'},ROOT/'data/forecast'/f'load_forecast_2026_h{half}.json'))
 queries.append(('hrl_load_prelim',{'datetime_beginning_ept':start+'to'+stop,'fields':'datetime_beginning_utc,load_area,prelim_load_avg_hourly'},ROOT/'data/forecast'/f'actual_load_2026_h{half}.json'))
for feed,params,dest in queries:
 if dest.exists():print(dest.name,'cached',flush=True);continue
 params.update({'rowCount':50000,'startRow':1})
 req=urllib.request.Request('https://api.pjm.com/api/v1/'+feed+'?'+urllib.parse.urlencode(params),headers={'Ocp-Apim-Subscription-Key':key})
 with urllib.request.urlopen(req,timeout=120)as response:body=json.load(response)
 assert len(body['items'])==body['totalRows'] and body['totalRows']>0,'Incomplete response; refuse save'
 dest.write_text(json.dumps(body));print(dest.name,'records',len(body['items']),flush=True);time.sleep(12)
print('Fixed-period download complete; no outcome summary generated.',flush=True)
