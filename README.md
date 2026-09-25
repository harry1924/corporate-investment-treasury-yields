# 企业投资与长久期融资如何影响美债利率

研究进度：构思框架已完成，**第一轮数据分析已完成**（投资与利率、融资与利率）。

## 目录

| 文件 | 内容 |
|---|---|
| [`REPORT.md`](REPORT.md) · [`REPORT.pdf`](REPORT.pdf) · [`REPORT.html`](REPORT.html) | **总报告：摘要、两部分分析、16 张图、结论与观察清单（PDF / 高清 HTML 可下载）** |
| [`01-framework.md`](01-framework.md) | 核心问题、四条传导渠道、可检验假说 |
| [`02-episodes.md`](02-episodes.md) | 历史样本：六个阶段的事实框架与待核验清单 |
| [`03-outline.md`](03-outline.md) | 长篇研报提纲（标题、摘要、章节、图表标题） |
| [`04-data-plan.md`](04-data-plan.md) | 数据口径、序列代码、实证设计 |
| [`05-literature.md`](05-literature.md) | 文献地图 |
| [`06-analysis-investment.md`](06-analysis-investment.md) | **分析一：企业投资与美债利率** |
| [`07-analysis-financing.md`](07-analysis-financing.md) | **分析二：企业融资与美债利率** |
| `scripts/` | 数据下载与分析脚本 |
| `data/processed/` | 季度 / 月度 / 日度面板 |
| `figures/` | 图表（16 张） |
| `output/` | 脚本自动生成的数字结果 |

## 第一轮分析的主要发现

**投资对美债利率的影响主要借道政策利率。** 实际非住宅投资同比每上升 1 个点，联邦基金利率上行 16.1bp，10 年期美债上行 4.1bp；10 年期的上行全部来自预期短端利率（+6.8bp），期限溢价反向下行 3.6bp。

**投资对长端利率的传导逐代减弱。** 10 年期对投资增速的弹性由 1962—1984 年的 5.9bp 降至 2008—2026 年的 1.2bp。

**2022 年以来的投资上行期，是 1982 年以来首次期限溢价同步抬升的一轮（+139bp）。** 1992—2000 年、2010—2019 年两轮投资扩张期，期限溢价分别下行 306bp、317bp。

**企业外部融资需求与实际利率同向（1985 年以来相关系数 0.47），但企业部门整体仍在用内部资金覆盖资本开支。** 2026Q2 融资缺口为 −1.10% GDP，AI 融资尚未改变总量格局。

**长久期发债的供给冲击量级有限。** 14 笔超大额发行前后 7 个交易日，30 年期美债平均上行 5.1bp（t=1.49），统计上不成立；季度流量回归中供给效应被发行择时掩盖。

## 对构思阶段假说的修正

构思阶段提出“企业部门由净储蓄者转为净借款人”。Z.1 总量数据显示这一回摆尚未发生，该判断需下调为：**AI 融资集中于个别发行人，影响或更多体现在个券长久期供给与表外结构上，总量层面的实际利率压力要等融资缺口转正并扩大后才会出现。**

## 复现

```bash
pip install -r requirements.txt
python scripts/fetch_data.py          # 下载 FRED、美联储 Z.1、纽约联储 ACM / HLW
python scripts/analysis_investment.py # 分析一
python scripts/analysis_financing.py  # 分析二
python scripts/financing_gap_long.py  # 融资缺口长序列（1929 年起）
python scripts/build_report.py        # 合并为 REPORT.md
```

## 下一步

1. 补齐企业债发行期限结构（SIFMA / FINRA TRACE），构造久期加权供给。
2. 扩大事件研究样本至单笔 ≥100 亿美元，加入 30 年期 SOFR 互换利差，逐笔核验定价日期。
3. 单独整理超大型科技公司的资本开支、经营现金流与发债数据。
4. 以 AI 相关投资分项（信息处理设备、数据中心、电力设备）检验投资—利率弹性。
