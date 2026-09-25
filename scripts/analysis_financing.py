"""分析二：企业融资（尤其长久期发债）与美债利率。

输出：
- figures/fin_*.png
- output/financing_results.md
"""
import numpy as np
import pandas as pd

from common import (C1, C2, C3, INK2, OUT, fmt_coef, load_d, load_m, load_q, ols_nw, plt, save, to_ts)

q = load_q()
m = load_m()
d = load_d()
lines = ["# 分析二结果：企业融资与美债利率（脚本自动生成）\n"]

# 年化流量/GDP 取四季度均值
q["capex4"] = (q["nfc_capex_gdp"]).rolling(4).mean()
q["gap4"] = q["nfc_financing_gap_gdp"].rolling(4).mean()
q["internal4"] = q["capex4"] - q["gap4"]
q["bond4"] = q["nfc_bond_flow_gdp"].rolling(4).mean()
q["loan4"] = q["nfc_loan_flow_gdp"].rolling(4).mean()
q["ust4"] = q["ust_flow_gdp"].rolling(4).mean()
for c in ["acm_tp10", "GS10", "FEDFUNDS", "infl_yoy", "acm_rn10", "real10_ex_post"]:
    q["d4_" + c] = q[c].diff(4)

# ---------- 1. 融资缺口：企业部门何时需要外部融资 ----------
yr = q.groupby(q.index.year)[["capex4", "internal4", "gap4", "bond4", "ust4", "GS10",
                               "real10_ex_post", "acm_tp10"]].mean()
sel = [1960, 1970, 1980, 1990, 1999, 2000, 2004, 2006, 2010, 2015, 2019, 2021, 2023, 2024, 2025]
last = q["gap4"].last_valid_index()
tbl = yr.loc[sel].copy()
tbl.loc[f"{last}（最新）"] = q.loc[last, tbl.columns]
tbl.columns = ["资本开支/GDP", "内部资金/GDP", "融资缺口/GDP", "公司债净发行/GDP", "美债净发行/GDP",
               "10Y", "10Y实际利率", "ACM期限溢价"]
lines += ["## 1. 非金融企业融资缺口（%，年均；融资缺口 = 资本开支 − 内部资金）\n",
          "来源：美联储 Z.1 表 S.11.1（FA105050005、FA105005305、FA103163005），FA313161105。\n",
          tbl.to_markdown(floatfmt=".2f"), "\n"]
g = q.loc["1985":, ["gap4", "real10_ex_post", "acm_tp10", "GS10"]].dropna()
lines += [f"1985 年以来融资缺口/GDP 与 10Y 实际利率相关系数 {g['gap4'].corr(g['real10_ex_post']):.2f}，"
          f"与 ACM 期限溢价 {g['gap4'].corr(g['acm_tp10']):.2f}，与 10Y 名义利率 {g['gap4'].corr(g['GS10']):.2f}。\n"]

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.4), sharex=True)
qq = q.loc["1952":]
x = to_ts(qq.index)
a1.plot(x, qq["capex4"], color=C1, label="资本开支/GDP")
a1.plot(x, qq["internal4"], color=C3, label="内部资金/GDP")
a1.fill_between(x, qq["internal4"], qq["capex4"], where=qq["capex4"] > qq["internal4"],
                color=C1, alpha=0.15, lw=0, label="融资缺口（需外部融资）")
a1.set_ylabel("%"); a1.set_ylim(5.5, 13); a1.legend(loc="upper left", ncol=3)
a1.set_title("2000 年代以来企业内部资金多数时间覆盖资本开支，外部融资需求较 1970—90 年代收缩")
a2.plot(x, qq["GS10"], color=C1, label="10年期美债收益率")
a2.plot(x, qq["real10_ex_post"], color=C2, label="10年期实际利率")
a2.axhline(0, color=INK2, lw=0.8); a2.set_ylabel("%"); a2.legend(loc="upper right")
save(fig, "fin_01_financing_gap", "美联储 Z.1（S.11.1），FRED；四季度移动平均")

# ---------- 2. 流量回归：公司债 vs 美债净供给 ----------
lines += ["## 2. 回归：净发行（占 GDP，四季度均值）每上升 1 个点，利率四季度变化（bp）\n",
          "控制变量：联邦基金利率四季度变化、通胀四季度变化；Newey-West(4)。\n"]
deps = [("d4_GS10", "10年期美债收益率"), ("d4_acm_rn10", "预期短端利率"), ("d4_acm_tp10", "期限溢价")]
eras = [("1962", "2026", "1962—2026"), ("1962", "1999", "1962—1999"), ("2000", "2026", "2000—2026")]
rows, plot = [], {}
for y, lab in deps:
    for s0, s1, en in eras:
        res, a, b, n = ols_nw(q.loc[s0:s1, y], q.loc[s0:s1, ["bond4", "ust4", "d4_FEDFUNDS", "d4_infl_yoy"]])
        rows.append({"因变量": lab, "样本": en, "公司债净发行": fmt_coef(res, "bond4", 100),
                     "美债净发行": fmt_coef(res, "ust4", 100), "N": n})
        if en == "1962—2026":
            plot[lab] = res
