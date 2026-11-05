"""Reproducible cost / risk / signal audit; no credentials or third-party models."""
import base64
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import skew
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT/'research_config.json').read_text())
OUT = ROOT/'outputs'
OUT.mkdir(exist_ok=True)

def nw_mean(x, lag=168):
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2: return {'mean': float(x.mean()) if n else 0., 'se': 0., 't': None}
    z = x-x.mean()
    lr = np.dot(z,z)/n
    for k in range(1, min(lag,n-1)+1):
        lr += 2*(1-k/(lag+1))*np.dot(z[k:],z[:-k])/n
    se = math.sqrt(max(0.,lr)/n)
    return {'mean':float(x.mean()), 'se':se, 't':float(x.mean()/se) if se else None,
            'ci95':[float(x.mean()-1.96*se),float(x.mean()+1.96*se)]}

def es_loss(x, alpha=.95):
    x=np.sort(np.asarray(x,dtype=float))
    return float(max(0.,-x[:max(1,math.ceil(len(x)*(1-alpha)))].mean())) if len(x) else 0.

def mdd(x):
    nav=np.r_[0.,np.cumsum(np.asarray(x,dtype=float))]
    return float(np.max(np.maximum.accumulate(nav)-nav))

def load_data():
    frames=[]
    for y in range(2022,2026):
        raw=json.loads((ROOT/'data'/f'western_hub_{y}.json').read_text())
        f=pd.DataFrame(raw['items'])
        expected_hours=int((pd.Timestamp(y+1,1,1)-pd.Timestamp(y,1,1))/pd.Timedelta(hours=1))
        assert len(f)==expected_hours
        frames.append(f)
    d=pd.concat(frames,ignore_index=True).sort_values('datetime_beginning_utc').reset_index(drop=True)
    d['utc']=pd.to_datetime(d.datetime_beginning_utc,utc=True)
    d['local']=pd.to_datetime(d.datetime_beginning_ept)
    assert d.utc.is_unique and (d.utc.diff().dropna()==pd.Timedelta(hours=1)).all()
    assert (d.pnode_id==51288).all() and (d.pnode_name=='WESTERN HUB').all()
    assert (d.utc.dt.tz_convert('America/New_York').dt.tz_localize(None)==d.local).all()
    for market in ['da','rt']:
        v=d[f'total_lmp_{market}']
        assert np.isfinite(v).all()
        total=sum(d[f'{s}_{market}'] for s in ['system_energy_price','congestion_price','marginal_loss_price'])
        assert np.max(np.abs(total-v))<2e-5
    d['date']=d.local.dt.strftime('%Y-%m-%d')
    d['month']=d.local.dt.strftime('%Y-%m')
    d['year']=d.local.dt.year
    d['hour']=d.local.dt.hour
    d['he']=d.hour+1
    d['weekend']=(d.local.dt.dayofweek>=5).astype(int)
    d['quarter']=d.local.dt.quarter
    d['spread']=d.total_lmp_da-d.total_lmp_rt
    return d

