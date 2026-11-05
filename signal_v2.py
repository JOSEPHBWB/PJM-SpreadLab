"""Frozen robust INC-only policy; one prequential 2026 evaluation, no result-based retuning."""
import base64,datetime,hashlib,html,json,re
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import research as R
import signals as S
ROOT=R.ROOT;OUT=R.OUT
CFG=json.loads((ROOT/'signal_v2_config.json').read_text())

def policy(pred,cost):
    return (np.asarray(pred)>np.asarray(cost)+CFG['extra_entry_buffer_usd_mwh']).astype(float)

def load_prices():
    old=R.load_data()
    body=json.loads((ROOT/'data/western_hub_2026.json').read_text())
    new=pd.DataFrame(body['items']).sort_values('datetime_beginning_utc').reset_index(drop=True)
    new['utc']=pd.to_datetime(new.datetime_beginning_utc,utc=True)
    new['local']=pd.to_datetime(new.datetime_beginning_ept)
    assert new.utc.is_unique and (new.pnode_id==51288).all()
    assert (new.utc.dt.tz_convert('America/New_York').dt.tz_localize(None)==new.local).all()
    for market in ['da','rt']:
        price=new[f'total_lmp_{market}'];assert np.isfinite(price).all()
        parts=sum(new[f'{part}_{market}'] for part in ['system_energy_price','congestion_price','marginal_loss_price'])
        assert np.abs(parts-price).max()<2e-5
    for k,v in {'date':new.local.dt.strftime('%Y-%m-%d'),'month':new.local.dt.strftime('%Y-%m'),'year':new.local.dt.year,'hour':new.local.dt.hour,'he':new.local.dt.hour+1,'weekend':(new.local.dt.dayofweek>=5).astype(int),'quarter':new.local.dt.quarter,'spread':new.total_lmp_da-new.total_lmp_rt}.items():new[k]=v
    allprices=pd.concat([old,new],ignore_index=True).sort_values('utc').reset_index(drop=True)
    assert allprices.utc.is_unique and (allprices.utc.diff().dropna()==pd.Timedelta(hours=1)).all()
    return R.attach_costs(allprices)

def hg(loss):return HistGradientBoostingRegressor(loss=loss,**CFG['hgb'])

def fit_month(train,test):
    ci=float((train.inc_unit_east+train.admin_segment).mean())
    cd=float((train.dec_unit_east+train.admin_segment).mean())
    models={'Load absolute INC':(hg('absolute_error'),S.CAL+S.LOAD),'Calendar absolute INC':(hg('absolute_error'),S.CAL),'Load squared INC':(hg('squared_error'),S.CAL+S.LOAD)}
    predictions={}
    for name,(model,features) in models.items():
        model.fit(train[features],train.spread)
        predictions[name]=model.predict(test[features])
    q={k:policy(v,ci) for k,v in predictions.items()}
    squared=predictions['Load squared INC']
    q['Load squared two-way']=np.where((squared-ci>0)&(squared-ci>=-squared-cd),1.,np.where(-squared-cd>0,-1.,0.))
    return q,predictions,ci,cd

