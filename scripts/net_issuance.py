"""企业净发债、国债净发行与利率：中长期视角。

“中长期”两层含义：
1) 期限：企业端取公司债（剔除商业票据），国债端取附息国债（中长期票据+债券，剔除国库券），
   并扣除美联储净买入，得到私人部门需要吸收的附息国债供给；
2) 时间维度：1 年、3 年、5 年移动平均的净发行，对照同期利率变化，并看存量与期限溢价水平。

美联储附息国债持有量以 Z.1 净买入（FA713061125）累加得到；2002 年后与 H.4.1 名义附息持有量
相比偏高 1%—22%（中位数 6%），差异主要来自 TIPS 通胀补偿与溢价摊销。

输出：figures/fin_07—fin_10、output/net_issuance.md
"""
import numpy as np
import pandas as pd

from common import C1, C2, C3, INK, INK2, OUT, SHADE, fmt_coef, load_q, ols_nw, plt, save, to_ts

q = load_q().loc["1947Q4":"2026Q2"].copy()
gdp_mn = q["GDP"] * 1000
q["fed_cpn_level"] = (q["fed_coupon_flow"] / 4).fillna(0).cumsum()
q["cpn_priv_gdp"] = (q["ust_coupon_level"] - q["fed_cpn_level"]) / gdp_mn * 100
q["cpn_xfed_flow_gdp"] = q["ust_coupon_flow_gdp"] - q["fed_coupon_flow_gdp"]

H = [(1, 4), (3, 12), (5, 20)]
SUP = {"corp": ("nfc_bond_flow_gdp", "企业公司债净发行"),
       "cp": ("nfc_cp_flow_gdp", "商业票据净发行"),
       "cpnx": ("cpn_xfed_flow_gdp", "附息国债净发行（扣除美联储）"),
       "cpn": ("ust_coupon_flow_gdp", "附息国债净发行"),
       "bill": ("ust_bill_flow_gdp", "国库券净发行")}
for h, k in H:
    for key, (col, _) in SUP.items():
        q[f"{key}{h}"] = q[col].rolling(k).mean()
    for y in ["GS10", "acm_tp10", "real10_ex_post", "FEDFUNDS", "infl_yoy"]:
        q[f"d{h}_{y}"] = q[y].diff(k)

QE = [("2008Q4", "2014Q4"), ("2020Q1", "2022Q1")]
lines = ["# 企业净发债、国债净发行与利率（脚本自动生成）\n"]

# ---------- 1. 分期限、分时间维度的相关 ----------
rows = []
for s0, s1, en in [("1962", "2026", "1962—2026"), ("1962", "2007", "1962—2007"), ("2008", "2026", "2008—2026")]:
    d = q.loc[s0:s1]
    for h, _ in H:
        r = {"样本": en, "窗口": f"{h} 年"}
        for key in ["corp", "cpnx"]:
            nm = "企业债" if key == "corp" else "附息国债(扣美联储)"
            r[f"{nm} vs Δ10Y"] = d[f"{key}{h}"].corr(d[f"d{h}_GS10"])
            r[f"{nm} vs Δ期限溢价"] = d[f"{key}{h}"].corr(d[f"d{h}_acm_tp10"])
        rows.append(r)
corr = pd.DataFrame(rows)
lines += ["## 1. 净发行（h 年均值，%GDP）与同期 h 年利率变化的相关系数\n", corr.round(2).to_markdown(index=False), "\n"]

# ---------- 2. 回归：同时放入企业债与附息国债净发行 ----------
rows, coef = [], {}
for h, k in H:
    for y, yn in [("acm_tp10", "期限溢价"), ("GS10", "10年期美债")]:
        res, a, b, n = ols_nw(q.loc["1962":, f"d{h}_{y}"],
                              q.loc["1962":, [f"corp{h}", f"cpnx{h}", f"d{h}_FEDFUNDS", f"d{h}_infl_yoy"]], k)
        rows.append({"窗口": f"{h} 年", "因变量": f"Δ{yn}", "企业公司债净发行": fmt_coef(res, f"corp{h}", 100),
                     "附息国债净发行(扣美联储)": fmt_coef(res, f"cpnx{h}", 100), "N": n})
        coef[(h, yn)] = res