def attach_costs(d):
    rates=pd.DataFrame(json.loads((ROOT/'data'/'sched_9_10_rates.json').read_text())['items'])
    rates=rates[rates.row_is_current].copy()
    rates['month']=rates.schedule_month.str[:7]
    assert not rates.duplicated(['month','schedule_name']).any()
    pivot=rates.pivot(index='month',columns='schedule_name',values='schedule_rate')
    def get(name, optional=False):
        a=d.month.map(pivot[name]) if name in pivot else pd.Series(np.nan,index=d.index)
        if optional: return a.fillna(0.)
        assert a.notna().all(),name
        return a
    energy=get('9-3: Market Support - Component 1')+get('9-MMU: Market Monitoring Unit (MMU) Funding - Component 1')
    segment=get('9-3: Market Support - Component 2')+get('9-MMU: Market Monitoring Unit (MMU) Funding - Component 2')
    energy+=get('9-PSI: PJM Settlement, Inc. - 9-3 Component 1',True)
    segment+=get('9-PSI: PJM Settlement, Inc. - 9-3 Component 2',True)
    # PSI split usage rates apply from February 2023; absence before then is a different regime, not imputation.
    assert get('9-PSI: PJM Settlement, Inc. - 9-3 Component 1',True)[d.month>='2023-02'].gt(0).all()
    invoice=get('9-PSI: PJM Settlement, Inc. - Per Invoice',True)
    old=get('9-PSI: PJM Settlement, Inc.',True)
    d['invoice_rate']=np.where(d.month<'2023-02',old,invoice)
    assert (d.invoice_rate>0).all()
    reserve=pd.DataFrame(json.loads((ROOT/'data'/'prelim_or_rates.json').read_text())['items'])
    reserve['date']=reserve.operating_reserve_date.str[:10]
    assert reserve.date.is_unique
    reserve=reserve.set_index('date')
    def daily(field):
        out=d.date.map(reserve[field]);assert out.notna().all(),field
        return out
    d['admin_energy']=energy
    d['admin_segment']=segment
    d['bor_rto']=daily('rto_bal_op_res_dev_rate')
    d['bor_east']=daily('east_bal_op_res_dev_rate')
    d['bor_west']=daily('west_bal_op_res_dev_rate')
    d['bor_regional_stress']=np.maximum(d.bor_east,d.bor_west)
    d['da_or']=daily('da_operating_reserve_rate')
    for scenario, regional in [('rto',0.),('east',d.bor_east),('regional_stress',d.bor_regional_stress)]:
        d[f'inc_unit_{scenario}']=energy+d.bor_rto+regional
        d[f'dec_unit_{scenario}']=d[f'inc_unit_{scenario}']+d.da_or
    return d

def predict(d, exclude_training_dates=()):
    """All fit inputs precede each month start by at least 60 days; target calendar only."""
    d=d.copy()
    for col in ['pred_spread','pred_cost_inc','pred_cost_dec','tail_inc','tail_dec']:
        d[col]=np.nan
    audits=[]
    pc=CFG['shrinkage_pseudocount']
    for month in sorted(d.loc[d.year>=2023,'month'].unique()):
        start=pd.Timestamp(month+'-01')
        cutoff=start-pd.Timedelta(days=CFG['label_embargo_days'])
        train=d[(d.local<cutoff)&(~d.date.isin(exclude_training_dates))].copy()
        target=d[d.month==month]
        assert len(train)>6000 and train.local.max()<cutoff
        assert train.local.max()<target.local.min()-pd.Timedelta(days=59)
        global_mu=float(train.spread.mean())
        hour=train.groupby('hour').spread.agg(['sum','count'])
        hour_mu=(hour['sum']+pc*global_mu)/(hour['count']+pc)
        groups=train.groupby(['hour','weekend','quarter']).spread.agg(['sum','count'])
        ci=float((train.inc_unit_east+train.admin_segment).mean())
        cd=float((train.dec_unit_east+train.admin_segment).mean())
        for key,g in target.groupby(['hour','weekend','quarter']):
            h=key[0]
            mu=(groups.loc[key,'sum']+pc*hour_mu[h])/(groups.loc[key,'count']+pc) if key in groups.index else hour_mu[h]
            # Historical direction-specific tails, hour-conditioned with a global floor. No test-period risk inputs.
            past=train[train.hour==h]
            ei=max(es_loss(past.spread,.99),es_loss(train.spread,.99),1.)
            ed=max(es_loss(-past.spread,.99),es_loss(-train.spread,.99),1.)
            d.loc[g.index,['pred_spread','pred_cost_inc','pred_cost_dec','tail_inc','tail_dec']]=[mu,ci,cd,ei,ed]
        audits.append({'month':month,'cutoff_exclusive':str(cutoff),'train_max_local':str(train.local.max()),'train_rows':len(train)})
    return d,audits

def positions(d):
    mu=d.pred_spread.to_numpy()
    inc_edge=mu-d.pred_cost_inc.to_numpy()
    dec_edge=-mu-d.pred_cost_dec.to_numpy()
    cal=np.where((inc_edge>0)&(inc_edge>=dec_edge),1.,np.where(dec_edge>0,-1.,0.))
    tail=np.where(cal>0,d.tail_inc,d.tail_dec)
    scaled=cal*np.minimum(1.,CFG['risk_hourly_es99_budget_usd']/tail)
    return {'No trade':np.zeros(len(d)), 'Always INC':np.ones(len(d)), 'Always DEC':-np.ones(len(d)),
            'Calendar INC filter':np.where(inc_edge>0,1.,0.), 'Calendar two-way':cal, 'Calendar risk-scaled':scaled}

