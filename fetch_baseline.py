import os, json, csv, urllib.request, urllib.parse, urllib.error, time
from pathlib import Path
from datetime import datetime, timedelta
ROOT=Path(__file__).resolve().parent
KEY=os.environ.get('PJM_API_KEY') or input('PJM API key: ').strip()
for year in range(2022,2026):
    dest=ROOT/'data'/f'western_hub_{year}.json'
    if dest.exists(): continue
    params={'startRow':1,'rowCount':50000,'pnode_id':51288,'datetime_beginning_ept':f'01/01/{year} 00:00to12/31/{year} 23:59'}
    url='https://api.pjm.com/api/v1/rt_da_monthly_lmps?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'Ocp-Apim-Subscription-Key':KEY})
    try:
        with urllib.request.urlopen(req,timeout=90) as response: body=json.load(response)
    except urllib.error.HTTPError as exc:
        print(year,'HTTP',exc.code,exc.read(1000).decode(),flush=True); raise SystemExit(1)
    rows=body.get('items',[])
    print(year,'rows',len(rows),'total',body.get('totalRows'),'nodes',sorted(set(str(r['pnode_name']) for r in rows)),flush=True)
    if len(rows)!=body.get('totalRows',len(rows)): raise ValueError('Pagination required; refusing partial save')
    if not rows or any(int(r['pnode_id'])!=51288 for r in rows): raise ValueError('Node filter failed')
    dest.write_text(json.dumps(body))
    time.sleep(11)
print('Download complete',flush=True)