lines += ["## 2. 回归：h 年净发行（%GDP）每上升 1 个点，同期 h 年利率变化（bp）\n",
          "控制 h 年联邦基金利率变化与通胀变化；Newey-West 滞后阶数取窗口季度数；样本 1962 年起。\n",
          pd.DataFrame(rows).to_markdown(index=False), "\n"]

# ---------- 3. 存量：私人持有附息国债 / 企业债 与期限溢价水平 ----------
rows = []
for s0, s1, en in [("1962", "2007", "1962—2007"), ("2008", "2026", "2008—2026"), ("1962", "2026", "1962—2026")]:
    res, a, b, n = ols_nw(q.loc[s0:s1, "acm_tp10"], q.loc[s0:s1, ["cpn_priv_gdp", "nfc_bond_level_gdp", "infl_yoy"]], 12)
    rows.append({"样本": en, "私人持有附息国债/GDP": fmt_coef(res, "cpn_priv_gdp", 100),
                 "企业公司债/GDP": fmt_coef(res, "nfc_bond_level_gdp", 100), "R²": round(res.rsquared, 2), "N": n})
lines += ["## 3. 回归：存量/GDP 每上升 1 个点，ACM 期限溢价水平（bp）\n", "控制通胀；Newey-West(12)。\n",
          pd.DataFrame(rows).to_markdown(index=False), "\n"]
snap = q.loc[["1962Q1", "1974Q4", "1985Q1", "1996Q1", "2000Q4", "2007Q4", "2014Q4", "2020Q4", "2026Q2"],
             ["cpn_priv_gdp", "nfc_bond_level_gdp", "acm_tp10", "GS10"]]
snap.columns = ["私人持有附息国债/GDP", "企业公司债/GDP", "ACM期限溢价", "10Y"]
lines += ["存量读数（%）：\n", snap.round(1).to_markdown(), "\n"]
lt = q.loc["2002Q4":]
lines += ["最新：私人持有附息国债/GDP " f"{q['cpn_priv_gdp'].iloc[-1]:.1f}%，企业公司债/GDP {q['nfc_bond_level_gdp'].iloc[-1]:.1f}%，"
          f"附息国债净发行（扣美联储，3 年均值）{q['cpnx3'].iloc[-1]:.2f}% GDP，企业公司债净发行（3 年均值）{q['corp3'].iloc[-1]:.2f}% GDP。\n"]