def pnl(d,q,scenario='east',extra=0.,invoices=0):
    q=np.asarray(q,dtype=float)
    gross=q*d.spread.to_numpy()
    # Variable fees scale with cleared MW; segment fees scale with active submitted segments, not MW.
    unit=np.where(q>=0,d[f'inc_unit_{scenario}'],d[f'dec_unit_{scenario}'])
    variable=np.abs(q)*(unit+extra)
    segment=(np.abs(q)>1e-12)*d.admin_segment.to_numpy()
    fixed=np.zeros(len(d))
    if invoices:
        for month,g in d.groupby('month'):
            ix=d.index.get_indexer(g.index)
            active=ix[np.abs(q[ix])>1e-12]
            if len(active):fixed[active[-1]]=invoices*float(g.invoice_rate.iloc[0])
    return np.asarray(gross-variable-segment-fixed),np.asarray(gross),np.asarray(variable+segment+fixed)

def metrics(d,q,net,gross,cost):
    daily=pd.Series(net,index=d.date).groupby(level=0).sum()
    active=np.abs(q)>1e-12
    traded=float(np.abs(q).sum())
    nw=nw_mean(daily.to_numpy(),7)
    return {'hours':len(d),'active_hours':int(active.sum()),'mwh':traded,'gross':float(gross.sum()),'cost':float(cost.sum()),
            'net':float(net.sum()),'net_per_mwh':float(net.sum()/traded) if traded else None,
            'mdd':mdd(net),'worst_day':float(daily.min()),'worst_day_date':str(daily.idxmin()),
            'daily_es95':es_loss(daily,.95),'active_hour_es99':es_loss(net[active],.99),
            'daily_nw_t':nw['t'],'win_rate_active':float((net[active]>0).mean()) if active.any() else None,
            'break_even_extra_per_mwh':float(net.sum()/traded) if traded else None}

def paired_bootstrap(a,b):
    delta=np.asarray(a)-np.asarray(b);n=len(delta)
    rng=np.random.default_rng(CFG['bootstrap_seed'])
    block=CFG['bootstrap_block_days'];count=math.ceil(n/block)
    starts=rng.integers(0,n,size=(CFG['bootstrap_replications'],count))
    ids=(starts[:,:,None]+np.arange(block))%n
    means=delta[ids.reshape(len(starts),-1)[:,:n]].mean(axis=1)
    return {'increment_total':float(delta.sum()),'mean_daily_increment':float(delta.mean()),
            'ci95_daily':np.quantile(means,[.025,.975]).tolist(),
            'ci95_period_total':[float(x*n) for x in np.quantile(means,[.025,.975])],
            'block_days':block,'note':'paired circular block bootstrap; exploratory, not adjusted for strategy selection or regime change'}

def md_table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])

def review_diagnostics(d,e,ledgers):
    q=ledgers['Calendar two-way']['q']
    split={}
    for label,mask in [('INC',q>0),('DEC',q<0)]:
        split[label]={k:float(ledgers['Calendar two-way'][k][mask].sum()) for k in ['gross','cost','net']}
    counts=e.loc[q<0].groupby('he').size().sort_values(ascending=False)
    # Influence diagnostic only: remove storm dates from fitting; keep EVERY evaluation outcome.
    counter,_=predict(d,exclude_training_dates=('2022-12-23','2022-12-24'))
    counter=counter[counter.year>=2023].reset_index(drop=True)
    qc=positions(counter)['Calendar two-way']
    changed=(q<0)&(qc>=0)
    influence={'excluded_training_dates':['2022-12-23','2022-12-24'],
               'original_dec_hours':int((q<0).sum()),'counterfactual_dec_hours':int((qc<0).sum()),
               'original_dec_hours_no_longer_dec':int(changed.sum()),
               'fraction_original_dec_changed':float(changed.sum()/(q<0).sum()),
               'note':'Post-hoc training-influence diagnostic, not a deployable storm filter; evaluation outcomes retained, no counterfactual performance used for model selection.'}
    matched_extra_segments=float(e.loc[ledgers['Calendar INC filter']['q']==0,'admin_segment'].sum())
    return {'two_way_direction_split':split,'dec_he_counts':{str(k):int(v) for k,v in counts.items()},
            'dec_q4_fraction':float((e.loc[q<0,'quarter']==4).mean()),
            'risk_scaled_active_median_mw':float(np.median(np.abs(ledgers['Calendar risk-scaled']['q'][ledgers['Calendar risk-scaled']['q']!=0]))),
            'equal_volume_control_extra_segment_fees':matched_extra_segments,'storm_influence':influence}

