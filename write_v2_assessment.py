"""Presentation-only interpretation of saved one-shot outcomes; does not fit/evaluate models."""
import json
import signal_v2 as V
r=json.loads((V.OUT/'signal_v2_results.json').read_text())
V.report(r)  # regenerate presentation only, keeping this script idempotent
p=r['strategies']['Load absolute INC'];b=r['strategies']['Always INC'];s=r['strategies']['Load squared INC'];volume=r['paired_primary_increment']['Equal-volume INC']
summary=f'**研究判断：** v2 没有找到可部署的盈利信号。主策略亏 ${-p["net"]:,.0f}；相对固定 INC 少亏 ${p["net"]-b["net"]:,.0f}，但相对同成交总量的均匀 INC 增量为 ${volume["increment_total"]:,.0f}，区间跨零。平方损失 INC 对照仅亏 ${-s["net"]:,.0f}，本次不支持“绝对损失优于平方损失”的推断。'
assessment=['## 对一次评估结果的解释','',summary,'',
 f'主策略交易量比固定 INC 少 {1-p["mwh"]/b["mwh"]:.1%}。相同成交总量对照的增量 95% 区间为 [${volume["ci95_period_total"][0]:,.0f}, ${volume["ci95_period_total"][1]:,.0f}]，未显示稳定择时增量。相对未缩仓 INC 的小额正增量不足以证明 alpha。','',
 f'固定 INC 毛收益 ${b["gross"]:,.0f}，已建模费用 ${b["cost"]:,.0f}，平均费用 ${b["cost"]/b["mwh"]:.2f}/MWh。主策略毛收益 ${p["gross"]:,.0f}，费用 ${p["cost"]:,.0f}。这轮的费用压力不能由正的毛价差抵消。','',
 '绝对损失的中位数目标可能保留大量“多数小时获利、少数小时大亏”的头寸。改变损失函数不是风险管理的替代品；平方损失估计条件均值的目标本身并没有错。这个结果仅适用于已冻结的几种规则，不证明所有稳健模型都无效。','',
 '2026 数据在本次评估后已经被查看，后续改规则必须列为事后变体；不能再将同一段数据当作未见测试。未更改本次配置、模型或门槛。']
(V.OUT/'V2_ASSESSMENT_zh.md').write_text('\n'.join(assessment))
path=V.OUT/'SIGNAL_V2_2026_zh.md';text=path.read_text();text=text.replace('\n\n','\n\n'+summary+'\n\n',1);text+='\n\n'+'\n'.join(assessment)
path.write_text(text)
V.render_html(text,V.OUT/'signal_v2.png',V.OUT/'PJM_2026_Frozen_Evaluation.html')
print('Saved interpretation from existing numerical results; no refits.')
