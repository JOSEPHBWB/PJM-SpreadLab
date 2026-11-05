"""Download public cost feeds. Credentials are never saved."""
import getpass
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

root=Path(__file__).resolve().parent
key=os.environ.get('PJM_API_KEY') or getpass.getpass('PJM API key: ')
for feed in ['sched_9_10_rates','prelim_or_rates']:
    dest=root/'data'/f'{feed}.json'
    if dest.exists():
        print(feed,'cached; remove file to refresh')
        continue
    query=urllib.parse.urlencode({'rowCount':50000,'startRow':1})
    req=urllib.request.Request(f'https://api.pjm.com/api/v1/{feed}?{query}',headers={'Ocp-Apim-Subscription-Key':key})
    with urllib.request.urlopen(req,timeout=120) as response:
        body=json.load(response)
    if len(body.get('items',[]))!=body.get('totalRows'):
        raise RuntimeError('Feed exceeds one page; refusing partial download')
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(body))
    print(feed,len(body['items']),'rows')
    time.sleep(11)
