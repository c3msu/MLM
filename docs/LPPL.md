下面是可直接转成实施方案的版本。核心结论是：**对美股、韩国股市、台湾股市、香港股市，不建议只跑单一 LPPL 曲线；应做“多窗口 + 多优化器 + 参数过滤 + 残差检验 + 临界时间聚合 + 市场宽度确认”的系统。** 单次拟合只能作为候选信号，不能作为风险预警结论。

知乎文章可检索摘要显示，它把 LPPL 公式拆成两部分理解：一部分是 **power law**，一部分是 **log-periodic**；并提到第一部分可看作 (A+Bt^m)，且 (0<m<1) 是为了保证在 (t_c) 附近收敛。([知乎专栏][1]) 附件论文则给出更完整的实施框架：原始 JLS/LPPL 方程、参数约束、2-step 非线性优化、遗传算法、2-step/3-step ML、ADF/KPSS 残差检验、随机终止时间诊断和 Crash Lock-In Plot。

---

## 0. 当前代码库落地状态

当前 `the-dial-treasury-v1` 已把本文的完整研究方案收敛成一个可部署的
`globalLpplRisk` 指数/ETF 代理层，不是全市场个股扫描平台。按本文 16 个
核心模块拆分，当前看板层覆盖或部分覆盖 10 项；其中本次已补齐 4 个直接
影响当前 payload 契约的缺口。

| 模块 | 当前状态 |
| --- | --- |
| 线性化 LPPL 主模型 | 已覆盖：使用对数价格、给定 `(tc,m,omega)` 后 OLS 解 `A,B,C1,C2`。 |
| 多窗口 | 已补齐：日常窗口为 `120/180/252/375/500/750` 个交易日；快速历史回放仍使用单窗口以控制运行时间。 |
| 参数过滤 | 已覆盖：约束未来 `tc`、`m/omega` 网格、`B<0`、LPPL 相对 power-law 改善、振荡次数和趋势加速。 |
| 残差检验 | 部分覆盖并已补齐契约：输出 `adfProxyPass`、`kpssProxyPass`、`ljungBoxProxyPass`，目前是 lag-1 自相关、符号翻转和低残差方差的启发式 proxy，不是 `statsmodels` 的正式 ADF/KPSS/Ljung-Box。 |
| 临界时间聚合 | 已补齐：每个指数行输出 `fitEnsemble` 和日期化 `tcAggregation`，含 `tcQ20/tcMedian/tcQ80`、有效窗口数、残差通过率和窗口一致性。 |
| CLIP | 已覆盖：逐市场 `history.points` 保留 replayed `criticalDate`，`clipState` 判断 scattered/converging/locked。 |
| 预警分数 | 部分覆盖：当前保留 raw LPPL score，并用 validation、multi-window ensemble 与 residual proxy pass rate 加权 `forwardSignal`；尚未把 full formula 的 `S_breadth` 反向写入 raw score。 |
| 市场宽度确认 | 已补齐当前范围：顶层 `breadthConfirmation` 基于 6 个市场/ETF 代理统计 raw risk、forward risk、CLIP lock 和加权风险宽度。 |
| 逐市场回测 | 已覆盖当前范围：每个可用指数有 own-market 5/10/15/20D forward drawdown audit、threshold grid 和 alert cluster test。 |
| 数据源与复权 | 部分覆盖：使用 Nasdaq daily rows，失败时 Stooq fallback；当前 ETF/指数代理不等同于 CRSP/HKEX/TWSE/KRX 研究级复权个股数据。 |
| 全市场个股池 | 未覆盖：CRSP/Russell 3000、KRX/TWSE/TPEX/HKEX 成分与高成交额个股扫描仍是后续工程。 |
| 多优化器 | 未覆盖：当前是确定性网格 + OLS，不含 differential evolution、LM/BFGS 精修或多 optimizer agreement。 |
| 微观结构/资金流 | 未覆盖：外资、融资融券、南向、short turnover、options IV 等仍未接入 LPPL 主模型。 |

