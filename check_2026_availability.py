"""Inspect timestamps/counts only. No price/load values requested or exposed."""
import getpass,json,os,time,urllib.request,urllib.parse,calendar
from pathlib import Path
ROOT=Path(__file__).resolve().parent
key=os.environ.get('PJM_API_KEY') or getpass.getpass('PJM API key: ')
rates=json.loads((ROOT/'data/sched_9_10_rates.json').read_text())['items']
required={'9-3: Market Support - Component 1','9-3: Market Support - Component 2','9-MMU: Market Monitoring Unit (MMU) Funding - Component 1','9-MMU: Market Monitoring Unit (MMU) Funding - Component 2','9-PSI: PJM Settlement, Inc. - 9-3 Component 1','9-PSI: PJM Settlement, Inc. - 9-3 Component 2','9-PSI: PJM Settlement, Inc. - Per Invoice'}
months=sorted({r['schedule_month'][:7] for r in rates if r['row_is_current'] and r['schedule_month'].startswith('2026-')})
complete=[]
reserve=json.loads((ROOT/'data/prelim_or_rates.json').read_text())['items'];dates={r['operating_reserve_date'][:10] for r in reserve}
for month in months:
 names={r['schedule_name'] for r in rates if r['row_is_current'] and r['schedule_month'].startswith(month)}
 days=calendar.monthrange(2026,int(month[5:]))[1]
 if required<=names and all(f'{month}-{d:02d}' in dates for d in range(1,days+1)):complete.append(month)
assert complete
last=complete[-1];m=int(last[5:]);end=f'{m:02d}/{calendar.monthrange(2026,m)[1]:02d}/2026 23:59'
checks=[]
queries=[('rt_da_monthly_lmps',{'pnode_id':51288,'datetime_beginning_ept':'01/01/2026 00:00to'+end,'fields':'datetime_beginning_utc,pnode_id'}),('load_frcstd_hist',{'forecast_area':'RTO','forecast_hour_beginning_ept':f'{m:02d}/01/2026 00:00to'+end,'fields':'evaluated_at_utc,forecast_hour_beginning_utc,forecast_area'}),('hrl_load_prelim',{'datetime_beginning_ept':f'{m:02d}/01/2026 00:00to'+end,'fields':'datetime_beginning_utc,load_area'})]
for feed,params in queries:
 params.update({'rowCount':1,'startRow':1})
 req=urllib.request.Request('https://api.pjm.com/api/v1/'+feed+'?'+urllib.parse.urlencode(params),headers={'Ocp-Apim-Subscription-Key':key})
 with urllib.request.urlopen(req,timeout=120) as response:x=json.load(response)
 check={'feed':feed,'total_rows':x['totalRows'],'first_timestamps_only':x['items'][:1]}
 checks.append(check);print(check,flush=True);time.sleep(12)
manifest={'common_end_month':last,'end_ept':end,'admin_complete_months':complete,'checks':checks,'numeric_price_or_load_values_requested':False}
(ROOT/'data/availability_2026.json').write_text(json.dumps(manifest,indent=2))
print('Availability manifest ready:',last,flush=True)
