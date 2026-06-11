我来分析这个宏观监控项目。先用并行探索代理摸清代码库结构、数据源和计算逻辑。

核验全部完成。所有关键问题已确认（其中两项探索代理的说法被我推翻——`mean_parkinson_vol` 实际有保护、Nasdaq 取数并无 Referer 伪装）。以下是完整分析报告。

---

# MarcoMonitor 代码库分析：数据源可靠性、时效性与信号指导性

**TLDR：** 这套系统工程质量不错（原子写入、拍卖/FOMC 双源备援、前视保护意识都在），但有三个高优先级问题：① **Nasdaq 非官方 API 是全部 20 个股票符号和全部 6 个 LPPL 指数的单点故障**，而现成的 Stooq 备援函数没有接上；② **慢频数据源（ACM/CFTC/TIC）无论多旧都标 "ok"**，时效性判断只覆盖了股票日线；③ **LPPL 选参逻辑按"风险分最高"而非"拟合最好"挑候选，系统性高估泡沫风险**，且短期风险回测是内样本的——面板上显示的命中率大概率高于真实水平。这三点直接影响"计算结果能不能信"。

---

## 一、数据源可靠性

### 🔴 P0：Nasdaq API 单点故障

[sources.py:596](the-dial-treasury-v1/treasury_data/sources.py:596) 的 `fetch_nasdaq_daily_bars` 是唯一的股票日线来源：`retries=1`、14 秒超时、伪装浏览器 UA 的**非官方接口**（Nasdaq 随时可能收紧反爬）。依赖它的有：

- 短期股票风险的全部 9 个组件（SPY/QQQ/TLT/板块 ETF/9 只热门股）
- [build_dashboard.py:355-416](the-dial-treasury-v1/treasury_data/build_dashboard.py:355) 的 `GLOBAL_LPPL_INDEX_SPECS`——**6 个 LPPL 指数全部 `source: "nasdaq"`**

讽刺的是，[sources.py:513](the-dial-treasury-v1/treasury_data/sources.py:513) 已经有 `fetch_stooq_daily_bars`，[build_dashboard.py:602-605](the-dial-treasury-v1/treasury_data/build_dashboard.py:602) 也已有 stooq 分支，**但没有任何 spec 使用它，也没有作为 Nasdaq 失败后的备援**。这是性价比最高的修复。

### 🟠 其他可靠性缺口

| 问题 | 位置 | 影响 |
|---|---|---|
| 国债收益率曲线仅依赖财政部 XML，无 FRED DGS 备援 | sources.py 曲线抓取 | 曲线是仪表盘核心内容，挂了整页降级 |
| FRED 批量取数按 12 个一组分块，**任一块失败则整批异常**，无逐块隔离重试 | [sources.py:736-743](the-dial-treasury-v1/treasury_data/sources.py:736) | 一次网络抖动丢掉全部 43 个宏观序列 |
| 联邦基金期货、黄金报价仅依赖 Stooq（第三方聚合站），无备援 | sources.py:529-534 | 喂给早期预警的利率预期信号 |
| 前端健康轮询失败时固定快频重试，无指数退避 | [app.js:629-643](the-dial-treasury-v1/app.js:629) | 服务端持续故障时无意义地高频打点 |

---

## 二、时效性

**做得好的**：股票日线有完整的新鲜度状态机（waiting/fresh/stale/catchup，纽约交易日历感知，serve.py:368-422），前端有新鲜度药丸和追赶模式。这部分不用动。

**缺口在宏观侧**——[build_dashboard.py:505-530](the-dial-treasury-v1/treasury_data/build_dashboard.py:505) 我逐条核验过：每个数据源只要"取到了"就标 `"status": "ok"`，**没有任何地方比对数据日期与预期更新节奏**：

- ACM 期限溢价（月更、滞后 10+ 天）、CFTC 持仓（周更、滞后 5-7 天）、TIC 外资持仓（滞后 30+ 天）——哪怕数据已经停更三个月，状态照样是 "ok"
- 页面显示的 `generatedAt` 是**快照构建时间**，不是数据本身的时间；用户看到"2 小时前生成"，无法分辨曲线其实是昨天的、TIC 其实是两个月前的