因此，当前代码库和本文完整方案的差距不是“公式未实现”，而是**从指数级
风险层扩展到研究级全市场平台**的差距。当前看板已经不再是单资产单窗口
LPPL；仍未完成的是个股 universe、研究级复权数据、正式统计检验和多优化器。

---

## 1. 最适合四个市场统一落地的 LPPL 主模型

建议主模型采用对数价格形式：

[
y(t)=\ln P(t)
]

[
y(t)=A+B(t_c-t)^m+C(t_c-t)^m\cos[\omega\ln(t_c-t)+\phi]
]

其中：

| 参数            | 含义                | 实施解释                                    |
| ------------- | ----------------- | --------------------------------------- |
| (A)           | (t_c) 附近的理论对数价格水平 | 不是估值目标，只是拟合参数                           |
| (B)           | 主趋势方向             | (B<0)：上涨泡沫；(B>0)：下跌泡沫或恐慌下跌              |
| (m) / (\beta) | 幂律加速指数            | 要求 (0<m<1)，实务中用 (0.1<m<0.9)             |
| (C)           | 对数周期振荡幅度          | 控制围绕幂律趋势的振荡强弱                           |
| (\omega)      | 对数周期频率            | 实务中用 (6\le \omega \le 15)               |
| (\phi)        | 相位                | 纯拟合参数，经济含义弱                             |
| (t_c)         | 临界时间              | 可能是顶部、底部、平台切换、波动率 regime change，不一定是暴跌日 |

论文原式也指出，LPPL 的核心是价格在 (t_c) 前表现为幂律加速，并叠加对数周期振荡；其中 (B<0)、(0<\beta<1)、(0<\phi<2\pi) 等条件用于描述上涨泡沫接近临界点的形态。

为了提高数值稳定性，建议代码中使用等价的线性化形式：

[
y(t)=A+B\tau^m+C_1\tau^m\cos(\omega\ln\tau)+C_2\tau^m\sin(\omega\ln\tau)
]

[
\tau=t_c-t
]

这样可以把 (\phi) 隐含进 (C_1,C_2)，使非线性参数从 ((t_c,m,\omega,\phi)) 变成 ((t_c,m,\omega))，更适合批量扫描美股、韩国、台湾、香港个股。

---

## 2. 为什么四个市场都应使用“对数复权价格”

LPPL 应拟合的是连续价格路径。单只股票存在拆股、送股、现金分红、配股、除权、合股、红股、特别股息等跳变，直接用未复权价格会把公司行为误判成崩盘或反弹。

实施建议：

| 对象         | 拟合价格                     |
| ---------- | ------------------------ |
| 指数         | 优先用价格指数；如需跨市场比较，再补充总回报指数 |
| 个股         | 必须用前复权或总回报复权价格           |
| ETF        | 用复权净值或复权收盘价              |
| ADR / 双重上市 | 本地股和 ADR 分开拟合，再做同步验证     |
| 跨市场统一看板    | 本地货币版本为主，美元换算版本为辅        |

美股数据首选 CRSP，因为其美国股票数据库覆盖 NYSE、NYSE American、NYSE Arca、NASDAQ、Cboe BZX，并提供日/月度市场数据与公司行为，且强调 survivor-bias-free 历史。([Center for Research in Security Prices][2]) 台湾和香港官方数据源也能拿到日收盘价、成交量、成交额等字段；台湾政府开放资料平台列明有 TWSE 上市股票日收盘价和月平均价资料集，HKEX 的 Day-end Closing Data 提供每日 High、Low、Close、turnover 等数据。([政府資料開放平臺][3])

---

## 3. 总体计算流程

### Step 1：确定扫描对象

分两层跑。

第一层是**市场指数和行业指数**，用于判断系统性泡沫：