def main():
    d=attach_costs(load_data())
    predicted,audits=predict(d)
    e=predicted[predicted.year>=2023].reset_index(drop=True)
    qs=positions(e)
    summaries={};ledgers={};annual={};sens=[];paired={}
    for name,q in qs.items():
        net,gross,cost=pnl(e,q)
        summaries[name]=metrics(e,q,net,gross,cost)
        ledgers[name]={'q':q,'net':net,'gross':gross,'cost':cost}
        annual[name]={}
        for y,g in e.groupby('year'):
            ix=g.index.to_numpy()
            annual[name][str(y)]=metrics(g,q[ix],net[ix],gross[ix],cost[ix])
        for extra in CFG['extra_cost_sensitivity_usd_mwh']:
            n,_,_=pnl(e,q,extra=extra)
            sens.append({'strategy':name,'extra_usd_mwh':extra,'net':float(n.sum())})
        for scenario in ['rto','east','regional_stress']:
            n,gr,c=pnl(e,q,scenario=scenario,invoices=5)
            summaries[name][scenario+'_5_invoices_net']=float(n.sum())
        summaries[name]['rto_only_net']=float(pnl(e,q,scenario='rto')[0].sum())
    days=sorted(e.date.unique())
    def daily(x): return pd.Series(x,index=e.date).groupby(level=0).sum().reindex(days).to_numpy()
    for name in ['Calendar INC filter','Calendar two-way','Calendar risk-scaled']:
        q=qs[name]
        matched=np.full(len(e),np.abs(q).mean())
        mn,_,_=pnl(e,matched)
        paired[name]={'versus_always_inc':paired_bootstrap(daily(ledgers[name]['net']),daily(ledgers['Always INC']['net'])),
                      'versus_no_trade':paired_bootstrap(daily(ledgers[name]['net']),np.zeros(len(days))),
                      'versus_equal_volume_inc':paired_bootstrap(daily(ledgers[name]['net']),daily(mn))}
    baseline={};tail_days={};component=[]
    for y,g in d.groupby('year'):
        x=g.spread.to_numpy(); n=len(x)
        lo,hi=np.quantile(x,[.01,.99])
        daily_g=g.groupby('date').spread.sum()
        nw=nw_mean(x)
        baseline[str(y)]={'hours':n,'mean':float(x.mean()),'median':float(np.median(x)),'trimmed_mean_1pct':float(x[(x>=lo)&(x<=hi)].mean()),
             'skewness':float(skew(x,bias=False)),'win_rate':float((x>0).mean()),'nw168':nw,'nw24':nw_mean(x,24),'nw336':nw_mean(x,336),
             'gross':float(x.sum()),'worst_day':float(daily_g.min()),'worst_day_date':str(daily_g.idxmin()),'daily_es95':es_loss(daily_g,.95),
             'worst_1pct_hours_gross':float(np.sort(x)[:math.ceil(n*.01)].sum()),'all_negative_hours_gross':float(x[x<0].sum())}
        tail_days[str(y)]=[{'date':date,'gross_inc':float(value)} for date,value in daily_g.nsmallest(10).items()]
        for market in ['inc','dec']:
            q=np.ones(len(g))*(1 if market=='inc' else -1)
            nn,gg,cc=pnl(g,q)
            component.append({'year':int(y),'hours':len(g),'direction':market,'gross':float(gg.sum()),'net_east':float(nn.sum()),'net_regional_stress':float(pnl(g,q,scenario='regional_stress')[0].sum()),'cost_total':float(cc.sum()),
                 'admin':float((g.admin_energy+g.admin_segment).sum()),'bor_rto':float(g.bor_rto.sum()),'east':float(g.bor_east.sum()),'regional_stress':float(g.bor_regional_stress.sum()),
                 'da_or':float(g.da_or.sum()) if market=='dec' else 0.,'standalone_5invoice_net':float(pnl(g,q,invoices=5)[0].sum())})
    grid=d.groupby(['year','he']).spread.agg(['mean','count','sum']).reset_index()
    monthly=d.groupby(['year','month']).spread.agg(['mean','count','sum']).reset_index()
    out={'config':CFG,'config_sha256':hashlib.sha256((ROOT/'research_config.json').read_bytes()).hexdigest(), 'descriptive_baseline':baseline,
         'cost_components':component,'strategies':summaries,'annual':annual,'cost_sensitivity':sens,'paired_bootstrap':paired,'worst_days':tail_days,
         'year_he':grid.to_dict(orient='records'),'months':monthly.to_dict(orient='records'),'training_audit':audits, 'review_diagnostics':review_diagnostics(d,e,ledgers)}
    (OUT/'results.json').write_text(json.dumps(out,indent=2,allow_nan=False))
    # Compact auditable hourly ledger. No prices or fees are used to choose same-period positions.
    audit=[]
    for i,row in e.iterrows():
        audit.append({'utc':str(row.utc),'local':str(row.local),'pred_spread':row.pred_spread,
                      'strategies':{name:{k:float(v[i]) for k,v in ledger.items()} for name,ledger in ledgers.items()}})
    (OUT/'hourly_ledger.json').write_text(json.dumps(audit,allow_nan=False))
    make_plot(d,e,ledgers,grid)
    make_report(out)
    print(json.dumps({'strategies':summaries,'annual_net':{k:{y:round(m['net'],2) for y,m in v.items()} for k,v in annual.items()},'paired':paired},indent=2))