这对一个宏观监控工具是实质性缺陷：**时效性失效是静默的**。

---

## 三、计算结果对股市的指导性

这是最值得投入的部分。核心发现有三个：

### 🔴 1. LPPL 选参偏差：挑的是"最吓人"的拟合，不是"最好"的拟合

[build_dashboard.py:3520](the-dial-treasury-v1/treasury_data/build_dashboard.py:3520) 网格内选候选、[3444](the-dial-treasury-v1/treasury_data/build_dashboard.py:3444) 跨窗口选结果，**都是 `max(..., key=score)`**——即在 140 个网格候选 × 3 个窗口中挑风险分最高的那个展示给用户。而 `raw_score` 里 `critical_score` 占 24% 权重且随 `tc_offset` 变近而暴涨（tc=15 天贡献 ≈23 分，tc=170 天仅 ≈1.4 分，[3488](the-dial-treasury-v1/treasury_data/build_dashboard.py:3488)）。后果：

- 只要近临界日候选的 R² 不太差，搜索就会选它 → **"距临界 15 天"很可能只是目标函数的倾向，不是数据的结论**
- `daysToCritical` 只能取 `{15,25,40,60,90,130,170}` 七个离散网格值（[3455](the-dial-treasury-v1/treasury_data/build_dashboard.py:3455)），展示成精确天数是假精度
- 置信度公式 [3499](the-dial-treasury-v1/treasury_data/build_dashboard.py:3499) 的 `osc/max(|bubble_coef|, 1e-6)` 在系数趋零时退化
- 无样本外验证、无跨窗口分歧度展示

**正确姿势**：按拟合质量（R²/SSE）选参，从该拟合推导风险分；用三个窗口的 tc 离散度给出区间（如"临界窗口 25–60 天"）而非点估计。

### 🔴 2. 短期风险回测是内样本的，面板显示的命中率偏乐观

- 历史回放（[5423-5433](the-dial-treasury-v1/treasury_data/build_dashboard.py:5423)）把**当前**的 `spy_early_warning` 和宏观快照传给每一个历史日期——`macroOverlay` 组件（[4612-4634](the-dial-treasury-v1/treasury_data/build_dashboard.py:4612)）在回放里全程用今天的分数。权重虽只有 0.03，但污染了回测
- 更重要的是：`calibrationGrid`、`recommendedCautionThreshold` 等阈值校准与 precision 报告用的是**同一段数据**——典型的内样本评估。回测框架本身做得很丰富（分桶、聚类告警、最差窗口分析都有），缺的只是一个 walk-forward 切分
- **没有基准率对照**：面板告诉用户"≥75 分后 10 日回撤 ≥2% 的命中率 X%"，但不告诉用户任意一天的无条件概率是多少。没有 lift，命中率数字无法解读

### 🟠 3. 评分函数的局部问题

- **turnover 组件跳变**（[4541-4549](the-dial-treasury-v1/treasury_data/build_dashboard.py:4541)，已核验）：成交量分位从 45→46，`thin_breakout` 条件失效，分数从 78 直接跌到 25。一个百分位的噪声造成 53 分摆动，会让该组件（权重 0.14）在边界附近反复翻转
- **热门股反转小样本不稳**：热门股只有 1-2 只时 `reversal_share` 只能取 0 或 1，极端化
- **大量硬编码阈值无敏感性记录**：`risk_linear(qqq_pressure, 0.95, 1.85)`、hedge_failure 基分 82、crowded_rollover 基分 76、11 条减震规则链……这些可能是对着近期行情手调的，换个波动率体制就漂移。不一定是错的，但**没有校准流程**意味着无法复现、无法验证

### ✅ 经核验不是问题的（探索代理误报，已推翻）

- `mean_parkinson_vol` 的空列表除法——实际有 `len(values) < window` 保护（[6270](the-dial-treasury-v1/treasury_data/build_dashboard.py:6270)）
- 事件风险组件"前视"——经济日历本来就是提前公布的，用未来 1-5 天的已知事件**不是**前视偏差，且权重仅 0.01
- 作者已有前视保护意识：optionOI 快照晚于信号日则拒用（[4640](the-dial-treasury-v1/treasury_data/build_dashboard.py:4640)），且把易污染组件权重刻意压到 0.03/0.01/0.00

