"""把分析一、分析二合并为总报告 REPORT.md，并生成内嵌图片的 HTML 版本。

用法：python scripts/build_report.py [HTML 输出路径]
"""
import base64
import io
import re
import sys
from pathlib import Path

import markdown
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

CAPTIONS = {
    "inv_01_share_vs_yields": "投资上行期多伴随利率上行，但 2010 年后的投资扩张未能扭转利率下行趋势",
    "inv_10_era_correlation": "1984 年前投资与长端利率联动更强，近十年联动回升",
    "inv_02_episode_decomposition": "投资上行期预期短端利率普遍抬升，期限溢价方向不定",
    "inv_03_regression_coefs": "投资提速主要推升政策利率，对期限溢价的影响为负",
    "inv_04_lead_lag": "投资增速与政策利率同步变化，对长端利率的领先性较弱",
    "inv_05_intangibles_rstar": "投资结构转向无形资产的同时，中性利率趋势下行",
    "inv_06_tangible_vs_rates": "有形投资与名义利率长期同向，2008 年后联动减弱",
    "inv_07_tangible_scatter": "2008 年前有形投资与名义利率正相关，2008 年后关系消失",
    "inv_08_capex_cagr_vs_yield": "剔除通胀后，资本开支增速与美债收益率的同步性基本消失",
    "inv_09_cagr_corr": "与美债收益率同步的主要是名义增长，资本开支本身的解释力有限",
    "fin_01_financing_gap": "2000 年代以来企业内部资金多数时间覆盖资本开支，外部融资需求收缩",
    "fin_02_supply_regression": "季度流量数据中，公司债净发行对长端利率的推升效应不可识别",
    "fin_03_stocks": "1952—1984 年美债/GDP 持续下行，2008 年后美债与企业债同步扩张",
    "fin_04_flight_to_quality": "信用利差走阔时美债收益率倾向下行，避险关系强弱随时期变化",
    "fin_05_event_study": "超大额企业发债前后，30 年期美债收益率变化多落在正常波动区间内",
}

CN = "一二三四五六七八九十"

HEADER = """# 企业投资会抬升美债利率吗？
——企业投资、长久期融资与美债利率的历史复盘

## 摘要

2000 年代以来，美国企业部门长期处于资金盈余状态，企业储蓄是长端利率低位运行的因素之一。2025 年起，超大型科技公司为 AI 资本开支集中发行长久期债券，市场开始讨论企业部门是否会成为美债利率的新推升力量。但历史上企业投资与融资对美债的影响，渠道与量级差异较大。企业投资通过哪条渠道影响美债？长久期发债能否与美债争夺久期买盘？本轮 AI 周期与历史相比有何不同？

**投资对美债利率的影响主要借道政策利率。** 实际非住宅投资同比每上升 1 个点，联邦基金利率四季度变化上行 16.1bp，10 年期美债上行 4.1bp；10 年期的上行全部来自预期短端利率（+6.8bp），期限溢价反向下行 3.6bp。

**有形投资与利率的联动强于投资总量，但 2008 年后同样减弱。** 建筑与设备投资/GDP 与 10 年期名义利率的全样本水平相关系数为 0.79，1953—1984 年为 0.88，2008—2026 年转为 −0.13；知识产权产品投资与利率变化基本无关。

**“资本开支增速与债券收益率高度同步”的图表，主要反映名义增长。** 以美国数据复现，1986—2026 年名义资本开支 5 年年化增速与 10 年期美债的相关系数为 0.21，剔除价格后为 0.11，名义 GDP 增速为 0.76。

**企业外部融资需求与实际利率同向，但企业部门整体仍在用内部资金覆盖资本开支。** 1985 年以来融资缺口/GDP 与 10 年期实际利率的相关系数为 0.47；2026Q2 融资缺口为 −1.10% GDP，AI 融资尚未改变总量格局。

**长久期发债的供给冲击量级有限。** 14 笔单笔 150 亿美元以上的企业发行，定价前后 7 个交易日 30 年期美债平均上行 5.1bp（t=1.49），落在 12.7bp 的正常波动区间内。

**2022 年以来的投资上行期，是 1982 年以来首次期限溢价同步抬升的一轮。** 本轮期限溢价上行 139bp，贡献了 10 年期上行 248bp 中的一半以上；有形投资/GDP 为 8.47%，仍低于 2019 年，AI 资本开支若推动有形投资回升，名义利率的上行压力或重新显现。
"""

