"""10 年及以上国债供给与利率。

数据：
- 美国财政部 Fiscal Data API：
  · MSPD 表 3（2001 年起，逐只证券月末存量）→ 剩余期限 ≥10 年的附息国债存量
  · 拍卖数据（1979 年 11 月起）→ 原始期限 ≥10 年的附息国债毛发行
- FRED TREAS10Y：美联储持有的剩余期限 10 年以上国债（周度，2002 年 12 月起）
私人部门持有的 ≥10 年国债 = MSPD 剩余期限 ≥10 年存量 − 美联储持有。

输出：data/processed/long_duration_supply.csv、figures/fin_11—fin_13、output/long_duration_supply.md
"""
import io

import numpy as np
import pandas as pd
import requests

from common import C1, C2, C3, INK, INK2, OUT, PROC, SHADE, fmt_coef, load_q, ols_nw, plt, save, to_ts

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
COUPON = ["Notes", "Bonds", "Inflation-Protected Securities", "Inflation-Indexed Notes", "Inflation-Indexed Bonds"]
QE = [("2008Q4", "2014Q4"), ("2020Q1", "2022Q1")]


def pull(ep: str, fields: str, sort: str) -> pd.DataFrame:
    out, p = [], 1
    while True:
        r = requests.get(API + ep, params={"page[size]": 10000, "page[number]": p, "fields": fields, "sort": sort},
                         timeout=300).json()
        out += r["data"]
        if p >= r["meta"]["total-pages"]:
            return pd.DataFrame(out)
        p += 1


def build() -> pd.DataFrame:
    m = pull("/v1/debt/mspd/mspd_table_3_market",
             "record_date,security_class1_desc,issue_date,maturity_date,outstanding_amt", "record_date")
    m = m[m.security_class1_desc.isin(COUPON)].copy()
    for c in ["record_date", "maturity_date"]:
        m[c] = pd.to_datetime(m[c], errors="coerce")
    m["out"] = pd.to_numeric(m["outstanding_amt"], errors="coerce") / 1000  # 百万 → 十亿美元
    m = m.dropna(subset=["record_date", "maturity_date", "out"])
    m["rem"] = (m.maturity_date - m.record_date).dt.days / 365.25
    ms = pd.DataFrame({"coupon_all": m.groupby("record_date").out.sum(),
                       "rem10": m[m.rem >= 10].groupby("record_date").out.sum()})
    ms = ms.resample("QE").last()
    ms.index = ms.index.to_period("Q")

    a = pull("/v1/accounting/od/auctions_query",
             "security_type,original_security_term,issue_date,offering_amt,total_accepted", "issue_date")
    a["yrs"] = a.original_security_term.astype(str).str.extract(r"(\d+)-Year").astype(float)
    a["amt"] = pd.to_numeric(a.total_accepted, errors="coerce").fillna(pd.to_numeric(a.offering_amt, errors="coerce"))
    a["issue_date"] = pd.to_datetime(a.issue_date)
    lg = a[(a.security_type != "Bill") & (a.yrs >= 10)]
    gross = lg.groupby(lg.issue_date.dt.to_period("Q")).amt.sum() / 1e9

    t = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=TREAS10Y&cosd=2002-01-01", timeout=120).text
    f = pd.read_csv(io.StringIO(t), index_col=0, parse_dates=True).iloc[:, 0] / 1000
    f = f.resample("QE").last()
    f.index = f.index.to_period("Q")

    d = pd.concat({"coupon_all": ms.coupon_all, "rem10": ms.rem10, "fed10": f, "gross10": gross}, axis=1).sort_index()
    d.index.name = "quarter"
    d.to_csv(PROC / "long_duration_supply.csv")
    return d


