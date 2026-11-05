"""Timestamp-aware load signal pilot; future realized errors are labels, never signals."""
import json, math, hashlib, base64, html, re
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from scipy.stats import pearsonr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import research as R
ROOT=R.ROOT;OUT=ROOT/'outputs';CFG=json.loads((ROOT/'signal_config.json').read_text())

CAL=['hour_sin','hour_cos','hour_sin2','hour_cos2','dow_sin','dow_cos','month_sin','month_cos','weekend']
LOAD=['forecast_gw','day_mean','day_max','day_min','day_range','ramp','relative_load','forecast_age','revision_gw','has_revision']

def build_features(prices):
    rows=[]
    for path in sorted((ROOT/'data'/'forecast').glob('load_forecast_*_h*.json')):
        body=json.loads(path.read_text());assert len(body['items'])==body['totalRows'];rows.extend(body['items'])
    f=pd.DataFrame(rows)
    assert set(f.forecast_area)=={'RTO'}
    f['utc']=pd.to_datetime(f.forecast_hour_beginning_utc,utc=True)
    f['issue']=pd.to_datetime(f.evaluated_at_utc,utc=True)
    assert not f.duplicated(['utc','issue']).any()
    local=f.utc.dt.tz_convert('America/New_York').dt.tz_localize(None)
    decision_local=local.dt.normalize()-pd.Timedelta(days=1)+pd.Timedelta(hours=CFG['decision_hour_ept'])
    f['decision']=decision_local.dt.tz_localize('America/New_York').dt.tz_convert('UTC')
    f['assumed_available']=f.issue+pd.Timedelta(minutes=CFG['creation_to_availability_buffer_minutes'])
    eligible=f[f.assumed_available<=f.decision].sort_values(['utc','issue']).copy()
    assert (eligible.issue<eligible.utc).all()
    eligible['prior_value']=eligible.groupby('utc').forecast_load_mw.shift()
    eligible['prior_issue']=eligible.groupby('utc').issue.shift()
    selected=eligible.groupby('utc').tail(1).copy()
    selected['revision_gw']=(selected.forecast_load_mw-selected.prior_value).fillna(0)/1000
    selected['has_revision']=selected.prior_value.notna().astype(float)
    d=prices.merge(selected[['utc','issue','decision','assumed_available','forecast_load_mw','revision_gw','has_revision']],on='utc',how='left',validate='one_to_one')
    d['available']=d.forecast_load_mw.notna()
    assert (d.loc[d.available,'assumed_available']<=d.loc[d.available,'decision']).all()
    d['forecast_gw']=d.forecast_load_mw/1000
    group=d.groupby('date').forecast_gw
    d['day_mean']=group.transform('mean');d['day_max']=group.transform('max');d['day_min']=group.transform('min')
    d['day_range']=d.day_max-d.day_min
    d['ramp']=d.groupby('date').forecast_gw.diff().fillna(0.)
    d['relative_load']=d.forecast_gw-d.day_mean
    d['forecast_age']=(d.decision-d.issue).dt.total_seconds()/3600
    for label,value,period in [('hour',d.hour,24),('dow',d.local.dt.dayofweek,7),('month',d.local.dt.month-1,12)]:
        d[label+'_sin']=np.sin(2*np.pi*value/period);d[label+'_cos']=np.cos(2*np.pi*value/period)
    d['hour_sin2']=np.sin(4*np.pi*d.hour/24);d['hour_cos2']=np.cos(4*np.pi*d.hour/24)
    actual_paths=sorted((ROOT/'data'/'forecast').glob('actual_load_*_h*.json'))
    actual=[]
    for path in actual_paths:actual.extend(json.loads(path.read_text())['items'])
    if actual:
        a=pd.DataFrame(actual);a['utc']=pd.to_datetime(a.datetime_beginning_utc,utc=True)
        assert not a.duplicated(['utc','load_area']).any()
        expected={'AEP','AP','ATSI','DAY','DEOK','DOM','DUQ','EKPC','MIDATL','NI'}
        assert set(a.load_area)==expected
        a=a[np.isfinite(a.prelim_load_avg_hourly)].copy()
        counts=a.groupby('utc').load_area.nunique()
        complete=counts[counts==len(expected)].index
        # Sum the ten non-overlapping regional components; never double-count a total row.
        a=a[a.utc.isin(complete)].groupby('utc',as_index=False).prelim_load_avg_hourly.sum()
        a['actual_gw']=a.prelim_load_avg_hourly/1000
        d=d.merge(a[['utc','actual_gw']],on='utc',how='left',validate='one_to_one')
        d['error_gw']=d.actual_gw-d.forecast_gw
    else:d['actual_gw']=np.nan;d['error_gw']=np.nan
    qa={'raw_forecast_rows':len(f),'selected_target_hours':len(selected),'price_hours':len(d),'covered_price_hours':int(d.available.sum()),
        'coverage_by_year':{str(y):{'hours':len(g),'covered':int(g.available.sum()),'with_prior_revision':int((g.has_revision==1).sum())} for y,g in d.groupby('year')},
        'actual_hours':int(d.actual_gw.notna().sum()),'issue_before_cutoff':True}
    return d,qa

