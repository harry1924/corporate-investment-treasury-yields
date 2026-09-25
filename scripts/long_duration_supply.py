"""10 年及以上国债净供给与利率（流量口径）。

净发行 = 原始期限 ≥10 年附息国债的发行 − 到期 − 回购：
- 2001Q2 起：财政部公债月报 MSPD 表 3 逐只证券存量的季度变化（已含到期与回购）
- 1990—2001Q1：财政部拍卖数据，毛发行 − 同口径证券到期；1979 年 11 月前发行的长债到期未覆盖，
  1990 年代净发行或略有高估。两种方法在 2001—2026 年相关系数 0.99。
私人净供给 = 净发行 − 美联储净买入。美联储净买入取纽约联储 SOMA 逐只持仓（2003Q3 起）中原始期限
≥10 年证券面值的季度变化，与净发行口径一致。原始期限按 CUSIP 对应的拍卖期限认定。

输出：data/processed/long_duration_net_supply.csv、figures/fin_11—fin_13、output/long_duration_supply.md
"""
import time

import numpy as np
import pandas as pd
import requests

from common import C1, C2, C3, INK, INK2, OUT, PROC, SHADE, fmt_coef, load_q, ols_nw, plt, save, to_ts

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
SOMA = "https://markets.newyorkfed.org/api/soma"
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


def soma_quarterly() -> pd.DataFrame:
    dates = pd.Series(sorted(pd.to_datetime(requests.get(f"{SOMA}/asofdates/list.json", timeout=60)
                                            .json()["soma"]["asOfDates"])))
    rows = []
    for p in pd.period_range(dates.min().to_period("Q"), dates.max().to_period("Q"), freq="Q"):
        d = dates[dates <= p.end_time].max()
        for _ in range(3):
            try:
                h = requests.get(f"{SOMA}/tsy/get/asof/{d:%Y-%m-%d}.json", timeout=120).json()["soma"]["holdings"]
                break
            except Exception:
                time.sleep(3)
        rows += [(p, x["cusip"], float(x["parValue"]) / 1e9) for x in h if x["securityType"] != "Bills"]
    return pd.DataFrame(rows, columns=["quarter", "cusip", "par"])


def build() -> pd.DataFrame:
    a = pull("/v1/accounting/od/auctions_query",
             "cusip,security_type,original_security_term,issue_date,maturity_date,offering_amt,total_accepted",
             "issue_date")
    a = a[a.security_type != "Bill"].copy()
    a["yrs"] = a.original_security_term.astype(str).str.extract(r"(\d+)-Year", expand=False).astype(float)
    a["amt"] = (pd.to_numeric(a.total_accepted, errors="coerce")
                .fillna(pd.to_numeric(a.offering_amt, errors="coerce")) / 1e9)
    for c in ["issue_date", "maturity_date"]:
        a[c] = pd.to_datetime(a[c])
    term = a.groupby("cusip").yrs.max()
    lg = a[a.yrs >= 10]
    gross = lg.groupby(lg.issue_date.dt.to_period("Q")).amt.sum()
    mat = lg.groupby(lg.maturity_date.dt.to_period("Q")).amt.sum()

    m = pull("/v1/debt/mspd/mspd_table_3_market",
             "record_date,security_class1_desc,security_class2_desc,issue_date,maturity_date,outstanding_amt",
             "record_date")
    m = m[m.security_class1_desc.isin(COUPON)].copy()
    for c in ["record_date", "issue_date", "maturity_date"]:
        m[c] = pd.to_datetime(m[c], errors="coerce")
    m["out"] = pd.to_numeric(m.outstanding_amt, errors="coerce") / 1000
    m["yrs"] = m.security_class2_desc.map(term).fillna((m.maturity_date - m.issue_date).dt.days / 365.25)
    out10 = m[m.yrs >= 9.5].groupby("record_date").out.sum().resample("QE").last()
    out10.index = out10.index.to_period("Q")

    s = soma_quarterly()
    s["yrs"] = s.cusip.map(term)
    fed10 = s[s.yrs >= 10].groupby("quarter").par.sum()

    idx = pd.period_range("1979Q4", out10.index.max(), freq="Q")
    d = pd.DataFrame(index=idx)
    d["gross"] = gross.reindex(idx).fillna(0)
    d["maturing"] = mat.reindex(idx).fillna(0)
    d["net_auction"] = d.gross - d.maturing
    d["out10_mspd"] = out10
    d["net"] = d.out10_mspd.diff().where(d.index >= pd.Period("2001Q2", "Q"), d.net_auction)
    d["fed10"] = fed10
    d["fed_net"] = d.fed10.diff()
    d["priv_net"] = d.net - d.fed_net
    d.index.name = "quarter"
    d.to_csv(PROC / "long_duration_net_supply.csv")
    return d