def make_plot(d,e,ledgers,grid):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axs=plt.subplots(2,2,figsize=(14,8.5),layout='constrained')
    colors={'Always INC':'#2563eb','Always DEC':'#9ca3af','Calendar INC filter':'#f59e0b','Calendar two-way':'#a855f7','Calendar risk-scaled':'#059669'}
    for name,c in colors.items():
        axs[0,0].plot(e.utc,np.cumsum(ledgers[name]['net']),label=name,color=c,lw=1.3)
    axs[0,0].set(title='Cost-adjusted cumulative P&L | 2023–2025',ylabel='USD, <=1 MW/hour')
    axs[0,0].axhline(0,color='#64748b',lw=.5);axs[0,0].legend(fontsize=8)
    axs[0,0].xaxis.set_major_locator(mdates.YearLocator())
    axs[0,0].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    daily=d.groupby('date').spread.sum();worst=daily.nsmallest(8).sort_values()
    axs[0,1].barh(worst.index,worst.values,color='#dc2626')
    axs[0,1].set(title='Worst gross INC days | 1 MW, 2022–2025',xlabel='USD')
    mat=grid.pivot(index='year',columns='he',values='mean')
    lim=max(abs(mat.to_numpy().min()),abs(mat.to_numpy().max()))
    im=axs[1,0].imshow(mat,aspect='auto',cmap='RdBu',vmin=-lim,vmax=lim)
    axs[1,0].set(yticks=range(4),yticklabels=mat.index,xticks=range(0,24,3),xticklabels=range(1,25,3),xlabel='Local hour ending (repeated DST hour retained)',title='DA–RT mean by year/hour | descriptive only')
    fig.colorbar(im,ax=axs[1,0],label='USD/MWh')
    for name in ['Always INC','Calendar INC filter','Calendar two-way','Calendar risk-scaled']:
        q=ledgers[name]['q'];net=ledgers[name]['net']
        costs=np.array(CFG['extra_cost_sensitivity_usd_mwh'])
        axs[1,1].plot(costs,net.sum()-costs*np.abs(q).sum(),marker='o',label=name,color=colors[name])
    axs[1,1].axhline(0,color='#64748b',lw=.7)
    axs[1,1].set(title='Additional unmodeled-cost stress | frozen positions',xlabel='Extra USD / cleared MWh',ylabel='Period P&L, USD')
    axs[1,1].legend(fontsize=8)
    fig.suptitle('PJM SpreadLab — costs, tails and incremental signal value\nPreliminary uplift + admin; RTO + East base; excludes fixed invoices in main panels',fontsize=14)
    fig.savefig(OUT/'research.png',dpi=150)
    plt.close(fig)