lines += [pd.DataFrame(rows).to_markdown(index=False), "\n",
          "解读提示：公司债发行对利率具有择时性（利率低时多发），流量回归同时包含供给效应与反向因果，系数为负不代表供给压低利率。\n"]

fig, ax = plt.subplots(figsize=(8.5, 4.2))
labs = list(plot)
yy = np.arange(len(labs))[::-1]
for off, var, c, nm in [(0.15, "bond4", C1, "公司债净发行"), (-0.15, "ust4", C2, "美债净发行")]:
    b = np.array([plot[k].params[var] * 100 for k in labs]); se = np.array([plot[k].bse[var] * 100 for k in labs])
    ax.errorbar(b, yy + off, xerr=1.96 * se, fmt="o", color=c, ecolor=c, elinewidth=2, ms=7, label=nm)
    for y0, bb in zip(yy + off, b):
        ax.annotate(f"{bb:+.1f}", (bb, y0), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
ax.axvline(0, color=INK2, lw=0.8)
ax.set_yticks(yy, labs)
ax.set_xlabel("净发行占 GDP 每上升 1 个点，对应利率四季度变化（bp，95% 置信区间）")
ax.set_title("季度流量数据中，公司债净发行对长端利率的推升效应不可识别")
ax.legend(loc="lower left")
save(fig, "fin_02_supply_regression", "美联储 Z.1，纽约联储 ACM；1962—2026 季度回归")

# ---------- 3. 存量：企业债与美债此消彼长？ ----------
q["bond_share"] = q["nfc_bond_level"] / (q["nfc_bond_level"] + q["nfc_loan_level"]) * 100
q["d4_bondlv"] = q["nfc_bond_level_gdp"].diff(4)
q["d4_ustlv"] = q["ust_level_gdp"].diff(4)
lines += ["## 3. 存量关系：美债/GDP 与非金融企业公司债/GDP\n"]
rows = []
for s0, s1 in [("1952", "1984"), ("1985", "2007"), ("2008", "2026"), ("1952", "2026")]:
    dd = q.loc[s0:s1, ["nfc_bond_level_gdp", "ust_level_gdp", "bond_share", "d4_bondlv", "d4_ustlv"]].dropna()
    res, *_ = ols_nw(dd["d4_bondlv"], dd[["d4_ustlv"]], 8)
    rows.append({"样本": f"{s0}—{s1}",
                 "水平相关：公司债/GDP vs 美债/GDP": round(dd["nfc_bond_level_gdp"].corr(dd["ust_level_gdp"]), 2),
                 "水平相关：债券占企业债务比重 vs 美债/GDP": round(dd["bond_share"].corr(dd["ust_level_gdp"]), 2),
                 "变化回归：Δ4公司债/GDP 对 Δ4美债/GDP": fmt_coef(res, "d4_ustlv", 1, 3)})
lines += [pd.DataFrame(rows).to_markdown(index=False), "\n"]

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
qq = q.loc["1952":]
x = to_ts(qq.index)
a1.plot(x, qq["ust_level_gdp"], color=C2, label="可流通美债/GDP")
a1.plot(x, qq["nfc_bond_level_gdp"], color=C1, label="非金融企业公司债/GDP")
a1.set_ylabel("%"); a1.legend(loc="upper left")
a1.set_title("1952—1984 年美债/GDP 持续下行，企业债/GDP 小幅抬升；2008 年后两者同步扩张")
a2.plot(x, qq["bond_share"], color=C1, label="公司债占非金融企业债务（债券+贷款）比重")
a2.set_ylabel("%"); a2.legend(loc="upper left")
save(fig, "fin_03_stocks", "美联储 Z.1（L.103 / S.11.1，F.3.2）")

# ---------- 4. 避险：信用利差与美债收益率 ----------
m["qual_spread"] = m["BAA"] - m["AAA"]
dm = m[["GS10", "qual_spread"]].diff().dropna()
rc = dm["GS10"].rolling(60).corr(dm["qual_spread"])
pick = [rc.loc[:f"{y}-12"].index[-1] for y in range(1958, 2026, 5)] + [rc.index[-1]]
tbl = rc.loc[pick]
tbl.index = [f"{t:%Y-%m}" for t in tbl.index]
lines += ["## 4. 滚动 60 个月相关：Δ10Y 与 Δ(Baa−Aaa)\n",
          "用同为企业债的 Baa−Aaa 利差，避免 Baa−10Y 利差与 10Y 之间的机械负相关。\n",
          tbl.round(2).to_frame("相关系数").T.to_markdown(), "\n",
          f"全样本（{dm.index.min():%Y-%m}—{dm.index.max():%Y-%m}）相关系数：{dm.corr().iloc[0, 1]:.2f}\n"]
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(rc.index, rc, color=C1)
ax.axhline(0, color=INK2, lw=0.8)
ax.set_ylabel("相关系数")
ax.set_title("信用利差走阔时美债收益率倾向下行，但这一避险关系强弱随时期变化")
save(fig, "fin_04_flight_to_quality", "穆迪，FRED；月度变化的 60 个月滚动相关")

# ---------- 5. 事件研究：超大额企业发债 ----------
# 定价日期来自公开报道，均需逐笔核验
deals = [
    ("2013-04-30", "Apple", 17), ("2013-09-11", "Verizon", 49), ("2015-03-03", "Actavis", 21),
    ("2016-01-13", "AB InBev", 46), ("2018-03-06", "CVS", 40), ("2019-11-12", "AbbVie", 30),
    ("2020-03-30", "Oracle", 20), ("2020-04-30", "Boeing", 25), ("2023-02-22", "Amgen", 24),
    ("2023-05-16", "Pfizer", 31), ("2025-09-24", "Oracle", 18), ("2025-10-30", "Meta", 30),
    ("2025-11-03", "Alphabet", 17.5), ("2025-11-17", "Amazon", 15),
]
dd = d[["DGS10", "DGS30"]].dropna()
dd["S"] = dd["DGS30"] - dd["DGS10"]
W = 3
base = (dd.shift(-W) - dd.shift(W + 1)).dropna() * 100  # [t-3, t+3] 窗口变化，bp
base = base.loc["2010":]
rows = []
for dt, nm, sz in deals:
    t = dd.index[dd.index.searchsorted(pd.Timestamp(dt))]
    i = dd.index.get_loc(t)
    if i + W >= len(dd):
        continue
    ch = (dd.iloc[i + W] - dd.iloc[i - W - 1]) * 100
    rows.append({"定价日（待核验）": dt, "发行人": nm, "规模(亿美元)": int(sz * 10),
                 "10Y(bp)": ch["DGS10"], "30Y(bp)": ch["DGS30"], "30Y−10Y(bp)": ch["S"],
                 "30Y 变化分位": (base["DGS30"] < ch["DGS30"]).mean() * 100})
ev = pd.DataFrame(rows)
avg = ev[["10Y(bp)", "30Y(bp)", "30Y−10Y(bp)"]].mean()
n = len(ev)
tstat = {c: avg[c] / (base[k].std() / np.sqrt(n)) for c, k in
         [("10Y(bp)", "DGS10"), ("30Y(bp)", "DGS30"), ("30Y−10Y(bp)", "S")]}
lines += [f"## 5. 事件研究：单笔 ≥150 亿美元企业发债，定价日前 3 至后 3 个交易日利率变化\n",
          "“30Y 变化分位”为该窗口变化在 2010 年以来全部 7 日窗口中的分位数。\n",
          ev.to_markdown(index=False, floatfmt=".0f"), "\n",
          f"平均：10Y {avg['10Y(bp)']:+.1f}bp（t={tstat['10Y(bp)']:.2f}），30Y {avg['30Y(bp)']:+.1f}bp（t={tstat['30Y(bp)']:.2f}），"
          f"30Y−10Y {avg['30Y−10Y(bp)']:+.1f}bp（t={tstat['30Y−10Y(bp)']:.2f}）；"
          f"2010 年以来全部 7 日窗口 30Y 变化均值 {base['DGS30'].mean():+.1f}bp，标准差 {base['DGS30'].std():.1f}bp。"
          "t 值以全样本窗口标准差近似，未扣除重叠窗口影响。\n"]

fig, ax = plt.subplots(figsize=(10, 4.6))
xi = np.arange(n)
sd = base["DGS30"].std()
ax.axhspan(-sd, sd, color=C3, alpha=0.12, lw=0, label=f"2010 年以来 7 日窗口 ±1 倍标准差（{sd:.0f}bp）")
ax.bar(xi, ev["30Y(bp)"], 0.6, color=C1, label="30年期美债收益率变化")
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(xi, [f"{r['发行人']}\n{r['定价日（待核验）'][:7]}" for _, r in ev.iterrows()], fontsize=8)
ax.set_ylabel("bp")
ax.set_title("超大额企业发债前后，30 年期美债收益率变化多落在正常波动区间内")
ax.legend(loc="lower left")
save(fig, "fin_05_event_study", "FRED（DGS10、DGS30），公开报道整理的发行日期（待核验）")

(OUT / "financing_results.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
