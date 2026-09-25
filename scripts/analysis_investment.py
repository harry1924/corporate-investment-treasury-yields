"""分析一：企业投资与美债利率。

输出：
- figures/inv_*.png
- output/investment_results.md（数字结果，供报告引用）
"""
import numpy as np
import pandas as pd

from common import (C1, C2, C3, INK2, SHADE, OUT, fmt_coef, load_q, ols_nw, plt, save, stars, to_ts)

q = load_q()
q["inv_g"] = q["real_nonres_qoq_saar"].rolling(4).mean()  # 实际非住宅投资同比（近似）
q["share_ma"] = q["nonres_share"].rolling(4).mean()
for c in ["GS10", "FEDFUNDS", "acm_rn10", "acm_tp10", "real10_ex_post", "infl_yoy"]:
    q["d4_" + c] = q[c].diff(4)

lines = ["# 分析一结果：企业投资与美债利率（脚本自动生成）\n"]


# ---------- 1. 投资周期划分 ----------
def zigzag(s: pd.Series, th: float):
    pts, direction = [], 0
    ext_i, ext_v = s.index[0], s.iloc[0]
    for i, v in s.items():
        if direction >= 0:
            if v > ext_v:
                ext_i, ext_v = i, v
            elif ext_v - v >= th:
                pts.append((ext_i, "peak")); direction = -1; ext_i, ext_v = i, v
        else:
            if v < ext_v:
                ext_i, ext_v = i, v
            elif v - ext_v >= th:
                pts.append((ext_i, "trough")); direction = 1; ext_i, ext_v = i, v
    return pts


s = q["share_ma"].dropna()
pts = zigzag(s, 0.8)
ups = [(a, b) for (a, ta), (b, tb) in zip(pts, pts[1:]) if ta == "trough" and tb == "peak"]
if pts[-1][1] == "trough":  # 当前仍处上行段
    ups.append((pts[-1][0], s.index[-1]))

rows = []
for a, b in ups:
    a2 = max(a, pd.Period("1961Q3", "Q"))  # ACM 起点
    r = {"阶段": f"{a}—{b}", "投资占GDP变化(个点)": s[b] - s[a],
         "10Y变化(bp)": (q.at[b, "GS10"] - q.at[a, "GS10"]) * 100,
         "联邦基金利率变化(bp)": (q.at[b, "FEDFUNDS"] - q.at[a, "FEDFUNDS"]) * 100,
         "10Y实际利率变化(bp)": (q.at[b, "real10_ex_post"] - q.at[a, "real10_ex_post"]) * 100,
         "预期短端利率变化(bp)": (q.at[b, "acm_rn10"] - q.at[a2, "acm_rn10"]) * 100,
         "期限溢价变化(bp)": (q.at[b, "acm_tp10"] - q.at[a2, "acm_tp10"]) * 100}
    rows.append(r)
ep = pd.DataFrame(rows).set_index("阶段")
lines += ["## 1. 投资上行周期（非住宅投资/GDP 四季度均值，拐点阈值 0.8 个点）\n",
          "ACM 分解在 1961Q3 之前无数据，首段起点取 1961Q3。\n", ep.to_markdown(floatfmt=(".0f", ".1f", ".0f", ".0f", ".0f", ".0f", ".0f")), "\n"]

# 图1：投资占比（右轴）与利率（左轴）
fig, ax = plt.subplots(figsize=(11, 5.2))
for a, b in ups:
    ax.axvspan(a.to_timestamp(), b.to_timestamp(how="end"), color=SHADE, lw=0, zorder=0)
qq = q.loc["1953Q2":]
x = to_ts(qq.index)
l1, = ax.plot(x, qq["GS10"], color=C1, label="10年期美债收益率（左轴）")
l2, = ax.plot(x, qq["real10_ex_post"], color=C2, label="10年期实际利率，减核心通胀（左轴）")
ax.axhline(0, color=INK2, lw=0.8)
ax.set_ylabel("利率（%）")
ax.set_ylim(-4, 17)
axr = ax.twinx()
l3, = axr.plot(x, qq["nonres_share"], color=C3, lw=2.4, label="非住宅固定投资/GDP（右轴）")
axr.set_ylabel("投资/GDP（%）")
axr.set_ylim(6, 16.5)
axr.grid(False)
axr.spines["right"].set_visible(True)
ax.set_title("投资上行期多伴随利率上行，但 2010 年后的投资扩张未能扭转利率下行趋势")
ax.legend(handles=[l3, l1, l2], loc="upper left", ncol=3, fontsize=9)
ax.text(0.99, 0.90, "阴影：投资占比上行阶段", transform=ax.transAxes, ha="right", va="top", fontsize=8, color=INK2)
save(fig, "inv_01_share_vs_yields", "BEA，美联储，FRED")