def run():
    resultpath=OUT/'signal_v2_results.json'
    if resultpath.exists():raise RuntimeError('Evaluation already exists; refuse a second evaluation run.')
    freeze=json.loads((ROOT/'signal_v2_freeze.json').read_text())
    digest=hashlib.sha256((ROOT/'signal_v2_config.json').read_bytes()).hexdigest()
    assert digest==freeze['config_sha256'],'Frozen config changed'
    codefreeze=json.loads((ROOT/'signal_v2_code_freeze.json').read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==codefreeze['signal_v2_py_sha256']
    (OUT/'signal_v2_evaluation_started.json').write_text(json.dumps({'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'config_sha256':digest,'protocol':'first evaluation; no model selection from results'},indent=2))
    prices=load_prices();d,qa=S.build_features(prices)
    mask=(d.year==2026)&d.available
    e=d[mask].copy().reset_index(drop=True)
    names=['Load absolute INC','Calendar absolute INC','Load squared INC','Load squared two-way']
    qs={'No trade':np.zeros(len(e)),'Always INC':np.ones(len(e)),**{n:np.zeros(len(e)) for n in names}}
    preds={n:np.full(len(e),np.nan) for n in names[:-1]};audit=[]
    for month,g in e.groupby('month',sort=True):
        cut=pd.Timestamp(month+'-01')-pd.Timedelta(days=CFG['label_embargo_days'])
        train=d[(d.local<cut)&d.available]
        assert len(train)>30000 and train.local.max()<cut
        q,p,ci,cd=fit_month(train,g)
        ids=g.index.to_numpy()
        for name in names:qs[name][ids]=q[name]
        for name in preds:preds[name][ids]=p[name]
        audit.append({'month':month,'cutoff_exclusive':str(cut),'last_train_target':str(train.local.max()),'train_hours':len(train),'eval_hours':len(g),'expected_inc_cost':ci,'expected_dec_cost':cd})
        print('fitted',month,'train',len(train),'eval',len(g),flush=True)
    summaries={};monthly={};ledger={};sensitivity=[]
    for name,q in qs.items():
        net,gross,cost=R.pnl(e,q)
        summaries[name]=R.metrics(e,q,net,gross,cost)
        summaries[name]['invoice5_net']=float(R.pnl(e,q,invoices=5)[0].sum())
        ledger[name]={'q':q,'net':net,'gross':gross,'cost':cost}
        monthly[name]={}
        for month,g in e.groupby('month'):
            ids=g.index.to_numpy();monthly[name][month]=R.metrics(g,q[ids],net[ids],gross[ids],cost[ids])
        for extra in CFG['cost_sensitivity_usd_mwh']:sensitivity.append({'strategy':name,'extra_usd_mwh':extra,'net':float(R.pnl(e,q,extra=extra)[0].sum())})
    def daily(x):return pd.Series(x,index=e.date).groupby(level=0).sum().to_numpy()
    primary='Load absolute INC';paired={}
    for base in ['Always INC','Calendar absolute INC','Load squared INC','No trade']:
        paired[base]=R.paired_bootstrap(daily(ledger[primary]['net']),daily(ledger[base]['net']))
    matched=np.full(len(e),np.abs(qs[primary]).mean());matched_net,_,_=R.pnl(e,matched)
    paired['Equal-volume INC']=R.paired_bootstrap(daily(ledger[primary]['net']),daily(matched_net))
    result={'config':CFG,'freeze':freeze,'code_freeze':codefreeze,'availability':json.loads((ROOT/'data/availability_2026.json').read_text()),'qa':qa,'eval_months':list(monthly[primary]),'evaluation_hours':len(e),'strategies':summaries,'monthly':monthly,'paired_primary_increment':paired,'cost_sensitivity':sensitivity,'training_audit':audit}
    # Save numerical outcome once, even if presentation rendering later fails.
    resultpath.write_text(json.dumps(result,indent=2,allow_nan=False))
    rows=[]
    for i,row in e.iterrows():
        rows.append({'utc':str(row.utc),'issue_utc':str(row.issue),'decision_utc':str(row.decision),'assumed_available_utc':str(row.assumed_available),'median_spread_prediction':float(preds[primary][i]),'strategies':{name:{k:float(v[i]) for k,v in ls.items()} for name,ls in ledger.items()}})
    (OUT/'signal_v2_hourly_ledger.json').write_text(json.dumps(rows,allow_nan=False))
    plot(e,ledger)
    report(result)
    print('RESULTS',json.dumps({'net':{k:v['net']for k,v in summaries.items()},'paired':paired},ensure_ascii=False),flush=True)

def plot(e,ledger):
    fig,ax=plt.subplots(figsize=(12,5),layout='constrained')
    for name in ['Always INC','Load absolute INC','Calendar absolute INC','Load squared INC','Load squared two-way']:
        ax.plot(e.utc,np.cumsum(ledger[name]['net']),label=name,lw=1.4)
    ax.axhline(0,color='gray',lw=.6);ax.legend(fontsize=9)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2));ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.set(title='Frozen v2 | 2026 follow-on evaluation',ylabel='Cost-adjusted P&L, USD (<=1 MW/hour)')
    fig.savefig(OUT/'signal_v2.png',dpi=150);plt.close(fig)

def report(r):
    primary='Load absolute INC';p=r['strategies'][primary];b=r['strategies']['Always INC'];pair=r['paired_primary_increment']['Always INC']
    lines=['# PJM SpreadLab v2：冻结规则后的 2026 检验','',
      f'**结果：** 主策略（绝对损失、只做 INC）扣已建模成本后为 ${p["net"]:,.0f}；同样本固定 INC 为 ${b["net"]:,.0f}；增量 ${p["net"]-b["net"]:,.0f}。','',
      f'**不确定性：** 对固定 INC 的配对分块 bootstrap 增量 95% 区间为 [${pair["ci95_period_total"][0]:,.0f}, ${pair["ci95_period_total"][1]:,.0f}]。这是预先指定的比较，仍受样本长度和制度变化限制。','',
      '**样本性质：** v2 依据已查看的 2022–2025 结果设计，在下载本项目的 2026 价差结果之前冻结配置和代码，保留全部对照。2026 DA 价格此前已在其他工作中使用，因此称为后续时期、按时间滚动的冻结策略检验，不称完全未接触的盲测。','',
      '## 冻结规则','',
      '- 主策略：HGB absolute_error，预测条件中位数；只做 INC 或不交易，每小时最多 1 MW。',
      '- 门槛：预测值 > 训练期平均 INC 成本 + $0.50/MWh。绝对损失不等于期望收益估计，实际评价保留全部尾部盈亏。',
      '- 每月扩展训练，标签至少滞后 90 天；较早的 2026 标签可按同一规则进入后续月份训练。',
      '- 只使用 D−1 10:00 EPT 前的负荷预测、修订和日历；生成后 15 分钟可得性缓冲为假设。', '',
      '配置 SHA-256：'+r['freeze']['config_sha256'], '',
      f'共同完整截止月：{r["availability"]["common_end_month"]}；实际评估 {r["evaluation_hours"]:,} 个可用预测小时。缺预测小时从所有策略同步剔除。初步 operating reserve 和区域映射假设沿用 METHODS.md。','',
      '## 收益与风险','',
      R.md_table(['策略','成交 MWh','毛收益 $','费用 $','调整后 $','最大回撤 $','最差日 $','日 ES95 $'],[[name,f"{v['mwh']:,.0f}",f"{v['gross']:,.0f}",f"{v['cost']:,.0f}",f"{v['net']:,.0f}",f"{v['mdd']:,.0f}",f"{v['worst_day']:,.0f}",f"{v['daily_es95']:,.0f}"]for name,v in r['strategies'].items()]),'',
      '## 主策略增量','',
      R.md_table(['对照','总增量 $','95%配对区间 $'],[[name,f"{v['increment_total']:,.0f}",f"[{v['ci95_period_total'][0]:,.0f}, {v['ci95_period_total'][1]:,.0f}]"]for name,v in r['paired_primary_increment'].items()]),'',
      '只预测不改变方向的平方损失 INC 对照，用于区分禁止 DEC 和改变损失函数的影响；相同成交总量的均匀 INC 对照用于区分降低暴露与择时，并不匹配尾部风险或信用占用。','',
      '## 月度结果','',
      R.md_table(['月份']+list(r['strategies']),[[month]+[f"{r['monthly'][name][month]['net']:,.0f}"for name in r['strategies']]for month in r['eval_months']]),'',
      '## 额外成本敏感性','',
      R.md_table(['策略']+[f'+${c}/MWh'for c in CFG['cost_sensitivity_usd_mwh']],[[name]+[f"{v['net']:,.0f}"for v in r['cost_sensitivity']if v['strategy']==name]for name in r['strategies']]),'',
      '## 审计记录','',
      'signal_v2_config.json 和 signal_v2_freeze.json 记录先冻结的规则与哈希；signal_v2_code_freeze.json 固定实现；availability_2026.json 记录只用时间戳和计数进行的可得性检查；signal_v2_evaluation_started.json 记录首次评估。脚本发现已有结果会拒绝再次运行。没有按本轮结果重新选择模型或门槛。','',
      'METRICS：交易费用模型不是最终完整账单，统计区间没有校正所有研究者选择。预测生成时间不等于独立核验的公开发布时间。负荷预测历史覆盖有限的缺失小时，实际执行、信用与融资未完整模拟。','']
    text='\n'.join(lines);(OUT/'SIGNAL_V2_2026_zh.md').write_text(text)
    render_html(text,OUT/'signal_v2.png',OUT/'PJM_2026_Frozen_Evaluation.html')

def render_html(text,picture,dest):
    blocks=[]
    for para in text.split('\n\n'):
        if para.startswith('|'):
            cells=[[c.strip()for c in row.strip('|').split('|')]for row in para.splitlines()]
            blocks.append('<div class="table"><table><tr>'+''.join('<th>'+html.escape(c)+'</th>'for c in cells[0])+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>'for c in row)+'</tr>'for row in cells[2:])+'</table></div>')
        elif para.startswith('#'):
            n=len(para)-len(para.lstrip('#'));blocks.append(f'<h{n}>'+html.escape(para[n:].strip())+f'</h{n}>')
        else:blocks.append('<p>'+re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',html.escape(para)).replace('\n','<br>')+'</p>')
    data=base64.b64encode(picture.read_bytes()).decode();body=''.join(blocks).replace('</h1>','</h1><img src="data:image/png;base64,'+data+'" alt="Frozen v2 2026 equity curves">',1)
    dest.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PJM 2026 Frozen Evaluation</title><style>body{max-width:1200px;margin:40px auto;padding:0 24px;background:#f8fafc;color:#172033;font:16px/1.8 system-ui}img{width:100%}.table{overflow:auto}table{border-collapse:collapse;white-space:nowrap;background:white;width:100%;font-size:13px}th,td{padding:8px 12px;border-bottom:1px solid #ddd;text-align:right}th{background:#e2e8f0}th:first-child,td:first-child{text-align:left}p{overflow-wrap:anywhere}</style>'+body+'</html>')

if __name__=='__main__':run()
