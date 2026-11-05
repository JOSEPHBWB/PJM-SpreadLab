"""Fetch ten non-overlapping preliminary load areas for an RTO aggregate label."""
import getpass,json,os,time,urllib.request,urllib.parse
from pathlib import Path
root=Path(__file__).resolve().parent/'data'/'forecast';root.mkdir(parents=True,exist_ok=True)
key=os.environ.get('PJM_API_KEY') or getpass.getpass('PJM API key: ')
expected={'AEP','AP','ATSI','DAY','DEOK','DOM','DUQ','EKPC','MIDATL','NI'}
for year in range(2022,2026):
 for half,start,end in [(1,f'01/01/{year} 00:00',f'06/30/{year} 23:59'),(2,f'07/01/{year} 00:00',f'12/31/{year} 23:59')]:
  dest=root/f'actual_load_{year}_h{half}.json'
  if dest.exists():continue
  params={'datetime_beginning_ept':start+'to'+end,'fields':'datetime_beginning_utc,load_area,prelim_load_avg_hourly','rowCount':50000,'startRow':1}
  req=urllib.request.Request('https://api.pjm.com/api/v1/hrl_load_prelim?'+urllib.parse.urlencode(params),headers={'Ocp-Apim-Subscription-Key':key})
  with urllib.request.urlopen(req,timeout=120) as response:x=json.load(response)
  assert len(x['items'])==x['totalRows'],'pagination required'
  assert len(x['items'])>40000 and set(r['load_area'] for r in x['items'])==expected
  dest.write_text(json.dumps(x));print(year,half,len(x['items']),flush=True);time.sleep(12)
