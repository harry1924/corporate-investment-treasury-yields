"""非金融企业融资缺口长序列（1929 年起，年度）。

- 1946 年起：美联储 Z.1 官方口径（FA105005305，年度）
- 1929—1945 年：估算。内部资金取 BEA NIPA 表 1.14（非金融企业固定资本消耗 B456RC
  + 含 IVA、CCAdj 的未分配利润 W332RC，1946 年后与 Z.1 内部资金几乎完全一致）；
  资本开支 = r ×（私人非住宅固定投资 A008RC + 非农存货变动 A015RC），
  r 为 1946—1965 年 Z.1 非金融企业资本开支占上述合计的平均比例。

输出：data/processed/financing_gap_annual.csv、figures/fin_06_financing_gap_long.png、
output/financing_gap_long.md
"""
import io

import pandas as pd
import requests

from common import C1, C2, C3, INK2, OUT, PROC, SHADE, plt, save

NIPA_URL = "https://apps.bea.gov/national/Release/TXT/NipaDataA.txt"


def fred(sid: str) -> pd.Series:
    t = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01", timeout=120).text
    s = pd.read_csv(io.StringIO(t), index_col=0, parse_dates=True, na_values=".").iloc[:, 0]
    return s


def main():
    n = pd.read_csv(io.StringIO(requests.get(NIPA_URL, timeout=180).text))
    n.columns = ["s", "y", "v"]
    n["v"] = n["v"].astype(str).str.replace(",", "").astype(float)
    w = n[n.s.isin(["A008RC", "A015RC", "A191RC", "B456RC", "W332RC"])].pivot(index="y", columns="s", values="v")
    w.index = w.index.astype(int)

    z_capex, z_gap = fred("BOGZ1FA105050005A"), fred("BOGZ1FA105005305A")
    w["capex_z1"] = pd.Series(z_capex.values, z_capex.index.year)
    w["gap_z1"] = pd.Series(z_gap.values, z_gap.index.year)
    w["internal_nipa"] = w["B456RC"] + w["W332RC"]
    w["base"] = w["A008RC"] + w["A015RC"]

    ratio = (w["capex_z1"] / w["base"]).loc[1946:1965]
    r, sd = ratio.mean(), ratio.std()
    for k, rr in [("est", r), ("est_lo", r - 2 * sd), ("est_hi", r + 2 * sd)]:
        w[f"gap_{k}_gdp"] = (rr * w["base"] - w["internal_nipa"]) / w["A191RC"] * 100
    w["gap_z1_gdp"] = w["gap_z1"] / w["A191RC"] * 100
    w["gap_gdp"] = w["gap_z1_gdp"].fillna(w["gap_est_gdp"])

    # 长端利率：1953 年及以前用长期国债收益率（LTGOVTBD），此后用 10 年期美债
    lt, gs10, cpi = fred("LTGOVTBD"), fred("GS10"), fred("CPIAUCNS")
    lt_a = lt.groupby(lt.index.year).mean()
    gs_a = gs10.groupby(gs10.index.year).mean()[gs10.groupby(gs10.index.year).count() == 12]
    cpi_a = cpi.groupby(cpi.index.year).mean()
    w["long_yield"] = pd.concat([lt_a.loc[:1953], gs_a.loc[1954:]])
    w["cpi_yoy"] = cpi_a.pct_change() * 100
    w["real_long"] = w["long_yield"] - w["cpi_yoy"]
    w = w.loc[1929:]
    w.to_csv(PROC / "financing_gap_annual.csv")

    # 校验与分时期相关
    ov = w.loc[1946:1965]
    lines = ["# 融资缺口长序列（1929 年起）\n",
             f"资本开支比例 r = {r:.3f}（1946—1965 年均值，标准差 {sd:.3f}）。\n",
             f"校验（1946—1965 年，估算 vs Z.1 官方）：相关系数 {ov['gap_est_gdp'].corr(ov['gap_z1_gdp']):.2f}，"
             f"平均绝对误差 {(ov['gap_est_gdp'] - ov['gap_z1_gdp']).abs().mean():.2f} 个点 GDP。\n",
             f"内部资金校验：1955 年 NIPA {w.at[1955, 'internal_nipa']:,.0f} vs Z.1 "
             f"{w.at[1955, 'capex_z1'] - w.at[1955, 'gap_z1']:,.0f}（百万美元）。\n"]
    rows = []
    for s0, s1, en in [(1929, 1941, "1929—1941"), (1946, 1984, "1946—1984"), (1985, 2025, "1985—2025"),
                       (1929, 2025, "1929—2025（剔除 1942—1951 利率钉住期）")]:
        d = w.loc[s0:s1]
        if "剔除" in en:
            d = d.drop(range(1942, 1952), errors="ignore")
        rows.append({"样本": en, "融资缺口 vs 长端名义利率": d["gap_gdp"].corr(d["long_yield"]),
                     "融资缺口 vs 长端实际利率": d["gap_gdp"].corr(d["real_long"]), "N": len(d.dropna(subset=["gap_gdp"]))})
    lines += ["## 分时期相关系数（年度水平）\n", pd.DataFrame(rows).round(2).to_markdown(index=False), "\n",
              "## 1929—1950 年读数（%GDP）\n",
              w.loc[1929:1950, ["gap_est_gdp", "gap_z1_gdp", "long_yield", "real_long"]].round(2).T.to_markdown(), "\n"]
    (OUT / "financing_gap_long.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    # 图：融资缺口（右轴）与长端名义、实际利率（左轴）
    fig, ax = plt.subplots(figsize=(11, 5.4))
    x = w.index
    ax.axvspan(1941.5, 1951.5, color=SHADE, lw=0, zorder=0)
    ax.text(1946.5, 15.3, "1942—1951\n利率钉住期", ha="center", va="top", fontsize=8, color=INK2)
    l1, = ax.plot(x, w["long_yield"], color=C1, label="长端美债收益率（左轴；1953 年及以前为长期国债）")
    l2, = ax.plot(x, w["real_long"], color=C2, lw=1.4, label="长端实际利率，减 CPI 同比（左轴）")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_ylim(-16, 16); ax.set_ylabel("利率（%）")
    axr = ax.twinx()
    est = w.loc[:1945]
    axr.fill_between(est.index, est["gap_est_lo_gdp"], est["gap_est_hi_gdp"], color=C3, alpha=0.2, lw=0)
    l3, = axr.plot(est.index, est["gap_est_gdp"], color=C3, lw=2.2, ls="--", label="融资缺口/GDP，1929—1945 估算（右轴）")
    off = w.loc[1946:]
    l4, = axr.plot(off.index, off["gap_z1_gdp"], color=C3, lw=2.4, label="融资缺口/GDP，Z.1 官方（右轴）")
    axr.set_ylim(-6, 6); axr.set_ylabel("融资缺口/GDP（%）"); axr.grid(False)
    axr.spines["right"].set_visible(True)
    ax.legend(handles=[l4, l3, l1, l2], loc="lower left", ncol=2, fontsize=8.5)
    ax.set_title("1929 年以来，企业融资缺口与长端名义利率温和正相关，与实际利率的关系不稳定")
    save(fig, "fin_06_financing_gap_long",
         "美联储 Z.1，BEA NIPA 表 1.14 / 1.1.5，FRED（LTGOVTBD、GS10、CPI）；1929—1945 年为估算，阴影为 ±2 倍标准差区间")


if __name__ == "__main__":
    main()