| 市场 | 指数池                                                           |
| -- | ------------------------------------------------------------- |
| 美股 | S&P 500、Nasdaq Composite、Nasdaq 100、Russell 2000、SOX、重要主题 ETF |
| 韩国 | KOSPI、KOSDAQ、KOSPI 200、KOSDAQ 150、半导体/电池相关指数                  |
| 台湾 | TAIEX、电子指数、半导体指数、AI 服务器/PCB/光电相关篮子                            |
| 香港 | HSI、HSCEI、HSTECH、红筹/内房/互联网/券商/生物科技篮子                          |

第二层是**个股池**，用于找局部泡沫和拥挤风险：

| 市场 | 个股筛选                                                  |
| -- | ----------------------------------------------------- |
| 美股 | CRSP 普通股；或 Russell 3000 + ADR + 高流动性主题股               |
| 韩国 | KOSPI 200、KOSDAQ 150、成交额前 300                         |
| 台湾 | TWSE + TPEX 成交额前 300，重点加入半导体、PCB、散热、AI 服务器链           |
| 香港 | Main Board 成交额前 300，重点加入 HSTECH、南向高持仓、中概回港、AI/消费/医药主题 |

必须加流动性过滤，否则 LPPL 会在低流动性个股上产生大量假信号。建议门槛：

[
ADTV_{60} > 100万美元
]

或按本地货币设等价门槛。香港小票、台湾柜买小票、韩国 KOSDAQ 小票尤其需要这个过滤。

---

### Step 2：构建时间窗口

附件论文在黄金泡沫案例中使用 shrinking windows 和 expanding windows，并以 5 个交易日为步长改变窗口，同时对不同算法得到的 (t_c) 做分位数区间统计。 这个方法适合直接迁移到四个市场。

建议窗口设计：

| 类型     | 用途           | 参数                           |
| ------ | ------------ | ---------------------------- |
| 滚动窗口   | 日常监控         | 120、180、250、375、500、750 个交易日 |
| 扩展窗口   | 检查从低点以来的完整泡沫 | 从近 1–3 年局部低点开始，到当前日          |
| 收缩窗口   | 检查起点敏感性      | 固定当前日，起点每 5 或 10 个交易日向后移动    |
| 指数专项窗口 | 市场级泡沫        | 250、500、750、900 个交易日         |
| 个股专项窗口 | 单股波动更大       | 120、180、250、375、500 个交易日     |

实务上，**指数可以用长窗口，个股应多用短中窗口**。因为个股常有财报跳空、并购、停牌、涨跌停、主题轮动，太长窗口容易把多个 regime 混在一起。

---

### Step 3：拟合参数

对每个资产、每个窗口、每个截至日 (t_2)，拟合：

[
\theta=(t_c,m,\omega)
]

在线性化形式下，给定 (\theta) 后，(A,B,C_1,C_2) 用 OLS 直接求解。附件论文也强调，通过“slaving”线性参数 (A,B,C)，可以把自由非线性参数数量降低，并把线性参数用普通最小二乘解析求出。

推荐优化组合：

| 阶段     | 方法                                            | 目的         |
| ------ | --------------------------------------------- | ---------- |
| 初始全局搜索 | Sobol / Latin Hypercube / random search       | 避免落入局部最优   |
| 候选筛选   | 取 SSE 最小的前 20–50 组                            | 保留多解       |
| 局部优化   | Levenberg-Marquardt / Nelder-Mead / BFGS      | 精修参数       |
| 稳健版本   | Huber loss / winsorized residual              | 降低跳空和极端点影响 |
| 多算法确认  | differential evolution + least_squares + BFGS | 降低单算法偏差    |

论文提到 LPPL 拟合常有多个局部极小值，原始 2-step 非线性优化用 Taboo search 找候选，再用 Levenberg-Marquardt 精修；同时也讨论遗传算法不需要梯度或光滑成本函数。

---

## 4. 参数约束和过滤条件

### 4.1 上涨泡沫过滤

用于判断顶部、平台、崩盘风险：

[
B<0
]

[
0.1<m<0.9
]

[
6\le \omega \le 15
]

[
t_c>t_2
]

[
5 \le t_c-t_2 \le 252
]

[
0<|C|<1
]

