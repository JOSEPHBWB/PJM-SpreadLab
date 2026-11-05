"""Cache issue-timestamped RTO load forecasts; avoid short-retention wind/solar substitution."""
import getpass,json,os,time,urllib.request,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parent
KEY=os.environ.get('PJM_API_KEY') or getpass.getpass('PJM API key: ')
folder=ROOT/'data'/'forecast';folder.mkdir(parents=True,exist_ok=True)
for year in range(2022,2026):
 for half,start,end in [(1,f'01/01/{year} 00:00',f'06/30/{year} 23:59'),(2,f'07/01/{year} 00:00',f'12/31/{year} 23:59')]:
  dest=folder/f'load_forecast_{year}_h{half}.json'
  if dest.exists():continue
  params={'forecast_area':'RTO','forecast_hour_beginning_ept':start+'to'+end,'fields':'evaluated_at_utc,forecast_hour_beginning_utc,forecast_area,forecast_load_mw','rowCount':50000,'startRow':1}
  req=urllib.request.Request('https://api.pjm.com/api/v1/load_frcstd_hist?'+urllib.parse.urlencode(params),headers={'Ocp-Apim-Subscription-Key':KEY})
  with urllib.request.urlopen(req,timeout=120) as response:body=json.load(response)
  assert len(body['items'])==body['totalRows'],'Pagination required; refusing partial save'
  assert all(r['forecast_area']=='RTO' for r in body['items'])
  dest.write_text(json.dumps(body));print(year,half,len(body['items']),flush=True)
  time.sleep(12)
print('Forecast history complete',flush=True)