def hg():return HistGradientBoostingRegressor(**CFG['hgb'])
def ridge():return make_pipeline(StandardScaler(),Ridge(alpha=CFG['ridge_alpha']))

def backtest(d):
    d=d.copy()
    for col in ['pred_calendar','pred_ridge','pred_load','pred_error','pred_error_spread','ci','cd']:d[col]=np.nan
    audit=[]
    for month in sorted(d.loc[d.year>=2023,'month'].unique()):
        start=pd.Timestamp(month+'-01');cut=start-pd.Timedelta(days=CFG['label_embargo_days'])
        tr=d[(d.local<cut)&d.available].copy();te=d[(d.month==month)&d.available]
        if len(te)==0:continue
        assert len(tr)>5000 and tr.local.max()<cut
        costs=[float((tr.inc_unit_east+tr.admin_segment).mean()),float((tr.dec_unit_east+tr.admin_segment).mean())]
        cal=hg().fit(tr[CAL],tr.spread)
        lin=ridge().fit(tr[CAL+LOAD],tr.spread)
        model=hg().fit(tr[CAL+LOAD],tr.spread)
        d.loc[te.index,'pred_calendar']=cal.predict(te[CAL]);d.loc[te.index,'pred_ridge']=lin.predict(te[CAL+LOAD]);d.loc[te.index,'pred_load']=model.predict(te[CAL+LOAD])
        d.loc[te.index,['ci','cd']]=costs
        err_tr=tr.dropna(subset=['error_gw'])
        if len(err_tr)>5000:
            error_model=hg().fit(err_tr[CAL+LOAD],err_tr.error_gw)
            error_hat=error_model.predict(te[CAL+LOAD])
            # Structural association fit uses realized error ONLY as training explanatory variable.
            # At decision time replace it with a forecast from issue-timestamped inputs.
            stage=ridge().fit(err_tr[CAL+['error_gw']],err_tr.spread)
            stage_x=te[CAL].copy();stage_x['error_gw']=error_hat
            d.loc[te.index,'pred_error']=error_hat
            d.loc[te.index,'pred_error_spread']=stage.predict(stage_x)
        audit.append({'month':month,'cutoff_exclusive':str(cut),'last_train_target':str(tr.local.max()),'train_hours':len(tr),'eval_hours':len(te),'error_train_hours':len(err_tr)})
        print('fit',month,'train',len(tr),'eval',len(te),flush=True)
    return d,audit

def choose(d,pred):
    inc=pred-d.ci.to_numpy();dec=-pred-d.cd.to_numpy()
    return np.where(np.isfinite(pred),np.where((inc>0)&(inc>=dec),1.,np.where(dec>0,-1.,0.)),0.)