附件论文提到常用过滤条件包括 (B<0)、(0<\beta<1)、(t_c>t_i)，并提到更严格约束可设为 (0.1<\beta<0.9)、(6\le\omega\le15)、(|C|<1)，以避免拟合噪音或把周期项误当趋势项。

还应加入振荡数量约束：

[
N_{osc}=\frac{\omega}{2\pi}\ln\left(\frac{t_c-t_1}{t_c-t_2}\right)
]

建议：

[
2 \le N_{osc} \le 10
]

低于 2 表示周期结构不足，高于 10 容易过拟合噪声。

### 4.2 下跌泡沫 / 恐慌反弹过滤

用于判断恐慌性下跌接近底部：

[
B>0
]

其余条件类似。也可以对 (-y(t)) 跑上涨泡沫模型，这样信号逻辑保持一致。

### 4.3 拟合质量过滤

每个结果至少需要通过：

| 检查                        | 标准                |
| ------------------------- | ----------------- |
| SSE / RMSE                | 排名前 20%           |
| LPPL 相对 power-law-only 改善 | SSE 至少下降 5%–10%   |
| LPPL 相对指数趋势 / 二次趋势改善      | 信息准则更优            |
| 残差异常点                     | 单个点不能贡献过高 SSE     |
| 参数稳定性                     | 相邻窗口 (t_c) 不应剧烈跳动 |
| 未来临界点                     | (t_c) 不宜离当前超过 1 年 |

论文提到泡沫刚开始形成时不容易诊断，且文中引用观点认为泡沫通常不能提前超过 1 年诊断。 因此实盘里 (t_c-t_2>252) 个交易日的信号不应作为高等级风险预警。

---

## 5. 残差检验：必须做，不做容易过拟合

附件论文讨论了 Chang 和 Feigenbaum 对原始 JLS 模型的批评：原始模型存在非平稳随机游走成分，价格路径直接拟合可能不一致；后续 Lin 等人提出 mean-reverting residuals 的广义 LPPL 模型，使价格围绕 LPPL 轨迹波动。

因此每个有效拟合都要检验残差：

[
e_t=y_t-\hat{y}_t
]

做三类检验：

| 检验        | 目标      | 通过条件    |
| --------- | ------- | ------- |
| ADF       | 检验单位根   | 拒绝单位根   |
| KPSS      | 检验平稳性   | 不拒绝平稳   |
| Ljung-Box | 检查残差自相关 | 自相关不能过强 |

论文建议在 ADF / PP 外加入 KPSS，因为 ADF/PP 在 AR(1) 系数接近 1 时功效较低；如果 ADF 指向单位根但 KPSS 指向平稳，应更保守。

残差不平稳时，信号降级；残差平稳且 (t_c) 聚合稳定时，信号升级。

---

## 6. 临界时间聚合：不要相信单个 (t_c)

每个资产当天会得到很多 (t_c)：

[
{t_{c,1},t_{c,2},...,t_{c,n}}
]

来源包括不同窗口、不同起点、不同优化器、不同 loss function。最终输出不要只给一个日期，而是给分位数：

[
Q_{5},Q_{20},Q_{50},Q_{80},Q_{95}
]

实际看板字段：

| 字段                  | 含义       |
| ------------------- | -------- |
| (t_c) median        | 最可能临界时间  |
| (t_c) 20%–80%       | 核心区间     |
| (t_c) 5%–95%        | 宽置信区间    |
| valid fit ratio     | 有效拟合比例   |
| residual pass ratio | 残差检验通过比例 |
| window agreement    | 多窗口是否集中  |
| optimizer agreement | 多优化器是否一致 |

论文黄金案例中，也使用不同窗口和不同算法得到的 (t_c)，再计算 20%/80% 和 5%/95% crash date 分位区间。

---

## 7. CLIP 图：实盘预警最有用的图

CLIP，即 Crash Lock-In Plot：

横轴：每次估计的最后观察日 (t_2)
纵轴：该次估计得到的 (t_c)