---

## 四、优化方案（按优先级）

### P0 — 数据层加固（约 1-2 天，低风险高回报）

1. **Nasdaq→Stooq 日线备援链**：在 [build_dashboard.py:568](the-dial-treasury-v1/treasury_data/build_dashboard.py:568) 和 `update_equity_risk.py` 的取数循环外包一层 try——Nasdaq 失败则用现成的 `fetch_stooq_daily_bars`（需加符号映射 `SPY→spy.us`）；给 spec 增加 `fallbackSymbol` 字段；sourceStatus 记录"已降级到 stooq"
2. **收益率曲线 FRED DGS 备援**：XML 失败时用已有 FRED 批量取数器拉 DGS1MO…DGS30 拼曲线，标记 sourceQuality 降级
3. **FRED 分块故障隔离**：逐块 try/except + 单块重试，失败块的系列显式列入 sourceStatus，不拖垮其余块
4. **时效性目录**：新增 `EXPECTED_SOURCE_CADENCE = {"NY Fed ACM term premium": 45, "CFTC financial futures COT": 10, ...}`（单位天），构建后统一后处理 source_status：计算 `ageDays`，超限自动降级为 `stale`；前端源状态模态框已有表格，加一列"数据年龄/预期"即可

### P1 — 信号方法论（约 2-4 天，直接提升指导性）

5. **LPPL 修正**（最重要）：选参改为按 R² 最优；`daysToCritical` 改为输出跨窗口区间 `daysToCriticalRange`（新增字段，schema 向后兼容）；修复置信度退化项；新增合成数据测试——已知 tc 的 LPPL 生成序列要能还原参数、随机游走序列分数必须保持低位（误报防护）
6. **回测去污染 + 样本外评估**：回放模式下剔除 `macroOverlay`（权重自动重归一，现有 ≥3 组件逻辑已支持），或从 `history.sqlite3` 读历史宏观分；回测加 70/30 walk-forward 切分，报告 OOS precision/recall；**在配置建议卡片旁附基准率对照**（"该分数段历史回撤概率 X% vs 无条件 Y%"）——这一条是把"分数"变成"可解读的概率"的关键
7. **turnover 平滑过渡**：在分位 42-48 之间做线性渐变，消除 53 分跳变
8. **热门股小样本保护**：`hot_count < 3` 时向 50 收缩

### P2 — 工程与展示（约 1 天）

9. 前端轮询指数退避（连续失败计数，上限 10 分钟）
10. `CONCLUSION_SOURCE_QUALITY` 在 app.js 与 build_dashboard.py 双处定义——改为 dashboard.json 下发，前端消费
11. 文档注明 Nasdaq 非官方 API 风险；Stooq 报价失败时的降级标注

### 统一验证方式

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 -m unittest discover -s the-dial-treasury-v1/tests
python3 the-dial-treasury-v1/scripts/update_data.py   # 全量刷新 + smoke_check 合同校验
```

备援链用注入失败 fetcher 的单测覆盖（现有 `test_update_equity_risk.py` 已有 fetcher 参数化模式可复用）；改动 app.js/styles.css 需同步 bump index.html 的 cache-bust 版本号（注意当前工作区有未提交的 LPPL 全宽布局改动，实施时基于其上，不要回退）。

---

**一句话总结**：数据侧最大的洞是"Nasdaq 单点 + 慢频数据静默过期"，信号侧最大的洞是"LPPL 挑最吓人的拟合 + 回测内样本无基准率"。P0+P1 大约 3-6 天工作量，完成后这个面板从"展示分数"升级为"展示可信度可解读的分数"。如果你想动手，我建议从 P0-1（Stooq 备援）和 P1-5（LPPL 选参）开始——前者防猝死，后者直接决定 LPPL 面板还值不值得看。需要我开始实施的话告诉我从哪部分入手。