def run():
    prices=R.attach_costs(R.load_data())
    d,qa=build_features(prices)
    d,audit=backtest(d)
    e=d[(d.year>=2023)&d.available].reset_index(drop=True)
    qs={'No trade':np.zeros(len(e)),'Always INC':np.ones(len(e)),'Always DEC':-np.ones(len(e)),
        'Calendar HGB':choose(e,e.pred_calendar.to_numpy()),'Load Ridge':choose(e,e.pred_ridge.to_numpy()),'Load HGB':choose(e,e.pred_load.to_numpy())}
    if e.pred_error_spread.notna().all():qs['Expected error -> spread']=choose(e,e.pred_error_spread.to_numpy())
    summaries={};annual={};ledgers={};pairs={};sensitivity=[]
    days=sorted(e.date.unique())
    def daily(x):return pd.Series(x,index=e.date).groupby(level=0).sum().reindex(days).to_numpy()
    for name,q in qs.items():
        net,gross,cost=R.pnl(e,q);summaries[name]=R.metrics(e,q,net,gross,cost);ledgers[name]={'q':q,'net':net,'gross':gross,'cost':cost}
        annual[name]={}
        for y,g in e.groupby('year'):
            ids=g.index.to_numpy();annual[name][str(y)]=R.metrics(g,q[ids],net[ids],gross[ids],cost[ids])
        summaries[name]['invoice5_net']=float(R.pnl(e,q,invoices=5)[0].sum())
        for extra in [0,.25,.5,1,2]:sensitivity.append({'strategy':name,'extra_cost':extra,'net':float(R.pnl(e,q,extra=extra)[0].sum())})
    for name in list(qs)[3:]:
        pairs[name]={}
        for base in ['Always INC','Calendar HGB','No trade']:
            pairs[name][base]=R.paired_bootstrap(daily(ledgers[name]['net']),daily(ledgers[base]['net']))
    prediction={}
    for name,col in [('Calendar HGB','pred_calendar'),('Load Ridge','pred_ridge'),('Load HGB','pred_load'),('Expected error -> spread','pred_error_spread')]:
        m=e[col].notna()
        if m.any():prediction[name]={'mae':float(np.abs(e.loc[m,col]-e.loc[m,'spread']).mean()),'rmse':float(np.mean((e.loc[m,col]-e.loc[m,'spread'])**2)**.5)}
    prediction['Zero spread']={'mae':float(np.abs(e.spread).mean()),'rmse':float(np.mean(e.spread**2)**.5)}
    actual=e.dropna(subset=['error_gw','pred_error'])
    diagnostics={}
    if len(actual):
        raw_corr=float(actual[['error_gw','spread']].corr().iloc[0,1])
        diagnostics={'hours':len(actual),'ex_post_error_spread_correlation':raw_corr,'error_mae_zero':float(np.abs(actual.error_gw).mean()),'error_mae_model':float(np.abs(actual.error_gw-actual.pred_error).mean()),'error_prediction_correlation':float(actual[['error_gw','pred_error']].corr().iloc[0,1]),'definition':'error=actual RTO load - pre-decision RTO forecast, GW; realized error is explanatory/label only'}
    results={'config':CFG,'config_sha256':hashlib.sha256((ROOT/'signal_config.json').read_bytes()).hexdigest(),'data_qa':qa,'training_audit':audit,'strategies':summaries,'annual':annual,'paired_bootstrap':pairs,'prediction_metrics':prediction,'error_diagnostics':diagnostics,'cost_sensitivity':sensitivity}
    (OUT/'signal_results.json').write_text(json.dumps(results,indent=2,allow_nan=False))
    ledger=[]
    for i,row in e.iterrows():
        ledger.append({'utc':str(row.utc),'decision_utc':str(row.decision),'issue_utc':str(row.issue),'assumed_available_utc':str(row.assumed_available),
             'forecast_gw':float(row.forecast_gw),'pred_load_spread':float(row.pred_load),'strategies':{name:{k:float(v[i]) for k,v in values.items()} for name,values in ledgers.items()}})
    (OUT/'signal_hourly_ledger.json').write_text(json.dumps(ledger,allow_nan=False))
    plot(e,ledgers,actual)
    report(results)
    print('RESULTS',json.dumps({'qa':qa,'net':{k:v['net'] for k,v in summaries.items()},'error':diagnostics},ensure_ascii=False),flush=True)