如果市场 regime change 接近，滚动估计的 (t_c) 会从乱跳转为在某一未来日期附近“锁定”。论文称，CLIP 可用于追踪泡沫发展并判断是否接近崩盘或泡沫收缩；如果递归估计的 (t_c) 稳定在接近临界时间的常数附近，说明 regime change 可能临近。

实盘判定：

| CLIP 状态            | 解释            |
| ------------------ | ------------- |
| (t_c) 散乱           | 无有效 LPPL 预警   |
| (t_c) 逐渐收敛但距离远     | 观察            |
| (t_c) 在未来 1–3 个月集中 | 中等级预警         |
| (t_c) 集中且价格继续加速    | 高等级预警         |
| (t_c) 已过但价格未跌      | 可能转平台、横盘或模型失效 |

---

## 8. 预警分数设计

建议最终不要输出“会不会崩盘”，而是输出 0–100 的 LPPL 风险分数。

[
Score = 0.25S_{param}+0.20S_{fit}+0.20S_{tc}+0.15S_{resid}+0.10S_{clip}+0.10S_{breadth}
]

| 子分数           | 计算逻辑                          |
| ------------- | ----------------------------- |
| (S_{param})   | 参数是否满足 (B,m,\omega,C,t_c) 条件  |
| (S_{fit})     | LPPL 相对基准模型的拟合改善              |
| (S_{tc})      | (t_c) 是否落在未来 5–90 个交易日，且分位区间窄 |
| (S_{resid})   | ADF/KPSS/Ljung-Box 是否通过       |
| (S_{clip})    | CLIP 是否锁定                     |
| (S_{breadth}) | 同市场/同板块是否大量资产同步出现 LPPL        |

预警等级：

|     分数 | 等级   | 操作含义                  |
| -----: | ---- | --------------------- |
|   0–39 | 无信号  | 不处理                   |
|  40–59 | 观察   | 加入 watchlist          |
|  60–74 | 中风险  | 降低追高、提高止盈纪律           |
|  75–89 | 高风险  | 控制净敞口、减少杠杆            |
| 90–100 | 极端风险 | 需要结合宏观、期权、成交、新闻进行人工复核 |

---

## 9. 四个市场的具体实施差异

### 9.1 美股

**优先目标：** Nasdaq、AI、半导体、软件、小盘成长股泡沫。

| 模块   | 建议                                                                             |
| ---- | ------------------------------------------------------------------------------ |
| 指数   | SPX、NDX、IXIC、RUT、SOX、ARKK、SMH                                                  |
| 个股   | Russell 3000、CRSP 普通股、主题 ETF 成分股                                               |
| 数据源  | CRSP、Bloomberg、LSEG/Refinitiv、FactSet、Polygon、Tiingo                           |
| 关键字段 | adjusted close、split factor、dividend、delisting return、sector、market cap、volume |
| 特殊处理 | 拆股、现金股息、ADR、退市偏差、盘后财报跳空                                                        |

美股回测必须使用 survivor-bias-free 数据，否则 2000 年、2008 年、2021 年小盘成长股泡沫会严重失真。CRSP 明确提供 active 和 inactive securities，并包含公司行为，适合做研究级回测。([Center for Research in Security Prices][2])

### 9.2 韩国股市

**优先目标：** 半导体、HBM、二次电池、KOSDAQ 高弹性主题股。

| 模块   | 建议                                                                             |
| ---- | ------------------------------------------------------------------------------ |
| 指数   | KOSPI、KOSDAQ、KOSPI 200、KOSDAQ 150                                              |
| 个股   | Samsung Electronics、SK Hynix、KOSPI 200、KOSDAQ 150、成交额前 300                     |
| 数据源  | KRX Information Data System、Koscom、Bloomberg、LSEG                              |
| 关键字段 | adjusted close、volume、turnover、foreign ownership、short selling、suspension flag |
| 特殊处理 | 涨跌停、停牌、外资流入集中、KOSDAQ 主题股高波动                                                    |

KRX 官方有 Information Data System，Koscom 也提供交易所及 OTC 市场的股票、衍生品、债券、商品和指数的实时及批量信息。([data.krx.co.kr][4])