def main():
    d = build()
    q = load_q()
    q["fed_cpn"] = (q["fed_coupon_flow"] / 4).fillna(0).cumsum()
    q["cpn_priv_gdp"] = (q["ust_coupon_level"] - q["fed_cpn"]) / (q["GDP"] * 1000) * 100
    d = d.join(q[["GDP", "acm_tp10", "GS10", "GS30", "FEDFUNDS", "infl_yoy", "cpn_priv_gdp"]], how="left")
    d["rem10_gdp"] = d.rem10 / d.GDP * 100
    d["priv10_gdp"] = (d.rem10 - d.fed10) / d.GDP * 100
    d["gross10_gdp"] = d.gross10.rolling(4).sum() / d.GDP * 100
    d = d.loc[:"2026Q2"]
    s = d.dropna(subset=["priv10_gdp", "acm_tp10"])

    lines = ["# 10 年及以上国债供给与利率（脚本自动生成）\n"]
    snap = s.loc[["2002Q4", "2007Q4", "2012Q4", "2016Q4", "2020Q4", "2022Q4", "2024Q4", "2026Q2"],
                 ["rem10", "fed10", "rem10_gdp", "priv10_gdp", "acm_tp10", "GS30"]]
    snap.columns = ["剩余期限≥10年存量(十亿美元)", "美联储持有(十亿美元)", "存量/GDP", "私人持有/GDP", "ACM期限溢价", "30Y"]
    lines += ["## 1. 剩余期限 ≥10 年国债存量\n", snap.round(2).to_markdown(), "\n"]

    rows, sc = [], {}
    samples = [("全样本 2002—2026", s), ("剔除 2020—2022", s.drop(s.loc["2020Q1":"2022Q4"].index))]
    for lab, dd in samples:
        for h in [4, 12]:
            for x, xn in [("priv10_gdp", "私人持有≥10年国债/GDP"), ("cpn_priv_gdp", "私人持有全部附息国债/GDP")]:
                r = {"样本": lab, "窗口": f"{h // 4} 年", "供给口径": xn}
                for y, yn in [("acm_tp10", "Δ期限溢价"), ("GS30", "Δ30Y"), ("GS10", "Δ10Y")]:
                    X = pd.DataFrame({"dS": dd[x].diff(h), "dFF": dd.FEDFUNDS.diff(h), "dI": dd.infl_yoy.diff(h)})
                    res, *_ , n = ols_nw(dd[y].diff(h), X, h)
                    r[yn] = fmt_coef(res, "dS", 100)
                    if lab.startswith("全样本") and h == 12 and y == "acm_tp10":
                        sc[x] = res
                r["N"] = n
                rows.append(r)
    lines += ["## 2. 回归：供给/GDP 在窗口内每上升 1 个点，同期利率变化（bp）\n",
              "控制联邦基金利率变化与通胀变化；Newey-West 滞后阶数取窗口季度数。\n",
              pd.DataFrame(rows).to_markdown(index=False), "\n"]
    res_lv, *_ = ols_nw(s.acm_tp10, s[["priv10_gdp", "infl_yoy"]], 8)
    lines += [f"水平回归（期限溢价对私人持有≥10年国债/GDP，控制通胀）：{fmt_coef(res_lv, 'priv10_gdp', 100)}；"
              "水平序列受 QE 期间趋势主导，结论以变化回归为准。\n"]
    g = d.dropna(subset=["gross10_gdp"])
    lines += [f"## 3. 原始期限 ≥10 年附息国债毛发行（近四季度合计/GDP）\n",
              g.loc[[p for p in g.index if p.quarter == 4 and p.year % 4 == 3], ["gross10", "gross10_gdp"]]
              .round(2).set_axis(["当季毛发行(十亿美元)", "近四季度合计/GDP(%)"], axis=1).to_markdown(), "\n",
              f"最新（{g.index[-1]}）：近四季度毛发行 {g.gross10.iloc[-4:].sum():,.0f} 十亿美元，占 GDP {g.gross10_gdp.iloc[-1]:.2f}%。\n"]
    (OUT / "long_duration_supply.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    def shade(ax):
        for a0, b0 in QE:
            ax.axvspan(pd.Period(a0, "Q").to_timestamp(), pd.Period(b0, "Q").to_timestamp(how="end"),
                       color=SHADE, lw=0, zorder=0)

    # 图11：私人持有 ≥10 年国债存量与利率
    fig, ax = plt.subplots(figsize=(11, 5.2))
    shade(ax)
    x = to_ts(s.index)
    la, = ax.plot(x, s.GS30, color=INK, lw=1.6, label="30年期美债收益率（左轴）")
    lb, = ax.plot(x, s.acm_tp10, color=C2, lw=1.8, label="ACM 期限溢价（左轴）")
    ax.axhline(0, color=INK2, lw=0.8); ax.set_ylim(-2, 7); ax.set_ylabel("%")
    axr = ax.twinx()
    lc, = axr.plot(x, s.priv10_gdp, color=C1, lw=2.4, label="私人持有剩余期限≥10年国债/GDP（右轴）")
    ld, = axr.plot(x, s.rem10_gdp, color=C1, lw=1.2, ls=":", label="剩余期限≥10年国债/GDP，含美联储（右轴）")
    axr.set_ylim(0, 20); axr.set_ylabel("%GDP"); axr.grid(False); axr.spines["right"].set_visible(True)
    ax.legend(handles=[lc, ld, la, lb], loc="upper left", ncol=2, fontsize=8.5)
    ax.set_title("私人持有的 10 年以上国债在 2022 年后加速上升，期限溢价同步抬升")
    save(fig, "fin_11_long_supply_vs_rates", "美国财政部 MSPD，美联储 H.4.1（TREAS10Y），纽约联储 ACM；阴影为 QE 时期")

    # 图12：3 年变化散点：≥10 年 vs 全部附息
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (xv, nm, c) in zip(axes, [("priv10_gdp", "私人持有≥10年国债/GDP", C1),
                                      ("cpn_priv_gdp", "私人持有全部附息国债/GDP", C3)]):
        dx, dy = s[xv].diff(12), s.acm_tp10.diff(12)
        ok = dx.notna() & dy.notna()
        ax.scatter(dx[ok], dy[ok], s=18, color=c, alpha=0.75, edgecolors="none")
        b = np.polyfit(dx[ok], dy[ok], 1)
        xx = np.linspace(dx[ok].min(), dx[ok].max(), 50)
        ax.plot(xx, np.polyval(b, xx), color=INK, lw=1.2)
        res = sc[xv]
        ax.text(0.03, 0.95, f"控制政策利率与通胀后：{res.params['dS'] * 100:+.1f}bp（t={res.tvalues['dS']:.2f}）",
                transform=ax.transAxes, va="top", fontsize=9, color=INK2)
        ax.axhline(0, color=INK2, lw=0.8); ax.axvline(0, color=INK2, lw=0.8)
        ax.set_xlabel(f"3 年变化：{nm}（个点）"); ax.set_title(nm, fontsize=11)
    axes[0].set_ylabel("3 年变化：ACM 期限溢价（个点）")
    fig.suptitle("只看 10 年以上国债，私人持有增加对应期限溢价上行；全部附息国债口径无此关系", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    save(fig, "fin_12_long_supply_scatter", "美国财政部 MSPD，美联储 H.4.1，Z.1，纽约联储 ACM；2002Q4—2026Q2 季度，3 年变化")

    # 图13：≥10 年毛发行长序列
    fig, ax = plt.subplots(figsize=(11, 5))
    shade(ax)
    gx = to_ts(g.index)
    la, = ax.plot(gx, g.GS30, color=INK, lw=1.6, label="30年期美债收益率（左轴）")
    lb, = ax.plot(gx, g.acm_tp10, color=C2, lw=1.8, label="ACM 期限溢价（左轴）")
    ax.axhline(0, color=INK2, lw=0.8); ax.set_ylim(-2, 15); ax.set_ylabel("%")
    axr = ax.twinx()
    lc, = axr.plot(gx, g.gross10_gdp, color=C1, lw=2.4, label="原始期限≥10年附息国债毛发行，近四季度/GDP（右轴）")
    axr.set_ylim(0, 8); axr.set_ylabel("%GDP"); axr.grid(False); axr.spines["right"].set_visible(True)
    ax.legend(handles=[lc, la, lb], loc="upper right", fontsize=8.5)
    ax.set_title("10 年以上国债发行占 GDP 比重 2010 年以来均值 3.5%，为 1981—2007 年均值的 2.9 倍")
    save(fig, "fin_13_long_gross_issuance", "美国财政部拍卖数据（1979 年 11 月起），纽约联储 ACM；阴影为 QE 时期")


if __name__ == "__main__":
    main()