def plot(e,ledgers,actual):
    fig,ax=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for name in ['Always INC','Calendar HGB','Load Ridge','Load HGB','Expected error -> spread']:
        if name in ledgers:ax[0].plot(e.utc,np.cumsum(ledgers[name]['net']),label=name,lw=1.2)
    ax[0].axhline(0,color='gray',lw=.5);ax[0].set(title='Fixed-rule load signals | cost-adjusted P&L',ylabel='USD, <=1 MW/hour')
    ax[0].xaxis.set_major_locator(mdates.YearLocator());ax[0].xaxis.set_major_formatter(mdates.DateFormatter('%Y'));ax[0].legend(fontsize=8)
    if len(actual):
        bins=pd.qcut(actual.error_gw,10,duplicates='drop')
        points=actual.groupby(bins,observed=True)[['error_gw','spread']].mean()
        ax[1].plot(points.error_gw,points.spread,marker='o')
        ax[1].set(title='Realized load error vs DA-RT | explanatory only',xlabel='Actual - forecast load, GW',ylabel='Mean DA-RT, USD/MWh')
    else:ax[1].text(.5,.5,'Actual-load labels unavailable',ha='center')
    fig.suptitle('PJM SpreadLab — issue-timestamped load forecast pilot',fontsize=14)
    fig.savefig(OUT/'signals.png',dpi=150);plt.close(fig)

