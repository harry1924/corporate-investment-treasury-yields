"""下载原始数据并整理为季度 / 月度 / 日度面板。

来源：
- FRED（圣路易斯联储）：利率、投资、GDP、通胀
- 美联储 Z.1 金融账户：非金融企业与联邦政府的融资流量和存量
- 纽约联储：ACM 期限溢价模型、HLW 中性利率估计

用法：python scripts/fetch_data.py
"""
import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
RAW.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)

FRED = {
    # 利率
    "GS10": "10年期美债收益率（月）",
    "GS30": "30年期美债收益率（月）",
    "FEDFUNDS": "联邦基金利率（月）",
    "TB3MS": "3个月国库券利率（月）",
    "AAA": "穆迪Aaa企业债收益率（月）",
    "BAA": "穆迪Baa企业债收益率（月）",
    "THREEFYTP10": "KW 10年期期限溢价（日）",
    "EXPINF10YR": "克利夫兰联储10年通胀预期（月）",
    "DGS10": "10年期美债收益率（日）",
    "DGS30": "30年期美债收益率（日）",
    # 价格与就业
    "PCEPILFE": "核心PCE价格指数（月）",
    "CPIAUCSL": "CPI（月）",
    "UNRATE": "失业率（月）",
    "NROU": "CBO自然失业率（季）",
    # 投资与产出
    "GDP": "名义GDP（季，十亿美元SAAR）",
    "PNFI": "私人非住宅固定投资（季，十亿美元SAAR）",
    "A008RE1Q156NBEA": "非住宅固定投资占GDP（%）",
    "A008RL1Q225SBEA": "实际非住宅固定投资环比折年（%）",
    "A679RC1Q027SBEA": "信息处理设备与软件投资（季，十亿美元SAAR）",
    "Y001RC1Q027SBEA": "知识产权产品投资（季，十亿美元SAAR）",
    "B009RC1Q027SBEA": "非住宅建筑投资（季，十亿美元SAAR）",
    "Y033RC1Q027SBEA": "非住宅设备投资（季，十亿美元SAAR）",
    "A008RD3Q086SBEA": "非住宅固定投资价格指数（季，2017=100）",
}

# Z.1 序列：季度，百万美元；FA=交易流量（季调折年），FL=存量（期末）
Z1 = {
    "FA105000005.Q": "nfc_net_lending",        # 非金融企业净借出(+)/净借入(-)
    "FA105005305.Q": "nfc_financing_gap",      # 融资缺口 = 资本开支 - 内部资金
    "FA105050005.Q": "nfc_capex",              # 资本开支
    "FA104122005.Q": "nfc_debtsec_flow",       # 债务证券净发行
    "FA103163005.Q": "nfc_bond_flow",          # 公司债净发行
    "FA104135005.Q": "nfc_loan_flow",          # 贷款净增
    "FL104122005.Q": "nfc_debtsec_level",
    "FL103163005.Q": "nfc_bond_level",
    "FL104135005.Q": "nfc_loan_level",
    "FA313161105.Q": "ust_flow",               # 可流通美债净发行
    "FL313161105.Q": "ust_level",
    "FA103169100.Q": "nfc_cp_flow",            # 商业票据净发行（短期）
    "FA313161110.Q": "ust_bill_flow",          # 国库券净发行（短期）
    "FA313161275.Q": "ust_coupon_flow",        # 附息国债（中长期票据+债券）净发行
    "FL313161275.Q": "ust_coupon_level",
    "FA713061125.Q": "fed_coupon_flow",        # 美联储净买入附息国债
}

Z1_URL = "https://www.federalreserve.gov/releases/z1/current/z1_csv_files.zip"
ACM_URL = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"
HLW_URL = ("https://www.newyorkfed.org/medialibrary/media/research/economists/williams/data/"
           "Holston_Laubach_Williams_current_estimates.xlsx")


def get(url: str) -> bytes:
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    return r.content


def fetch_fred() -> dict:
    out = {}
    for sid in FRED:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01"
        df = pd.read_csv(io.BytesIO(get(url)), na_values=".")
        df.columns = ["date", sid]
        df["date"] = pd.to_datetime(df["date"])
        df.to_csv(RAW / f"fred_{sid}.csv", index=False)
        out[sid] = df.set_index("date")[sid].dropna()
    return out


def fetch_z1() -> pd.DataFrame:
    zf = zipfile.ZipFile(io.BytesIO(get(Z1_URL)))
    frames = []
    for name in zf.namelist():
        if not (name.startswith("csv/") and name.endswith(".csv")):
            continue
        head = zf.open(name).readline().decode().strip()
        cols = [c for c in Z1 if c in head.split(",")]
        if not cols:
            continue
        df = pd.read_csv(zf.open(name), na_values="ND", usecols=["date"] + cols)
        frames.append(df.set_index("date"))
    z = pd.concat(frames, axis=1)
    z = z.loc[:, ~z.columns.duplicated()][list(Z1)].rename(columns=Z1)
    z.index = pd.PeriodIndex(z.index.str.replace(":", ""), freq="Q")
    z.index.name = "quarter"
    z.to_csv(RAW / "z1_selected.csv")
    return z