韩国市场建议额外做**外资成交/持仓同步指标**，因为韩国科技股泡沫往往与外资集中买入、韩元、半导体周期同步。

### 9.3 台湾股市

**优先目标：** TAIEX、电子指数、半导体、AI 服务器、PCB、散热、光通讯。

| 模块   | 建议                                         |
| ---- | ------------------------------------------ |
| 指数   | TAIEX、电子指数、半导体指数、柜买指数                      |
| 个股   | TWSE/TPEX 成交额前 300，AI 服务器链、半导体链            |
| 数据源  | TWSE、TPEX、MOPS、台湾政府开放资料平台、Bloomberg、TEJ    |
| 关键字段 | adjusted close、除权息资料、成交值、融资融券、三大法人、注意股/处置股 |
| 特殊处理 | 除权息密集、涨跌停、柜买小票流动性、法人筹码集中                   |

TWSE 官方提供个股日收盘价/月平均价查询，台湾政府开放资料平台也列出 TWSE 上市股票日收盘价和月平均价资料集；TPEX 则提供柜买股票日行情下载。([台灣證券交易所][5])

台湾市场建议加入**融资余额变化、三大法人买卖超、处置股状态**作为辅助过滤。LPPL 只看价格，但台湾主题泡沫常常先在融资和注意股制度中暴露。

### 9.4 香港股市

**优先目标：** HSTECH、恒指、国企指数、南向资金驱动个股、中概回港股、内房/券商/互联网阶段性泡沫。

| 模块   | 建议                                                                                             |
| ---- | ---------------------------------------------------------------------------------------------- |
| 指数   | HSI、HSCEI、HSTECH                                                                               |
| 个股   | Main Board 成交额前 300、HSTECH 成分股、南向成交前列                                                          |
| 数据源  | HKEX Historical Data Services、HKEX Data Marketplace、Bloomberg、LSEG                             |
| 关键字段 | adjusted close、turnover、short selling turnover、suspension、southbound flow、dual-listing mapping |
| 特殊处理 | 长停牌、低流动性仙股、配股/供股、南向资金冲击、午休交易结构                                                                 |

HKEX Historical Data Services 的 Day-end Closing Data 提供 Main Board 与 GEM 股票的每日 High、Low、Close 和 turnover；HKEX Data Marketplace 则是其集中化市场数据平台。([香港交易所][6])

香港个股必须严格过滤停牌和低价股。大量小票会因供股、合股、停牌复牌产生非 LPPL 跳变，不适合纳入自动化预警主池。

---

## 10. 数据字段需求清单

### 10.1 最低可运行字段

| 字段                      | 必需性  | 说明                             |
| ----------------------- | ---- | ------------------------------ |
| date                    | 必需   | 本地交易日                          |
| ticker                  | 必需   | 市场内唯一代码                        |
| exchange                | 必需   | NYSE/Nasdaq/KRX/TWSE/TPEX/HKEX |
| close_raw               | 必需   | 原始收盘价                          |
| close_adjusted          | 必需   | 复权收盘价                          |
| volume                  | 必需   | 成交量                            |
| turnover                | 强烈建议 | 成交额，跨市场流动性过滤更好                 |
| currency                | 必需   | USD/KRW/TWD/HKD                |
| corporate_action_factor | 必需   | 拆股、配股、股息等调整因子                  |
| suspension_flag         | 必需   | 停牌过滤                           |
| market_cap              | 强烈建议 | 分层筛选                           |
| sector / industry       | 强烈建议 | 板块宽度分析                         |
| index_membership        | 强烈建议 | 指数成分与回测池                       |
| FXUSD                   | 可选   | 美元口径跨市场看板                      |

### 10.2 增强字段

| 字段                              | 用途         |
| ------------------------------- | ---------- |
| short interest / short turnover | 判断泡沫挤压和反身性 |
| margin balance                  | 台湾、韩国尤其有用  |
| foreign net buy                 | 韩国、台湾重要    |
| southbound flow                 | 香港重要       |
| options implied volatility      | 美股重要       |
| news/sentiment/search trend     | 辅助确定泡沫起点   |
| ETF flow                        | 美股主题泡沫有用   |
| insider selling / placement     | 个股泡沫风险辅助   |

