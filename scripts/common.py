"""绘图与回归的公共工具。"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"
OUT = ROOT / "output"
FIG.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# 参考调色板（dataviz 技能默认实例，已通过色盲校验的前三槽）
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
SHADE = "#efeee9"

plt.rcParams.update({
    "font.family": ["WenQuanYi Zen Hei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": INK2,
    "axes.labelcolor": INK2,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "lines.linewidth": 2,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlecolor": INK,
    "axes.titlelocation": "left",
    "legend.frameon": False,
})


def load_q() -> pd.DataFrame:
    q = pd.read_csv(PROC / "quarterly.csv", index_col=0)
    q.index = pd.PeriodIndex(q.index, freq="Q")
    return q


def load_m() -> pd.DataFrame:
    return pd.read_csv(PROC / "monthly.csv", index_col=0, parse_dates=True)


def load_d() -> pd.DataFrame:
    return pd.read_csv(PROC / "daily.csv", index_col=0, parse_dates=True)


def save(fig, name: str, source: str):
    fig.text(0.01, -0.01, f"资料来源：{source}", fontsize=8, color=INK2, ha="left", va="top")
    fig.savefig(FIG / f"{name}.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def ols_nw(y: pd.Series, X: pd.DataFrame, lags: int = 4):
    """带常数项的 OLS，Newey-West 标准误。"""
    d = pd.concat([y, X], axis=1).dropna()
    res = sm.OLS(d.iloc[:, 0], sm.add_constant(d.iloc[:, 1:])).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags})
    return res, d.index.min(), d.index.max(), len(d)


def stars(p: float) -> str:
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def fmt_coef(res, name: str, scale: float = 1.0, digits: int = 1) -> str:
    b, t, p = res.params[name] * scale, res.tvalues[name], res.pvalues[name]
    return f"{b:.{digits}f}{stars(p)} (t={t:.2f})"


def to_ts(idx) -> np.ndarray:
    """PeriodIndex -> 时间戳，便于绘图。"""
    return idx.to_timestamp() if isinstance(idx, pd.PeriodIndex) else idx