FOOTER = """
# 三、结论与观察清单

**企业部门影响美债利率的五条渠道，历史证据强弱不一：** 一是政策利率渠道，投资增速与联邦基金利率变化的相关系数稳定在 0.5—0.7，证据最强；二是名义增长渠道，名义 GDP 增速与 10 年期美债的相关系数为 0.76—0.83；三是外部融资需求渠道，融资缺口与实际利率同向（0.47）；四是久期供给渠道，季度回归与事件研究均未识别出统计上成立的推升效应，量级或在数个 bp 以内；五是避险渠道，信用利差与美债收益率长期负相关，但近年减弱。

**对当前的判断：** AI 资本开支目前集中在知识产权产品与少数现金充裕的发行人，有形投资占比与企业融资缺口两项总量指标均未显示扩张。本轮美债期限溢价上行的主因或在财政与通胀，企业部门的贡献有限。若有形投资/GDP 回升至 9% 以上、融资缺口转正并扩大至 1% GDP 以上，企业部门对美债利率的推升或由“边际”转为“系统性”。

**未来两个季度，重点观察三点：** 一是 BEA 分项中信息处理设备、数据中心建筑、电力设备投资的增速，判断有形投资是否回升；二是美联储 Z.1 的非金融企业融资缺口，判断企业部门是否转向外部融资；三是超大型科技公司的季度资本开支指引与长久期发行节奏，结合 30 年期美债与 SOFR 互换利差观察发行窗口的定价反应。

**证伪条件：** 若有形投资占比持续回升而 10 年期名义利率与期限溢价同步回落，“有形投资推升名义利率”的历史关系在本轮失效；若超大型科技公司大额发行周内 30 年期互换利差与美债收益率均未出现可识别变化，久期供给渠道的判断需进一步下调。

**风险提示：** AI 资本开支不及预期；美联储降息节奏超预期；信用事件冲击超预期。

# 附录：数据与方法

- 数据：FRED（利率、BEA 投资与 GDP、通胀）；美联储 Z.1 金融账户（S.11.1 非金融企业、F.3.2 美债）；纽约联储 ACM 期限溢价模型、HLW 中性利率估计。季度数据截至 2026Q2，月度截至 2026 年 8 月，日度截至 2026 年 9 月。
- 方法：投资周期以非住宅投资/GDP 四季度均值拐点划分（阈值 0.8 个点）；回归使用 Newey-West 标准误；事件研究窗口为定价日前 3 至后 3 个交易日，发行日期来自公开报道整理，需逐笔核验。
- 复现：`pip install -r requirements.txt && python scripts/fetch_data.py && python scripts/analysis_investment.py && python scripts/analysis_financing.py && python scripts/build_report.py`
- 分项结果：[`06-analysis-investment.md`](06-analysis-investment.md)、[`07-analysis-financing.md`](07-analysis-financing.md)、[`output/`](output/)。
"""


def body(path: Path) -> str:
    """去掉标题、数据说明、核心结论与小结，只保留正文各节，并把 ## 一、 改为 ## （一）。"""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## ", text)
    keep = [p for p in parts[1:] if not p.startswith(("核心结论", "五、小结", "六、小结"))]
    out, k = [], 0
    for p in keep:
        title, rest = p.split("\n", 1)
        title = re.sub(r"^[一二三四五六七八九十]+（[^）]*）、|^[一二三四五六七八九十]+、", "", title)
        out.append(f"## （{CN[k]}）{title}\n{rest}")
        k += 1
    return "".join(out)


def main():
    inv = body(ROOT / "06-analysis-investment.md")
    fin = body(ROOT / "07-analysis-financing.md")
    md = (HEADER + "\n# 一、企业投资与美债利率\n\n" + inv
          + "\n# 二、企业融资与美债利率\n\n" + fin + FOOTER)

    n = 0

    def fig(m):
        nonlocal n
        n += 1
        key = Path(m.group(1)).stem
        return f"**图{n}：{CAPTIONS[key]}**\n\n![图{n}]({m.group(1)})"

    md = re.sub(r"!\[[^\]]*\]\((figures/[^)]+)\)", fig, md)
    # 正文中的“图1”等旧编号已随图片替换，无需另行处理
    (ROOT / "REPORT.md").write_text(md, encoding="utf-8")
    print(f"REPORT.md：{n} 张图")

    if len(sys.argv) > 1:
        html_body = markdown.markdown(md, extensions=["tables"])

        def embed(m):
            # 压缩为 256 色 PNG 并限制宽度，保证 HTML 体积可在预览面板中完整加载
            im = Image.open(ROOT / m.group(2)).convert("RGB")
            if im.width > 1200:
                im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
            buf = io.BytesIO()
            im.quantize(colors=96, method=Image.Quantize.MEDIANCUT).save(buf, "PNG", optimize=True)
            b = base64.b64encode(buf.getvalue()).decode()
            return f'<img alt="{m.group(1)}" src="data:image/png;base64,{b}"'

        html_body = re.sub(r'<img alt="([^"]*)" src="([^"]+)"', embed, html_body)
        html_body = html_body.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
        css = """
:root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e6e5e0;--accent:#2a78d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--line:#3a3a38;--accent:#3987e5}}
:root[data-theme="dark"]{--bg:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--line:#3a3a38;--accent:#3987e5}
body{background:var(--bg);color:var(--ink);font-family:"PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;line-height:1.8;margin:0;padding:24px 16px}
main{max-width:920px;margin:0 auto}
h1{font-size:1.5rem;border-bottom:2px solid var(--accent);padding-bottom:.3em;margin-top:1.8em}
h1:first-child{font-size:1.9rem;border:0;margin-bottom:0}
h2{font-size:1.15rem;margin-top:1.8em}
img{max-width:100%;height:auto;border-radius:6px;margin:.3em 0 1em;background:#fcfcfb}
.tw{overflow-x:auto}table{border-collapse:collapse;font-size:.85rem;margin:.8em 0;white-space:nowrap}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:right}th:first-child,td:first-child{text-align:left}
th{color:var(--ink2);font-weight:600}code{font-size:.85em;color:var(--ink2);white-space:normal}
"""
        html = (f'<!doctype html><html lang="zh"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>企业投资与美债利率</title><style>{css}</style></head>'
                f'<body><main>{html_body}</main></body></html>')
        Path(sys.argv[1]).write_text(html, encoding="utf-8")
        print(f"HTML：{sys.argv[1]}（{len(html) // 1024} KB）")


if __name__ == "__main__":
    main()