def make_report(r):
    b=r['descriptive_baseline'];s=r['strategies'];diag=r['review_diagnostics']
    costs={v['year']:v for v in r['cost_components'] if v['direction']=='inc'}
    inc=s['Always INC']['net'];filt=s['Calendar INC filter']['net']
    decline=costs[2023]['net_east']-costs[2025]['net_east']
    cost_rise=costs[2025]['cost_total']-costs[2023]['cost_total']
    gross_drop=costs[2023]['gross']-costs[2025]['gross']
    inf=diag['storm_influence']
    dec=diag['two_way_direction_split']['DEC'];isplit=diag['two_way_direction_split']['INC']
    lines=['# PJM SpreadLab：成本门槛、尾部风险与信号增量','',
      f'**成本：** 固定 INC 的 2023–2025 年毛收益为 ${s["Always INC"]["gross"]:,.0f}，扣已建模费用后为 ${inc:,.0f}。2023 到 2025 年收益下降中，费用增加解释 {cost_rise/decline:.1%}，毛价差收益减少解释 {gross_drop/decline:.1%}。', '',
      f'**尾部：** 2022 年最差一天 INC 毛亏损 ${-b["2022"]["worst_day"]:,.0f}；四年固定 INC 扣已建模费用后合计 ${sum(v["net_east"] for v in costs.values()):,.0f}。高小时胜率没有消除少数极端日的损失。', '',
      f'**信号：** 日历 INC 过滤器三年赚 ${filt:,.0f}，相对固定 INC 增量 ${filt-inc:,.0f}；同成交量对照的增量区间也跨零。日历信号没有证明稳定收益增量。', '',
      '研究对象：Western Hub 完整 DA–RT LMP。INC=DA−RT，DEC=RT−DA。2022 年为初始训练及风险描述，2023–2025 年为历史滚动评估，每小时最多 1 MW。主表为 RTO + East 费用基准，包含管理费和初步 operating reserve，固定账户费用另列。完整假设集中在 METHODS.md。', '',
      '## 1. 成本门槛在抬高', '',
      md_table(['年份','毛价差 $/MWh','RTO BOR $/MWh','East BOR $/MWh','管理费 $/MWh','固定 INC 毛收益 $','扣成本后 $'],
       [[y,f"{v['gross']/v['hours']:.3f}",f"{v['bor_rto']/v['hours']:.3f}",f"{v['east']/v['hours']:.3f}",f"{v['admin']/v['hours']:.3f}",f"{v['gross']:,.0f}",f"{v['net_east']:,.0f}"] for y,v in costs.items()]), '',
      f'2023→2025：已建模费用增加 ${cost_rise:,.0f}，毛收益减少 ${gross_drop:,.0f}，合计使固定 INC 收益下降 ${decline:,.0f}。主要变化来自 uplift，而非管理费。DA OR 只计入 DEC：其年均费率从 {next(v["da_or"]/v["hours"] for v in r["cost_components"] if v["year"]==2023 and v["direction"]=="dec"):.3f} 涨到 {next(v["da_or"]/v["hours"] for v in r["cost_components"] if v["year"]==2025 and v["direction"]=="dec"):.3f} $/MWh，不能拿来解释 INC 成本增加。', '',
      '区域归属已查到官方映射文件：2026-09-16 更新表把 WESTERN HUB 标为 East。基准采用 RTO + East；max(East, West) 保留作区域压力情景。该文件确认当前归属，历史连续性假设及结算限制见 METHODS.md。仅 RTO 情景省略了 East 区域费。', '',
      f'固定 INC 三年还能承受的额外成本为 ${s["Always INC"]["break_even_extra_per_mwh"]:.3f}/MWh；假设每活跃月 5 张账户发票后，收益为 ${s["Always INC"]["east_5_invoices_net"]:,.0f}。这两项比“毛收益是否为正”更接近交易门槛。', '',
      '## 2. 风险集中在尾部', '',
      md_table(['年份','小时均值','中位数','小时胜率','偏度','NW168 t','最差日','该日毛收益 $','日 ES95 $'],
       [[y,f"{v['mean']:.3f}",f"{v['median']:.2f}",f"{v['win_rate']:.1%}",f"{v['skewness']:.2f}",f"{v['nw168']['t']:.2f}",v['worst_day_date'],f"{v['worst_day']:,.0f}",f"{v['daily_es95']:,.0f}"] for y,v in b.items()]), '',
      '小时胜率约 67%–71%，但负偏和极端损失使中位数显著高于均值。2022-12-24 一天的亏损超过该年全年毛亏损。日 ES95 是最差 5% 日收益的平均损失，不是损失上限。', '',
      '## 3. 双向策略的问题在 DEC 暴露', '',
      md_table(['双向策略分项','毛收益 $','成本 $','扣成本后 $'],[[k,f"{v['gross']:,.0f}",f"{v['cost']:,.0f}",f"{v['net']:,.0f}"] for k,v in diag['two_way_direction_split'].items()]), '',
      'DEC 时段按出现频率排列：'+', '.join(f'HE{k}: {v} 小时' for k,v in list(diag['dec_he_counts'].items())[:5])+f'。其中第四季度占 {diag["dec_q4_fraction"]:.1%}。HE 定义为本地小时起点+1，秋季重复小时保留。', '',
      f'为检验 Elliott 时段对均值的影响，增加一次**事后训练影响诊断**：只从训练中移除 2022-12-23/24，保留全部评估结果。原策略的 {inf["original_dec_hours"]:,} 个 DEC 小时中，{inf["original_dec_hours_no_longer_dec"]:,} 个（{inf["fraction_original_dec_changed"]:.1%}）不再选择 DEC。这衡量训练样本影响，不是能事前删除风暴的交易策略。', '',
      '本轮没有改用中位数或截尾均值，也没有据此重选规则。中位数估计典型小时，未必估计期望交易收益；截尾会改变尾部损失的权重。如后续测试，必须列为事后变体，并保留原始收益和尾部亏损评价。', '',
      f'手续费不是主要解释：同成交量固定 INC 对照额外支付的提交段费约 ${diag["equal_volume_control_extra_segment_fees"]:,.0f}。风险缩仓策略的活跃仓位中位数为 {diag["risk_scaled_active_median_mw"]:.3f} MW，其毛收益为 ${s["Calendar risk-scaled"]["gross"]:,.0f}；不能把表现差归因于提交段费。', '',
      '## 4. 信号的收益与风险增量', '',
      '规则固定：日历均值按小时×周末×季度分组并收缩；每月用至少滞后 60 天的标签重新训练。INC 过滤器只做预期收益覆盖成本的 INC；双向版本允许 DEC；风险版本对双向仓位按历史 ES99 缩放。', '',
      md_table(['策略','交易 MWh','毛收益 $','成本 $','扣成本后 $','最大回撤 $','最差日 $','日 ES95 $'],
       [[name,f"{v['mwh']:,.0f}",f"{v['gross']:,.0f}",f"{v['cost']:,.0f}",f"{v['net']:,.0f}",f"{v['mdd']:,.0f}",f"{v['worst_day']:,.0f}",f"{v['daily_es95']:,.0f}"] for name,v in s.items()]), '',
      md_table(['策略','2023 $','2024 $','2025 $','每月5张发票后 $','区域压力情景/同发票假设 $'],
       [[name]+[f"{r['annual'][name][y]['net']:,.0f}" for y in ['2023','2024','2025']]+[f"{v['east_5_invoices_net']:,.0f}",f"{v['regional_stress_5_invoices_net']:,.0f}"] for name,v in s.items()]), '',
      f'INC 过滤器最大回撤比固定 INC 少 {1-s["Calendar INC filter"]["mdd"]/s["Always INC"]["mdd"]:.1%}，但交易量也少 {1-s["Calendar INC filter"]["mwh"]/s["Always INC"]["mwh"]:.1%}。同成交量对照用于区分缩小暴露与择时。', '',
      md_table(['信号','对照','总增量 $','95% 配对分块 bootstrap 区间 $'],
       [[name,comp,f"{v['increment_total']:,.0f}",f"[{v['ci95_period_total'][0]:,.0f}, {v['ci95_period_total'][1]:,.0f}]"] for name,comparisons in r['paired_bootstrap'].items() for comp,v in comparisons.items()]), '',
      '### 额外成本敏感性：仓位固定', '',
      md_table(['策略']+[f'+${c}/MWh' for c in CFG['extra_cost_sensitivity_usd_mwh']],
       [[name]+[f"{v['net']:,.0f}" for v in r['cost_sensitivity'] if v['strategy']==name] for name in s]), '',
      '## 5. 研究判断与复现', '',
      '成本上升和尾部暴露已经得到量化；当前日历信号没有证明稳定 alpha。下一阶段应增加具有发布时间记录的负荷、风光和天气预测，并用冻结规则后的新数据检验。', '',
      '本报告使用初步费率、当前结算版本和历史滚动检验，不代表最终账单净利润。完整成本口径、历史区域归属假设、标签版本可得性、执行约束和统计限制集中在 METHODS.md。', '',
      '复现：python research.py；独立核验：python validate_research.py。完整数值与训练截止见 outputs/results.json；逐小时预测、仓位、收支见 outputs/hourly_ledger.json。v1_results.json 与 research_config_v1.json 保留原区域压力版本。', '',
      '官方来源：', '',
      '- https://dataminer2.pjm.com/feed/rt_da_monthly_lmps/definition',
      '- https://dataminer2.pjm.com/feed/sched_9_10_rates/definition',
      '- https://dataminer2.pjm.com/feed/prelim_or_rates/definition',
      '- https://www.pjm.com/-/media/DotCom/markets-ops/energy/op-reserves/bor-hubs-zones-interfaces-aggregates-posting.xlsx （2026-09-16，WESTERN HUB=East）',
      '- https://www.pjm.com/-/media/DotCom/documents/manuals/archive/m28/m28v93-operating-agreement-accounting-09-21-2023.pdf',
      '- https://www.pjm.com/-/media/DotCom/documents/manuals/m27.pdf', '']
    text='\n'.join(lines)
    (OUT/'REPORT_zh.md').write_text(text)
    # HTML with self-contained chart; readable offline, no remote resources.
    import html, re
    def inline(p):
        return re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',html.escape(p))
    blocks=[]
    paras=text.split('\n\n')
    for p in paras:
        if p.startswith('|'):
            rows=p.splitlines(); cells=[[c.strip() for c in row.strip('|').split('|')] for row in rows]
            blocks.append('<div class="table"><table><thead><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in cells[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in row)+'</tr>' for row in cells[2:])+'</tbody></table></div>')
        elif p.startswith('#'):
            level=len(p)-len(p.lstrip('#'));blocks.append(f'<h{level}>'+html.escape(p[level:].strip())+f'</h{level}>')
        else: blocks.append('<p>'+inline(p).replace('\n','<br>')+'</p>')
    image=base64.b64encode((OUT/'research.png').read_bytes()).decode()
    body=''.join(blocks)
    chart=f'<img alt="PJM cost, tail risk and strategy comparison" src="data:image/png;base64,{image}">'
    body=body.replace('</h1>','</h1>'+chart,1)
    (OUT/'PJM_Cost_Risk_Signals.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PJM SpreadLab</title><style>body{max-width:1200px;margin:40px auto;padding:0 24px;color:#172033;background:#f8fafc;font:16px/1.8 system-ui,sans-serif}h1,h2,h3{line-height:1.35;color:#0f172a}h2{margin-top:40px}img{width:100%;background:white;border-radius:12px}.table{overflow:auto;margin:18px 0}table{border-collapse:collapse;white-space:nowrap;font-size:13px;width:100%;background:white}th,td{text-align:right;padding:9px 12px;border-bottom:1px solid #e2e8f0}th{background:#e2e8f0}th:first-child,td:first-child{text-align:left}p{max-width:1000px}a{color:#2563eb}</style>'+body+'</html>')

if __name__=='__main__':main()