# 图2：各投资上行期的利率分解
e2 = ep.dropna(subset=["预期短端利率变化(bp)"])
x = np.arange(len(e2))
fig, ax = plt.subplots(figsize=(10, 4.6))
ax.bar(x - 0.2, e2["预期短端利率变化(bp)"], 0.38, color=C1, label="预期短端利率（ACM 风险中性收益率）")
ax.bar(x + 0.2, e2["期限溢价变化(bp)"], 0.38, color=C2, label="期限溢价（ACM）")
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(x, [i.replace("—", "\n—") for i in e2.index], fontsize=9)
ax.set_ylabel("bp")
ax.set_title("投资上行期预期短端利率普遍抬升，期限溢价方向不定")
ax.legend(loc="upper right")
save(fig, "inv_02_episode_decomposition", "纽约联储 ACM 模型，BEA")

# ---------- 2. 回归：投资增速对利率各分项 ----------
lines += ["## 2. 回归：实际非住宅投资同比每上升 1 个点，利率四季度变化（bp）\n",
          "控制变量：核心通胀四季度变化、失业率缺口（失业率 − CBO 自然失业率）；Newey-West(4) 标准误。"
          "实际利率一行不控制通胀变化（其定义已扣除通胀）。*** / ** / * 分别为 1% / 5% / 10% 显著。\n"]
deps = [("d4_FEDFUNDS", "联邦基金利率"), ("d4_GS10", "10年期美债收益率"), ("d4_acm_rn10", "其中：预期短端利率"),
        ("d4_acm_tp10", "其中：期限溢价"), ("d4_real10_ex_post", "10年期实际利率")]
eras = [("1955Q1", "2026Q2", "全样本"), ("1962Q1", "1984Q4", "1962—1984"),
        ("1985Q1", "2007Q4", "1985—2007"), ("2008Q1", "2026Q2", "2008—2026")]
tab, full = {}, {}
for y, lab in deps:
    ctr = ["inv_g", "unemp_gap"] + ([] if y == "d4_real10_ex_post" else ["d4_infl_yoy"])
    row = {}
    for s0, s1, en in eras:
        res, a, b, n = ols_nw(q.loc[s0:s1, y], q.loc[s0:s1, ctr])
        row[en] = fmt_coef(res, "inv_g", 100)
        if en == "全样本":
            full[lab] = (res.params["inv_g"] * 100, res.bse["inv_g"] * 100, a, b, n)
    tab[lab] = row
reg = pd.DataFrame(tab).T
lines += [reg.to_markdown(), "\n",
          "全样本区间：" + "；".join(f"{k} {v[2]}—{v[3]}（N={v[4]}）" for k, v in full.items()), "\n"]

# 图3：系数与 95% 置信区间
fig, ax = plt.subplots(figsize=(8.5, 4.2))
labs = list(full)
b = np.array([full[k][0] for k in labs]); se = np.array([full[k][1] for k in labs])
ypos = np.arange(len(labs))[::-1]
ax.errorbar(b, ypos, xerr=1.96 * se, fmt="o", color=C1, ecolor=C1, elinewidth=2, capsize=0, ms=8)
for yy, bb in zip(ypos, b):
    ax.annotate(f"{bb:+.1f}", (bb, yy), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=9)
ax.axvline(0, color=INK2, lw=0.8)
ax.set_yticks(ypos, labs)
ax.set_xlabel("实际非住宅投资同比每上升 1 个点，对应利率四季度变化（bp，95% 置信区间）")
ax.set_title("投资提速主要推升政策利率，对期限溢价的影响为负")
save(fig, "inv_03_regression_coefs", "BEA，美联储，纽约联储 ACM，CBO；1955Q1—2026Q2 季度回归")