def report(r):
    s=r['strategies'];dg=r['error_diagnostics'];qa=r['data_qa']
    lines=['# PJM SpreadLab：负荷预测信号检验','',
      f'**收益：** 主检验 Load HGB 成本调整后为 ${s["Load HGB"]["net"]:,.0f}，同一可用预测样本的固定 INC 为 ${s["Always INC"]["net"]:,.0f}；加入负荷信息没有改善本轮交易结果。','',
      f'**机制：** 事后误差与价差的相关系数为 {dg["ex_post_error_spread_correlation"]:.3f}，但预测误差 MAE 为 {dg["error_mae_model"]:.3f} GW，未优于假设误差为零的 {dg["error_mae_zero"]:.3f} GW。事后解释力没有转化为事前可交易能力。' if dg else '**机制：** 当前未取得完整实际负荷标签，不能计算误差机制检验。','',
      '**判断：** 保留全部固定模型结果，本轮没有据此调参。后续需要新的事前信息和未见数据，而非从这轮回测中继续挑规则。','',
      '**数据：** 已取得带生成时间的历史 RTO 负荷预测；按交付前一日 10:00 EPT 选择当时最近版本，并预留 15 分钟可得性缓冲。风光预测只保留最近 30 天，本轮未加入。','',
      '**范围：** 2023–2025 历史滚动评估；每月重新拟合，训练标签滞后至少 90 天。原样本已被查看，不是未见测试集。成本沿用 RTO + East 和管理费；此处报告成本调整收益。','',
      '## 数据与可得性','',
      R.md_table(['年份','价格小时','可用负荷预测小时','可用更早预测修订小时'],[[y,v['hours'],v['covered'],v['with_prior_revision']] for y,v in qa['coverage_by_year'].items()]),'',
      f'本轮所有策略统一比较 {s["Always INC"]["hours"]:,} 个可用预测小时；缺预测小时同时从信号和基准中剔除。因此固定 INC 数值不同于上一里程碑的全价格样本，不能跨样本直接比较。','',
      'evaluated_at 是预测生成时间，尚未独立核实每条记录的公开发布时间。15 分钟缓冲是研究假设；历史档案的日后入库时间不被当成当日发布时间。所有被选记录的生成时间和假定可得时间均早于决策截止。','',
      '## 先区分两种“预测误差”','',
      '交付日的实际负荷减事前预测，是事后误差，可用来解释 DA–RT 价差，但不能作为该日投标信号。可交易输入只使用事前负荷预测、已发布修订及其日内形状。Expected error → spread 先预测误差，再代入训练期学到的价差关系；交易时没有读取当天实际负荷。','']
    if dg:lines +=[R.md_table(['指标','结果'],[['事后误差与 DA−RT 相关系数',f"{dg['ex_post_error_spread_correlation']:.3f}"],['误差预测与实际误差相关系数',f"{dg['error_prediction_correlation']:.3f}"],['假设误差为零 MAE（GW）',f"{dg['error_mae_zero']:.3f}"],['模型预测误差 MAE（GW）',f"{dg['error_mae_model']:.3f}"]]),'']
    lines+=['## 预先固定的模型对照','',
      'Calendar HGB 只用日历；Load HGB 使用相同算法和参数、增加事前负荷信息，构成信息增量对照。Load Ridge 为线性对照。Expected error → spread 为两步机制检验。所有版本均展示，没有根据本轮收益挑选参数。','',
      R.md_table(['策略','成交 MWh','毛收益 $','成本 $','调整后 $','最大回撤 $','最差日 $','日 ES95 $'],[[k,f"{v['mwh']:,.0f}",f"{v['gross']:,.0f}",f"{v['cost']:,.0f}",f"{v['net']:,.0f}",f"{v['mdd']:,.0f}",f"{v['worst_day']:,.0f}",f"{v['daily_es95']:,.0f}"] for k,v in s.items()]),'',
      R.md_table(['策略','2023 $','2024 $','2025 $','每活跃月5张发票后 $'],[[name]+[f"{r['annual'][name][y]['net']:,.0f}" for y in ['2023','2024','2025']]+[f"{v['invoice5_net']:,.0f}"] for name,v in s.items()]),'',
      '## 信号增量的不确定性','',
      R.md_table(['策略','对照','增量 $','95%配对分块bootstrap区间 $'],[[name,base,f"{v['increment_total']:,.0f}",f"[{v['ci95_period_total'][0]:,.0f}, {v['ci95_period_total'][1]:,.0f}]"] for name,pairs in r['paired_bootstrap'].items() for base,v in pairs.items()]),'',
      '7天循环分块、2,000次；未校正多重比较和模型选择，区间仅为该样本的探索性推断。','',
      '## 预测误差与交易收益分开评估','',
      R.md_table(['模型','Spread MAE $/MWh','RMSE $/MWh'],[[k,f"{v['mae']:.3f}",f"{v['rmse']:.3f}"] for k,v in r['prediction_metrics'].items()]),'',
      '## 复现和限制','',
      'python fetch_forecasts.py；python fetch_actual_load.py；python signals.py。配置和参数在 signal_config.json，完整数值在 outputs/signal_results.json，逐小时选择版本和仓位在 outputs/signal_hourly_ledger.json。负荷误差标签使用初步实际负荷，并非精确最终负荷；最终价格、实际负荷及历史预测的修订版本仍需 point-in-time 核验。完整费用限制见 METHODS.md。','',
      '官方来源：','',
      '- https://dataminer2.pjm.com/feed/load_frcstd_hist/definition',
      '- https://dataminer2.pjm.com/feed/hrl_load_prelim/definition',
      '- https://dataminer2.pjm.com/feed/hourly_wind_power_forecast/definition',
      '- https://dataminer2.pjm.com/feed/hourly_solar_power_forecast/definition','']
    posthoc=OUT/'SIGNAL_V1_POSTHOC_zh.md'
    if posthoc.exists():
        lines+=['## 事后诊断：方向与负荷分档','',posthoc.read_text().split('\n',1)[1]]
    text='\n'.join(lines);(OUT/'SIGNALS_zh.md').write_text(text)
    blocks=[]
    for p in text.split('\n\n'):
        if p.startswith('|'):
            cells=[[c.strip() for c in row.strip('|').split('|')] for row in p.splitlines()]
            blocks.append('<div class="table"><table><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in cells[0])+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in row)+'</tr>' for row in cells[2:])+'</table></div>')
        elif p.startswith('#'):
            n=len(p)-len(p.lstrip('#'));blocks.append(f'<h{n}>'+html.escape(p[n:].strip())+f'</h{n}>')
        else:blocks.append('<p>'+re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',html.escape(p)).replace('\n','<br>')+'</p>')
    picture=base64.b64encode((OUT/'signals.png').read_bytes()).decode()
    body=''.join(blocks).replace('</h1>','</h1><img alt="Signal backtest and load error relationship" src="data:image/png;base64,'+picture+'">',1)
    (OUT/'PJM_Load_Signals.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PJM Load Signals</title><style>body{max-width:1200px;margin:40px auto;padding:0 24px;font:16px/1.8 system-ui;color:#172033;background:#f8fafc}img{width:100%}.table{overflow:auto}table{border-collapse:collapse;font-size:13px;white-space:nowrap;background:white;width:100%}td,th{padding:8px 12px;border-bottom:1px solid #ddd;text-align:right}td:first-child,th:first-child{text-align:left}th{background:#e2e8f0}h2{margin-top:36px}</style>'+body+'</html>')

if __name__=='__main__':run()