(OUT / "net_issuance.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))


def shade_qe(ax):
    for a, b in QE:
        ax.axvspan(pd.Period(a, "Q").to_timestamp(), pd.Period(b, "Q").to_timestamp(how="end"),
                   color=SHADE, lw=0, zorder=0)


def rates_left(ax, d, ylim=(-2, 16)):
    x = to_ts(d.index)
    la, = ax.plot(x, d["GS10"], color=INK, lw=1.6, label="10年期美债收益率（左轴）")
    lb, = ax.plot(x, d["acm_tp10"], color=C2, lw=1.6, label="ACM 期限溢价（左轴）")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_ylim(*ylim); ax.set_ylabel("%")
    return [la, lb]


# ---------- 图7：企业净发债与利率 ----------
d = q.loc["1955Q1":]
fig, ax = plt.subplots(figsize=(11, 5.2))
shade_qe(ax)
hl = rates_left(ax, d)
axr = ax.twinx()
x = to_ts(d.index)
l1, = axr.plot(x, d["corp3"], color=C1, lw=2.4, label="企业公司债净发行，3 年均值（右轴）")
l2, = axr.plot(x, d["cp3"], color=C3, lw=1.6, ls="--", label="商业票据净发行，3 年均值（右轴）")
axr.axhline(0, color=C1, lw=0.6, ls=":")
axr.set_ylim(-1.5, 4.5); axr.set_ylabel("%GDP"); axr.grid(False); axr.spines["right"].set_visible(True)
ax.legend(handles=[l1, l2] + hl, loc="upper left", ncol=2, fontsize=8.5)
ax.set_title("企业中长期发债多在利率下行期放量，发行择时特征明显")
save(fig, "fin_07_corp_issuance_vs_rates", "美联储 Z.1（FA103163005、FA103169100），纽约联储 ACM；阴影为 QE 时期")

# ---------- 图8：国债净发行与利率 ----------
fig, ax = plt.subplots(figsize=(11, 5.2))
shade_qe(ax)
hl = rates_left(ax, d)
axr = ax.twinx()
l1, = axr.plot(x, d["cpnx3"], color=C1, lw=2.4, label="附息国债净发行，扣除美联储买入，3 年均值（右轴）")
l2, = axr.plot(x, d["cpn3"], color=C1, lw=1.2, ls=":", label="附息国债净发行，3 年均值（右轴）")
l3, = axr.plot(x, d["bill3"], color=C3, lw=1.6, ls="--", label="国库券净发行，3 年均值（右轴）")
axr.set_ylim(-4, 12); axr.set_ylabel("%GDP"); axr.grid(False); axr.spines["right"].set_visible(True)
ax.legend(handles=[l1, l2, l3] + hl, loc="upper left", ncol=2, fontsize=8.5)
ax.set_title("附息国债净供给在衰退与财政扩张期上升，同期利率多处下行阶段")
save(fig, "fin_08_treasury_issuance_vs_rates", "美联储 Z.1（FA313161275、FA313161110、FA713061125），纽约联储 ACM；阴影为 QE 时期")

# ---------- 图9：时间维度——相关系数随窗口变化 ----------
fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), sharey=True)
for ax, (s0, s1, en) in zip(axes, [("1962", "2007", "1962—2007"), ("1962", "2026", "1962—2026")]):
    dd = corr[corr["样本"] == en].set_index("窗口")
    cols = ["企业债 vs Δ10Y", "企业债 vs Δ期限溢价", "附息国债(扣美联储) vs Δ10Y", "附息国债(扣美联储) vs Δ期限溢价"]
    labs = ["企业债 vs Δ10Y", "企业债 vs Δ期限溢价", "附息国债 vs Δ10Y", "附息国债 vs Δ期限溢价"]
    xx = np.arange(len(cols))
    for i, (w, c) in enumerate(zip(dd.index, [C3, C1, C2])):
        v = dd.loc[w, cols].values.astype(float)
        ax.bar(xx + (i - 1) * 0.26, v, 0.24, color=c, label=f"{w}窗口")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xticks(xx, [l.replace(" vs ", "\nvs ") for l in labs], fontsize=8.5)
    ax.set_title(en, fontsize=11)
axes[0].set_ylabel("相关系数")
axes[1].legend(loc="lower right", fontsize=9)
fig.suptitle("拉长时间窗口后，净发行与同期利率变化的负相关加深，择时效应主导流量关系", x=0.01, ha="left",
             fontsize=12, fontweight="bold")
fig.tight_layout()
save(fig, "fin_09_horizon_correlation", "美联储 Z.1，纽约联储 ACM；净发行取窗口均值（%GDP），利率取窗口内变化")

# ---------- 图10：存量与期限溢价 ----------
fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
d2 = q.loc["1961Q3":]
x2 = to_ts(d2.index)
for ax, col, nm, yl, c in [(a1, "cpn_priv_gdp", "私人持有附息国债/GDP", (0, 70), C1),
                           (a2, "nfc_bond_level_gdp", "企业公司债/GDP", (0, 35), C3)]:
    shade_qe(ax)
    lt_, = ax.plot(x2, d2["acm_tp10"], color=C2, lw=1.8, label="ACM 期限溢价（左轴）")
    ax.axhline(0, color=INK2, lw=0.8); ax.set_ylim(-2, 5.5); ax.set_ylabel("%")
    axr = ax.twinx()
    ls_, = axr.plot(x2, d2[col], color=c, lw=2.4, label=f"{nm}（右轴）")
    axr.set_ylim(*yl); axr.set_ylabel("%GDP"); axr.grid(False); axr.spines["right"].set_visible(True)
    ax.legend(handles=[ls_, lt_], loc="upper left", fontsize=9)
a1.set_title("控制通胀后，2007 年前私人持有附息国债越多期限溢价越高；QE 后这一关系断裂")
save(fig, "fin_10_stocks_vs_term_premium", "美联储 Z.1，纽约联储 ACM；美联储附息国债持有量由净买入累加；阴影为 QE 时期")