# ---------- 3. 领先滞后 ----------
ks = range(-8, 9)
cc = pd.DataFrame({
    "联邦基金利率": [q["inv_g"].corr(q["d4_FEDFUNDS"].shift(-k)) for k in ks],
    "10年期美债收益率": [q["inv_g"].corr(q["d4_GS10"].shift(-k)) for k in ks],
    "期限溢价（ACM）": [q["inv_g"].corr(q["d4_acm_tp10"].shift(-k)) for k in ks]}, index=list(ks))
lines += ["## 3. 领先滞后：投资同比（t）与利率四季度变化（t+k）的相关系数\n",
          "k>0 表示利率变化滞后于投资。\n", cc.round(2).to_markdown(), "\n"]
fig, ax = plt.subplots(figsize=(9, 4.2))
for col, c in zip(cc, [C1, C2, C3]):
    ax.plot(cc.index, cc[col], color=c, marker="o", ms=5, label=col)
ax.axhline(0, color=INK2, lw=0.8); ax.axvline(0, color=INK2, lw=0.8, ls=":")
ax.set_xlabel("k（季度；k>0 为利率变化滞后于投资）"); ax.set_ylabel("相关系数")
ax.set_title("投资增速与政策利率同步变化，对长端利率的领先性较弱")
ax.legend(loc="upper left")
save(fig, "inv_04_lead_lag", "BEA，美联储，纽约联储 ACM")

# ---------- 4. 结构：无形资产投资与 r* ----------
lv = q[["nonres_share", "info_share", "ipp_share", "hlw_rstar", "real10_ex_post", "acm_tp10"]].dropna()
corr = lv.corr().loc[["nonres_share", "info_share", "ipp_share"], ["hlw_rstar", "real10_ex_post", "acm_tp10"]]
corr.index = ["非住宅投资/GDP", "信息处理设备与软件/GDP", "知识产权产品/GDP"]
corr.columns = ["HLW r*", "10Y 实际利率", "ACM 期限溢价"]
lines += [f"## 4. 水平相关（{lv.index.min()}—{lv.index.max()}，季度）\n",
          "水平序列存在共同趋势，相关系数仅作描述，不作因果解读。\n", corr.round(2).to_markdown(), "\n"]

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
qq = q.loc["1961Q1":]
a1.plot(to_ts(qq.index), qq["ipp_share"], color=C1, label="知识产权产品投资/GDP")
a1.plot(to_ts(qq.index), qq["info_share"], color=C3, label="信息处理设备与软件/GDP")
a1.set_ylabel("%"); a1.legend(loc="upper left")
a1.set_title("投资结构转向无形资产的同时，中性利率趋势下行")
a2.plot(to_ts(qq.index), qq["hlw_rstar"], color=C2, label="HLW 中性利率 r*")
a2.axhline(0, color=INK2, lw=0.8); a2.set_ylabel("%"); a2.legend(loc="upper right")
save(fig, "inv_05_intangibles_rstar", "BEA，纽约联储 HLW 模型")

# ---------- 4b. 有形投资（建筑 + 设备）与利率 ----------
tg = q.loc["1953Q2":].copy()
for c in ["tangible_share", "ipp_share", "GS10", "real10_ex_post", "acm_tp10", "FEDFUNDS"]:
    tg["d4_" + c] = tg[c].diff(4)
rates = [("GS10", "10年期名义利率"), ("real10_ex_post", "10年期实际利率"), ("acm_tp10", "ACM 期限溢价"),
         ("FEDFUNDS", "联邦基金利率")]
eras3 = [("1953", "1984", "1953—1984"), ("1985", "2007", "1985—2007"), ("2008", "2026", "2008—2026"),
         ("1953", "2026", "全样本")]
for xv, xn in [("tangible_share", "有形投资（建筑+设备）/GDP"), ("ipp_share", "知识产权产品投资/GDP")]:
    rows = []
    for s0, s1, en in eras3:
        dd = tg.loc[s0:s1]
        r = {"样本": en}
        for yv, yn in rates:
            r[f"水平：{yn}"] = dd[xv].corr(dd[yv])
            r[f"四季度变化：{yn}"] = dd["d4_" + xv].corr(dd["d4_" + yv])
        rows.append(r)
    lines += [f"## 4b. {xn} 与利率的相关系数\n", pd.DataFrame(rows).round(2).to_markdown(index=False), "\n"]