附件论文黄金案例中也使用 Google Trends 的搜索量指数辅助判断泡沫起点，说明非价格情绪数据可作为窗口选择辅助，而不是 LPPL 主输入。

---

## 11. 输出结果格式

每个资产每日输出一条记录：

| 字段                 | 示例                         |
| ------------------ | -------------------------- |
| market             | US                         |
| ticker             | NVDA                       |
| as_of_date         | 2026-06-11                 |
| direction          | upward_bubble              |
| valid_fit_count    | 86                         |
| total_fit_count    | 240                        |
| valid_ratio        | 35.8%                      |
| tc_median          | 2026-08-15                 |
| tc_q20             | 2026-07-25                 |
| tc_q80             | 2026-09-10                 |
| score              | 78                         |
| residual_adf_pass  | true                       |
| residual_kpss_pass | true                       |
| clip_lock          | true                       |
| warning_level      | high                       |
| comment            | 多窗口 (t_c) 收敛，参数有效，但残差自相关偏高 |

市场层面输出：

| 市场        | 上涨泡沫资产占比 | 高风险资产数 | (t_c) 中位数 | 最高风险板块               |
| --------- | -------: | -----: | --------- | -------------------- |
| US        |      18% |     42 | 2026-08   | Semis / AI infra     |
| Korea     |      22% |     31 | 2026-07   | HBM / KOSDAQ         |
| Taiwan    |      25% |     55 | 2026-07   | PCB / AI server      |
| Hong Kong |      12% |     18 | 2026-09   | Internet / brokerage |

---

## 12. 推荐系统架构

### 数据层

每日收盘后运行：

1. 拉取官方或供应商 EOD 数据。
2. 拉取公司行为。
3. 生成复权价格。
4. 更新指数成分。
5. 更新流动性、成交额、市值。
6. 写入 `daily_prices_adjusted` 表。

### 模型层

每日按市场批处理：

1. universe filter。
2. window generator。
3. LPPL fitter。
4. parameter filter。
5. residual diagnostics。
6. (t_c) ensemble aggregation。
7. score engine。
8. chart generator。
9. alert writer。

### 看板层

需要 5 张图：

1. 价格 + LPPL 拟合曲线。
2. (t_c) 分布直方图。
3. CLIP 图。
4. 残差图 + ADF/KPSS 结果。
5. 市场/板块泡沫宽度热力图。

---

## 13. 伪代码

```python
for market in ["US", "KR", "TW", "HK"]:
    universe = load_universe(market)
    universe = liquidity_filter(universe, min_adtv_usd=1_000_000)

    for asset in universe:
        px = load_adjusted_price(asset)
        px = clean_price_series(px)

        all_fits = []

        for L in [120, 180, 250, 375, 500, 750]:
            if len(px) < L:
                continue

            window = px[-L:]
            y = np.log(window["adj_close"])

            for start_shift in range(0, min(120, L-100), 5):
                sub_y = y[start_shift:]

                candidates = global_search_lppl(sub_y)
                refined = local_optimize_lppl(sub_y, candidates)

                for fit in refined:
                    if pass_parameter_filter(fit):
                        fit.residual_tests = run_residual_tests(fit)
                        all_fits.append(fit)

        ensemble = aggregate_tc(all_fits)
        clip_state = update_clip(asset, ensemble)
        score = compute_lppl_score(all_fits, ensemble, clip_state)

        save_signal(asset, ensemble, clip_state, score)
```

---

## 14. 回测方法

必须 walk-forward，不允许事后选窗口。

### 14.1 标签定义

上涨泡沫成功预警可定义为：

[
\max_{t \in [t_c-20,t_c+20]} P_t
]

附近出现局部顶部，且未来 60 个交易日最大回撤超过：