def fetch_acm() -> pd.DataFrame:
    raw = get(ACM_URL)
    (RAW / "ACMTermPremium.xls").write_bytes(raw)
    d = pd.read_excel(io.BytesIO(raw), sheet_name="ACM Monthly")
    d["date"] = pd.to_datetime(d["DATE"], format="%d-%b-%Y")
    d = d.set_index("date")[["ACMY10", "ACMTP10", "ACMRNY10"]]
    d.columns = ["acm_y10", "acm_tp10", "acm_rn10"]  # 拟合收益率、期限溢价、风险中性收益率
    return d


def fetch_hlw() -> pd.Series:
    raw = get(HLW_URL)
    (RAW / "HLW_estimates.xlsx").write_bytes(raw)
    d = pd.read_excel(io.BytesIO(raw), sheet_name="HLW Estimates", header=None, skiprows=6)
    s = pd.Series(d.iloc[:, 10].values, index=pd.to_datetime(d.iloc[:, 0]), name="hlw_rstar").dropna()
    return s.astype(float)


def main():
    fred = fetch_fred()
    z1 = fetch_z1()
    acm = fetch_acm()
    hlw = fetch_hlw()

    # ---- 月度面板 ----
    mcols = ["GS10", "GS30", "FEDFUNDS", "TB3MS", "AAA", "BAA", "EXPINF10YR",
             "PCEPILFE", "CPIAUCSL", "UNRATE"]
    m = pd.concat({k: fred[k] for k in mcols}, axis=1)
    m["KWTP10"] = fred["THREEFYTP10"].resample("MS").mean()
    m = m.join(acm.set_axis(acm.index.to_period("M").to_timestamp()))
    m["core_pce_yoy"] = m["PCEPILFE"].pct_change(12, fill_method=None) * 100
    m["cpi_yoy"] = m["CPIAUCSL"].pct_change(12, fill_method=None) * 100
    # 通胀口径：1960 年起用核心 PCE，此前用 CPI
    m["infl_yoy"] = m["core_pce_yoy"].fillna(m["cpi_yoy"])
    m["real10_ex_post"] = m["GS10"] - m["infl_yoy"]
    m["real10_ex_ante"] = m["GS10"] - m["EXPINF10YR"]
    m["aaa_spread"] = m["AAA"] - m["GS10"]
    m["baa_spread"] = m["BAA"] - m["GS10"]
    m.index.name = "date"
    m.to_csv(PROC / "monthly.csv")

    # ---- 季度面板 ----
    q = m.resample("QS").mean()
    qcols = ["GDP", "PNFI", "A008RE1Q156NBEA", "A008RL1Q225SBEA",
             "A679RC1Q027SBEA", "Y001RC1Q027SBEA", "B009RC1Q027SBEA", "Y033RC1Q027SBEA", "A008RD3Q086SBEA", "NROU"]
    q = q.join(pd.concat({k: fred[k] for k in qcols}, axis=1))
    q = q.rename(columns={"A008RE1Q156NBEA": "nonres_share", "A008RL1Q225SBEA": "real_nonres_qoq_saar",
                          "A679RC1Q027SBEA": "info_equip_sw", "Y001RC1Q027SBEA": "ipp",
                          "B009RC1Q027SBEA": "structures", "Y033RC1Q027SBEA": "equipment",
                          "A008RD3Q086SBEA": "nonres_deflator"})
    q["hlw_rstar"] = hlw
    q.index = q.index.to_period("Q")
    q.index.name = "quarter"
    q = q.join(z1)
    gdp_mn = q["GDP"] * 1000  # 十亿美元 -> 百万美元，与 Z.1 对齐
    for c in ["nfc_net_lending", "nfc_financing_gap", "nfc_capex", "nfc_debtsec_flow",
              "nfc_bond_flow", "nfc_loan_flow", "ust_flow", "nfc_cp_flow", "ust_bill_flow",
              "ust_coupon_flow", "fed_coupon_flow"]:
        q[c + "_gdp"] = q[c] / gdp_mn * 100
    for c in ["nfc_debtsec_level", "nfc_bond_level", "nfc_loan_level", "ust_level", "ust_coupon_level"]:
        # 存量 / 年化 GDP
        q[c + "_gdp"] = q[c] / gdp_mn * 100
    q["info_share"] = q["info_equip_sw"] / q["GDP"] * 100
    q["ipp_share"] = q["ipp"] / q["GDP"] * 100
    # 有形投资 = 建筑 + 设备（= 非住宅投资 − 知识产权产品）
    q["tangible_share"] = (q["structures"] + q["equipment"]) / q["GDP"] * 100
    q["structures_share"] = q["structures"] / q["GDP"] * 100
    q["equipment_share"] = q["equipment"] / q["GDP"] * 100
    q["unemp_gap"] = q["UNRATE"] - q["NROU"]
    q.to_csv(PROC / "quarterly.csv")

    # ---- 日度（事件研究用）----
    d = pd.concat({"DGS10": fred["DGS10"], "DGS30": fred["DGS30"],
                   "KWTP10": fred["THREEFYTP10"]}, axis=1)
    d.index.name = "date"
    d.to_csv(PROC / "daily.csv")

    print("monthly", m.index.min().date(), m.index.max().date(), m.shape)
    print("quarterly", q.index.min(), q.index.max(), q.shape)
    print("daily", d.index.min().date(), d.index.max().date(), d.shape)


if __name__ == "__main__":
    main()