last_t = tg["tangible_share"].last_valid_index()
lines += [f"有形投资/GDP：1981Q4 {tg.at[pd.Period('1981Q4', 'Q'), 'tangible_share']:.2f}%，"
          f"2000Q4 {tg.at[pd.Period('2000Q4', 'Q'), 'tangible_share']:.2f}%，"
          f"2019Q3 {tg.at[pd.Period('2019Q3', 'Q'), 'tangible_share']:.2f}%，"
          f"{last_t} {tg.at[last_t, 'tangible_share']:.2f}%"
          f"（建筑 {tg.at[last_t, 'structures_share']:.2f}%，设备 {tg.at[last_t, 'equipment_share']:.2f}%）。\n"]

# 图6：有形投资（右轴）分别对照实际利率、名义利率、期限溢价（左轴）
fig, axes = plt.subplots(3, 1, figsize=(11, 10.5), sharex=True)
x = to_ts(tg.index)
panels = [("GS10", "10年期美债收益率", C1, (0, 16)),
          ("real10_ex_post", "10年期实际利率（减核心通胀）", C2, (-4, 10)),
          ("acm_tp10", "ACM 10年期期限溢价", C1, (-2, 5.5))]
for ax, (yv, yn, col, yl) in zip(axes, panels):
    la, = ax.plot(x, tg[yv], color=col, label=f"{yn}（左轴）")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_ylim(*yl); ax.set_ylabel("%")
    axr = ax.twinx()
    lb, = axr.plot(x, tg["tangible_share"], color=C3, lw=2.4, label="有形投资（建筑+设备）/GDP（右轴）")
    axr.set_ylim(6, 14.5); axr.set_ylabel("投资/GDP（%）"); axr.grid(False)
    axr.spines["right"].set_visible(True)
    ax.legend(handles=[lb, la], loc="upper left", ncol=2, fontsize=9)
axes[0].set_title("有形投资与名义利率长期同向，2008 年后联动减弱")
save(fig, "inv_06_tangible_vs_rates", "BEA，美联储，纽约联储 ACM；有形投资 = 非住宅建筑 + 设备")

# 图7：散点（水平），按时期着色
fig, axes = plt.subplots(1, 3, figsize=(13, 4.6))
cols = [C1, C2, C3]
for ax, (yv, yn, _, _) in zip(axes, panels):
    for (s0, s1, en), c in zip(eras3[:3], cols):
        dd = tg.loc[s0:s1, ["tangible_share", yv]].dropna()
        ax.scatter(dd["tangible_share"], dd[yv], s=14, color=c, alpha=0.75, edgecolors="none",
                   label=f"{en}（r={dd.corr().iloc[0, 1]:.2f}）")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xlabel("有形投资/GDP（%）"); ax.set_ylabel(f"{yn}（%）")
    ax.legend(loc="upper left", fontsize=8, handletextpad=0.2)
axes[0].set_title("2008 年前有形投资与名义利率正相关，2008 年后关系消失", fontsize=11)
fig.tight_layout()
save(fig, "inv_07_tangible_scatter", "BEA，美联储，纽约联储 ACM；季度数据")

# ---------- 5. 最新读数 ----------
last = q.dropna(subset=["nonres_share"]).index[-1]
lines += ["## 5. 最新读数\n",
          f"- 最新季度：{last}",
          f"- 非住宅投资/GDP：{q.at[last, 'nonres_share']:.1f}%",
          f"- 实际非住宅投资同比（四季度均值近似）：{q.at[last, 'inv_g']:.1f}%",
          f"- 信息处理设备与软件/GDP：{q.at[last, 'info_share']:.2f}%；知识产权产品/GDP：{q.at[last, 'ipp_share']:.2f}%",
          f"- HLW r*：{q.at[last, 'hlw_rstar']:.2f}%；ACM 10Y 期限溢价（季均）：{q.at[last, 'acm_tp10']:.2f}%\n"]

(OUT / "investment_results.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