| 对象     |           阈值 |
| ------ | -----------: |
| 指数     |  -10% 或 -15% |
| 大盘股    |         -20% |
| 小盘/主题股 |         -30% |
| 香港小票   | 单独处理，不建议统一阈值 |

### 14.2 评价指标

| 指标                         | 含义                 |
| -------------------------- | ------------------ |
| Precision                  | 发出高风险信号后，实际发生大回撤比例 |
| Recall                     | 大回撤前是否提前报警         |
| False alarms / market-year | 每市场每年误报次数          |
| Median lead time           | 预警提前天数             |
| Drawdown avoided           | 降低仓位后减少的回撤         |
| Opportunity cost           | 过早减仓错过的上涨          |

### 14.3 回测池要求

| 市场 | 要求                         |
| -- | -------------------------- |
| 美股 | 包含退市股，避免 survivorship bias |
| 韩国 | 包含 KOSPI/KOSDAQ 历史成分变化     |
| 台湾 | 包含 TWSE/TPEX 历史成分和除权息      |
| 香港 | 包含长期停牌、退市、合股供股历史           |

---

## 15. 最终建议版本

后续实施时建议分三期。

### 第一期：指数与核心股票池

先跑：

| 市场 |                        标的数量 |
| -- | --------------------------: |
| 美股 |            指数 + 300 只高成交额股票 |
| 韩国 | 指数 + KOSPI 200 + KOSDAQ 150 |
| 台湾 |     指数 + TWSE/TPEX 成交额前 300 |
| 香港 |    指数 + Main Board 成交额前 300 |

先不用 AR-GARCH，先实现：

1. 线性化 LPPL。
2. 多窗口。
3. 多初值。
4. 参数过滤。
5. (t_c) 分位数。
6. CLIP。
7. ADF/KPSS。
8. 每日看板。

### 第二期：加入市场微观结构和资金流

加入：

| 市场 | 增强数据                                 |
| -- | ------------------------------------ |
| 美股 | options IV、ETF flow、short interest   |
| 韩国 | foreign net buy、short selling、margin |
| 台湾 | 三大法人、融资融券、注意股/处置股                    |
| 香港 | 南向资金、short selling turnover、停牌/配股/供股 |

### 第三期：组合风险应用

把 LPPL 分数转成仓位约束：

| LPPL 分数 | 仓位动作        |
| ------: | ----------- |
|     <40 | 不调整         |
|   40–60 | 禁止追高        |
|   60–75 | 降低新增仓位      |
|   75–90 | 降低净敞口、减少杠杆  |
|     >90 | 进入人工复核和风险会议 |

---

## 16. 关键风险

LPPL 不是“崩盘预测器”，更准确地说是**泡沫型价格路径识别器**。(t_c) 代表 regime change 的高概率窗口，结果可能是暴跌，也可能是横盘、慢跌、板块切换或估值压缩。附件论文也强调，为减少误报，应使用一组测试，只有预测通过所有测试才值得重视。

因此后续实施应遵循一条原则：

**单资产单窗口 LPPL = 噪音；多资产多窗口 (t_c) 收敛 + 残差平稳 + CLIP 锁定 + 市场宽度升高 = 可行动风险信号。**

[1]: https://zhuanlan.zhihu.com/p/395621402?utm_source=chatgpt.com "分解log-periodic power laws(LPPL)模型"
[2]: https://www.crsp.org/research/crsp-us-stock-databases/?utm_source=chatgpt.com "CRSP US Stock Databases - Center for Research in ..."
[3]: https://data.gov.tw/en/datasets/11548?utm_source=chatgpt.com "After-market information Individual stock daily closing ..."
[4]: https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd?locale=en&utm_source=chatgpt.com "KRX Information Data System"
[5]: https://www.twse.com.tw/en/trading/historical/stock-day-avg.html?utm_source=chatgpt.com "Taiwan Stock Exchange Corporation"
[6]: https://www.hkex.com.hk/eng/ods/historicalData.aspx?utm_source=chatgpt.com "Securities Market - Historical Data ..."