def main():
    d = build()
    q = load_q()
    d = d.join(q[["GDP", "acm_tp10", "GS10", "GS30", "FEDFUNDS", "infl_yoy",
                  "ust_coupon_flow_gdp", "fed_coupon_flow_gdp"]]).loc["1980Q1":"2026Q2"]
    for c in ["gross", "maturing", "net", "fed_net", "priv_net"]:
        d[c + "_gdp"] = d[c] * 4 / d.GDP * 100  # 季度流量折年 / GDP
    d["cpnx_gdp"] = d.ust_coupon_flow_gdp - d.fed_coupon_flow_gdp

    ov = d.loc["2001Q2":"2026Q2"]
    lines = ["# 10 年及以上国债净供给与利率（脚本自动生成）\n",
             f"校验：2001Q2—2026Q2 拍卖法净发行与 MSPD 法相关系数 {ov.net_auction.corr(ov.net):.3f}，"
             f"累计分别为 {ov.net_auction.sum():,.0f} 与 {ov.net.sum():,.0f} 十亿美元。\n"]
    yr = d.groupby(d.index.year)[["gross_gdp", "maturing_gdp", "net_gdp", "fed_net_gdp", "priv_net_gdp"]].mean()
    yr.columns = ["毛发行", "到期", "净发行", "美联储净买入", "私人净供给"]
    yr.index.name = "年份"
    lines += ["## 1. 原始期限 ≥10 年附息国债供给（年度，%GDP）\n",
              yr.loc[[1990, 1995, 2000, 2005, 2008, 2010, 2012, 2015, 2019, 2020, 2021, 2022, 2023, 2024, 2025]]
              .round(2).to_markdown(), "\n"]

    measures = [("priv_net_gdp", "≥10年私人净供给（扣美联储）"), ("net_gdp", "≥10年净发行（含美联储）"),
                ("cpnx_gdp", "全部附息国债净供给（扣美联储）")]
    rows, coefs = [], {}
    for h, k in [(1, 4), (3, 12), (5, 20)]:
        for x, xn in measures:
            X = pd.DataFrame({"x": d[x].rolling(k).mean(), "dFF": d.FEDFUNDS.diff(k), "dI": d.infl_yoy.diff(k)})
            r = {"窗口": f"{h} 年", "供给口径": xn}
            for y, yn in [("acm_tp10", "Δ期限溢价"), ("GS30", "Δ30Y"), ("GS10", "Δ10Y")]:
                res, _, _, n = ols_nw(d.loc["2004":, y].diff(k), X.loc["2004":], k)
                r[yn] = fmt_coef(res, "x", 100)
                coefs[(h, x, y)] = (res.params["x"] * 100, res.bse["x"] * 100)
            r["N"] = n
            rows.append(r)
    lines += ["## 2. 回归（2004—2026）：窗口内年化净供给均值每 1 个点 GDP，对应窗口内利率变化（bp）\n",
              "控制联邦基金利率变化与通胀变化；Newey-West 滞后阶数取窗口季度数。\n",
              pd.DataFrame(rows).to_markdown(index=False), "\n"]
    rows = []
    for h, k in [(1, 4), (3, 12), (5, 20)]:
        X = pd.DataFrame({"x": d.net_gdp.rolling(k).mean(), "dFF": d.FEDFUNDS.diff(k), "dI": d.infl_yoy.diff(k)})
        r = {"窗口": f"{h} 年"}
        for y, yn in [("acm_tp10", "Δ期限溢价"), ("GS30", "Δ30Y"), ("GS10", "Δ10Y")]:
            res, _, _, n = ols_nw(d.loc["1990":, y].diff(k), X.loc["1990":], k)
            r[yn] = fmt_coef(res, "x", 100)
        r["N"] = n
        rows.append(r)
    lines += ["## 3. 长样本（1990—2026）：≥10年净发行（含美联储）\n", pd.DataFrame(rows).to_markdown(index=False), "\n"]
    p4 = d[["net_gdp", "priv_net_gdp"]].rolling(4).mean()
    lines += [f"最新（2026Q2，近四季度均值）：≥10年净发行 {p4.net_gdp.iloc[-1]:.2f}% GDP，"
              f"私人净供给 {p4.priv_net_gdp.iloc[-1]:.2f}% GDP。\n"]
    (OUT / "long_duration_supply.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    def shade(ax):
        for a0, b0 in QE:
            ax.axvspan(pd.Period(a0, "Q").to_timestamp(), pd.Period(b0, "Q").to_timestamp(how="end"),
                       color=SHADE, lw=0, zorder=0)

    # 图11：净供给（近四季度均值）与利率
    g = d.loc["1990Q1":].copy()
    g["net4"] = g.net_gdp.rolling(4).mean()
    g["priv4"] = g.priv_net_gdp.rolling(4).mean()
    fig, ax = plt.subplots(figsize=(11, 5.2))
    shade(ax)
    x = to_ts(g.index)
    la, = ax.plot(x, g.GS30, color=INK, lw=1.6, label="30年期美债收益率（左轴）")
    lb, = ax.plot(x, g.acm_tp10, color=C2, lw=1.8, label="ACM 期限溢价（左轴）")
    ax.axhline(0, color=INK2, lw=0.8); ax.set_ylim(-2, 10); ax.set_ylabel("%")
    axr = ax.twinx()
    lc, = axr.plot(x, g.priv4, color=C1, lw=2.4, label="≥10年国债私人净供给，扣除美联储（右轴）")
    ld, = axr.plot(x, g.net4, color=C1, lw=1.2, ls=":", label="≥10年国债净发行（右轴）")
    axr.axhline(0, color=C1, lw=0.6, ls="--")
    axr.set_ylim(-3, 5); axr.set_ylabel("%GDP，近四季度均值"); axr.grid(False); axr.spines["right"].set_visible(True)
    ax.legend(handles=[lc, ld, la, lb], loc="lower left", ncol=2, fontsize=8.5)
    ax.set_title("QE 期间美联储吸收长久期净发行，2022 年后私人净供给维持在 GDP 的 2% 以上")
    save(fig, "fin_11_long_net_supply_vs_rates",
         "美国财政部 MSPD 与拍卖数据，纽约联储 SOMA 持仓，纽约联储 ACM；近四季度均值；阴影为 QE 时期")

    # 图12：年度分解
    y2 = yr.loc[1990:2025]
    fig, ax = plt.subplots(figsize=(11, 5))
    xx = np.array(y2.index)
    ax.bar(xx, y2["毛发行"], 0.8, color=C1, label="毛发行")
    ax.bar(xx, -y2["到期"], 0.8, color=C3, label="到期（负值）")
    ax.bar(xx, -y2["美联储净买入"].fillna(0), 0.8, bottom=-y2["到期"], color=C2, label="美联储净买入（负值）")
    ax.plot(xx, y2["私人净供给"].where(xx >= 2004), color=INK, lw=2, marker="o", ms=4, label="私人净供给")
    ax.plot(xx, y2["净发行"], color=INK, lw=1.2, ls=":", label="净发行")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_ylabel("%GDP"); ax.legend(loc="upper left", ncol=3, fontsize=9)
    ax.set_title("≥10 年国债净供给的分解：发行扩张抬升净供给，美联储购债阶段性对冲")
    save(fig, "fin_12_long_net_supply_decomp",
         "美国财政部拍卖数据与 MSPD，纽约联储 SOMA；1990—2025 年，年内季度折年值均值；私人净供给自 2004 年起")

    # 图13：不同口径、不同窗口的系数对比
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, (y, yn) in zip(axes, [("GS30", "Δ30年期美债"), ("acm_tp10", "Δ期限溢价")]):
        for i, ((x, xn), c) in enumerate(zip(measures, [C1, INK2, C3])):
            bs = [coefs[(h, x, y)] for h in (1, 3, 5)]
            pos = np.arange(3) + (i - 1) * 0.22
            ax.errorbar(pos, [b for b, _ in bs], yerr=[1.96 * s_ for _, s_ in bs], fmt="o", color=c, ecolor=c,
                        elinewidth=2, ms=7, label=xn)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_xticks(range(3), ["1 年窗口", "3 年窗口", "5 年窗口"])
        ax.set_title(yn, fontsize=11)
    axes[0].set_ylabel("每 1 个点 GDP 年化净供给对应的利率变化（bp，95% 置信区间）")
    axes[1].legend(loc="upper left", fontsize=8.5)
    fig.suptitle("扣除美联储后的 ≥10 年国债净供给对 30 年期美债的推升在各窗口均成立，其他口径不稳定",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    save(fig, "fin_13_long_net_supply_coefs",
         "美国财政部，纽约联储 SOMA，Z.1，纽约联储 ACM；2004—2026 季度回归，控制联邦基金利率与通胀变化")


if __name__ == "__main__":
    main()
