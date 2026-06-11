const DEFAULT_DATA = {
  asOf: "2026-05-18",
  curve: {
    tenors: ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"],
    today: [3.69, 3.68, 3.77, 3.81, 4.07, 4.14, 4.27, 4.43, 4.61, 5.14, 5.14],
    w1: [3.71, 3.70, 3.77, 3.79, 3.95, 3.96, 4.07, 4.24, 4.42, 4.97, 4.98],
    m1: [3.69, 3.70, 3.69, 3.64, 3.71, 3.72, 3.84, 4.04, 4.26, 4.85, 4.88],
    d1: [-0.02, -0.01, 0.00, -0.01, -0.02, 0.00, 0.01, 0.00, 0.02, 0.00, 0.02]
  },
  decomposition: {
    components: [
      { index: "01", name: "短端实际利率", en: "E[real short rate]", value: "~1.6%", note: "EFFR 3.63 − 短期通胀预期约 2.0;受产出缺口与双重使命约束", driver: "基本面 + 政策" },
      { index: "02", name: "短端通胀预期", en: "E[π short]", value: "~2.5%", note: "10Y BEI 约 2.48%;长期锚定尚未完全脱锚", driver: "供需冲击" },
      { index: "03", name: "实际期限溢价", en: "Real term premium", value: "+0.31%", note: "ACM 模型估算;对供给压力、经济不确定性、风险偏好敏感", driver: "供给 + 风险偏好" },
      { index: "04", name: "通胀风险溢价", en: "Inflation risk prem.", value: "+0.20%", note: "补偿未来通胀不确定性", driver: "通胀不确定性" }
    ],
    attribution: [
      { window: "1 日", total: 2, real: 3, inflation: -1, term: 0, risk: 0, driver: "实际利率" },
      { window: "1 周", total: 19, real: 18, inflation: 1, term: 0, risk: 0, driver: "真实利率" },
      { window: "1 月", total: 35, real: 23, inflation: 12, term: 0, risk: 0, driver: "真实利率+通胀" },
      { window: "YTD", total: 42, real: 19, inflation: 23, term: null, risk: null, driver: "双轮驱动" }
    ],
    frameworkNote: "Clarida框架把长期名义利率拆成预期短端真实利率、预期短端通胀、实际期限溢价和通胀风险溢价,用来识别收益率背后的叙事变化。",
    regimeRead: "10Y上行由真实利率和通胀补偿共同驱动,实际利率处高位且BEI仍有粘性时,名义久期面对的是通胀冲击下的政策对峙。",
    policyRead: "市场先跑、官方后确认:市场隐含路径先反映降息退潮和加息尾部,SEP和点阵图属于低频官方锚,下一次FOMC将验证这条叙事。",
    sources: [
      { name: "美联储 SEP · 点阵图", value: "2026 中位数 ~3.75%", note: "官方季度预期,反映票委观点,频率最低但影响政策叙事。" },
      { name: "FF 期货 / OIS 隐含", value: "降息退潮 · 加息尾部升温", note: "实时市场定价,最先反映能源冲击后的路径再定价。" },
      { name: "调查 SPF / Blue Chip", value: "2026 年末 ~3.75%", note: "覆盖机构经济学家,低频且滞后,可作为理性预期基准。" }
    ]
  },
  fedPath: [
    { m: "6/17", hike: 0, hold: 99, cut: 1 },
    { m: "7/29", hike: 5, hold: 93, cut: 2 },
    { m: "9/16", hike: 18, hold: 78, cut: 4 },
    { m: "10/28", hike: 34, hold: 62, cut: 4 },
    { m: "12/9", hike: 56, hold: 40, cut: 4 }
  ],
  macroLiquidity: {
    score: 42,
    regime: "偏紧",
    bias: "restrictive",
    sourceUrl: "https://bhadial.com/dashboard",
    moduleCount: 7,
    scoredFactorCount: 30,
    method: "Bhadial Conditions Score-compatible 30-factor, 7-module 5Y historical percentile composite; Funding uses EMA(5).",
    summary: "偏紧: 等待 data/dashboard.json 后显示实时 30 因子模块评分。",
    constraint: { name: "净流动性", value: "$5.93T", contribution: -8.14, direction: "restrictive" },
    offset: { name: "SOFR-EFFR压力", value: "-11bp", contribution: 5.88, direction: "supportive" },
    balance: [
      { label: "拖累", count: 4, contribution: -20.99, direction: "restrictive" },
      { label: "中性", count: 0, contribution: 0, direction: "neutral" },
      { label: "缓冲", count: 2, contribution: 6.68, direction: "supportive" }
    ],
    focusComponents: [
      { name: "净流动性", score: 13, percentile: 13, weight: 0.22, contribution: -8.14, value: "$5.93T", source: "FRED WALCL - WTREGEN - RRPONTSYD", direction: "restrictive" },
      { name: "SOFR-EFFR压力", score: 99, percentile: 1, weight: 0.12, contribution: 5.88, value: "-11bp", source: "FRED SOFR - DFF", direction: "supportive" },
      { name: "银行准备金", score: 22, percentile: 22, weight: 0.18, contribution: -5.04, value: "$3.13T", source: "FRED WRESBAL", direction: "restrictive" },
      { name: "ON RRP缓冲", score: 3, percentile: 3, weight: 0.10, contribution: -4.7, value: "$0.004T", source: "FRED RRPONTSYD", direction: "restrictive" },
      { name: "TGA抽水", score: 24, percentile: 76, weight: 0.12, contribution: -3.12, value: "$0.81T", source: "FRED WTREGEN", direction: "restrictive" }
    ],
    hiddenComponentCount: 1,
    implications: [
      { label: "久期", tone: "restrictive", text: "净流动性压制承接,长端抛售更容易放大。" },
      { label: "风险资产", tone: "restrictive", text: "流动性低分位削弱估值缓冲,高贝塔资产更依赖盈利支撑。" },
      { label: "融资压力", tone: "watch", text: "SOFR-EFFR压力提供局部缓冲,但不足以抵消现金抽水。" }
    ],
    components: [
      { name: "银行准备金", score: 22, percentile: 22, weight: 0.18, contribution: -5.04, value: "$3.13T", source: "FRED WRESBAL", direction: "restrictive" },
      { name: "净流动性", score: 13, percentile: 13, weight: 0.22, contribution: -8.14, value: "$5.93T", source: "FRED WALCL - WTREGEN - RRPONTSYD", direction: "restrictive" },
      { name: "流动性动量", score: 55, percentile: 55, weight: 0.16, contribution: 0.8, value: "-0.02T", source: "Net liquidity 1M change", direction: "supportive" },
      { name: "TGA抽水", score: 24, percentile: 76, weight: 0.12, contribution: -3.12, value: "$0.81T", source: "FRED WTREGEN", direction: "restrictive" },
      { name: "ON RRP缓冲", score: 3, percentile: 3, weight: 0.10, contribution: -4.7, value: "$0.004T", source: "FRED RRPONTSYD", direction: "restrictive" },
      { name: "SOFR-EFFR压力", score: 99, percentile: 1, weight: 0.12, contribution: 5.88, value: "-11bp", source: "FRED SOFR - DFF", direction: "supportive" }
    ],
    drivers: [
      { name: "净流动性", score: 13, contribution: -8.14, value: "$5.93T", direction: "restrictive" },
      { name: "SOFR-EFFR压力", score: 99, contribution: 5.88, value: "-11bp", direction: "supportive" },
      { name: "银行准备金", score: 22, contribution: -5.04, value: "$3.13T", direction: "restrictive" }
    ]
  },
  macroLiquidityEquity: {
    available: false,
    title: "宏观环境评分 vs S&P 500 · 5Y Lead Study",
    method: "Monthly 5Y sample; requires live public history.",
    conclusion: "HTTP模式读取 data/dashboard.json 后显示历史领先性检验。",
    observationCount: 0,
    stats: [],
    buckets: [],
    series: []
  },
  spyEarlyWarning: {
    available: false,
    title: "SPY Early Warning Index",
    score: null,
    baseScore: null,
    regime: "Unavailable",
    regimeCn: "不可用",
    summary: "HTTP模式读取 data/dashboard.json 后显示SPY预警指标。",
    allocation: { stance: "等待", equityExposure: "不调整", hedgeAction: "等待更多数据", tone: "neutral" },
    amplifiers: [],
    dampeners: [],
    sleeves: [],
    drivers: [],
    backtest: { target: "3M SPX drawdown and negative forward-return warning", sampleSize: 0 }
  },
  equityShortTermRisk: {
    available: false,
    title: "短期股市风险预警",
    score: null,
    regime: "Unavailable",
    regimeCn: "不可用",
    summary: "HTTP模式读取 data/dashboard.json 后显示短期股市风险预警。",
    allocation: { stance: "等待", equityExposure: "不调整", hedgeAction: "等待日线市场结构数据" },
    components: [],
    drivers: [],
    trend: { available: false, points: [] },
    backtest: { available: false, sampleSize: 0, scoreBuckets: [], thresholdTests: [], regressionTests: [], worstWindows: [] },
    lookAheadGuard: {}
  },
  globalLpplRisk: {
    available: false,
    title: "Global LPPL Risk · 全球指数泡沫临界风险",
    score: null,
    scoreUse: "independent",
    regime: "Unavailable",
    regimeCn: "不可用",
    summary: "HTTP模式读取 data/dashboard.json 后显示全球LPPL风险评估。",
    method: "LPPL grid search over constrained tc/m/omega with linear least-squares fit.",
    indices: [],
    indexValidation: { available: false, rows: [] },
    history: { available: false, points: [] },
    backtest: { available: false, sampleSize: 0, threshold: 65, horizonTests: [] }
  },
  groups: [
    {
      id: "g1",
      name: "货币政策",
      en: "Monetary Policy",
      weight: 25,
      factors: [
        { n: "联邦基金目标利率", tag: "3.50-3.75% · 连续3次持平", v: "持平", score: -1, note: "政策按兵不动,但市场已转向定价加息,基准已不再是宽松。" },
        { n: "隐含政策路径", tag: "Fed Funds 期货", v: "偏加息", score: -2, curve: 1, note: "期货/OIS 显著削弱降息定价,加息尾部风险权重上升。" },
        { n: "新任主席倾向", tag: "K. Warsh · 5/15接任", v: "偏鹰", score: -1, note: "市场视其为偏鹰,强化紧缩预期。" },
        { n: "资产负债表 / 准备金", tag: "QT 已结束", v: "温和宽松", score: 1, curve: -1, note: "维持购买短期国债保持准备金充裕,对前端温和利多。" }
      ]
    },
    {
      id: "g2",
      name: "宏观基本面",
      en: "Macro Fundamentals",
      weight: 25,
      factors: [
        { n: "通胀跟踪", tag: "CPI 3.8% / PCE 3.3% / 核心PCE 2.5% / Dallas Trimmed PCE 2.4%", v: "全面偏热", score: -2, note: "同时跟踪FRED CPIAUCSL、PCEPI、PCEPILFE与Dallas Fed Trimmed Mean PCE(PCETRIM12M159SFRBDAL);PCE和核心PCE更贴近Fed通胀框架,Dallas Trimmed PCE过滤极端分项噪声,适合作为政策反应函数中的底层通胀趋势观察项。" },
        { n: "PPI 生产者物价 (4月)", tag: "+1.4% 环比 / +6% 同比", v: "爆表", score: -2, note: "生产端价格大幅超预期,通胀链条向下游延伸。" },
        { n: "劳动力市场", tag: "就业增长偏低", v: "温和降温", score: 1, note: "就业降温但被通胀压制,单独不足以支持宽松。" },
        { n: "增长动能", tag: "活动稳健扩张", v: "稳健", score: -1, curve: 1, note: "经济仍扩张,衰退风险有限,不支持降息。" }
      ]
    },
    {
      id: "g3",
      name: "供给与技术面",
      en: "Supply & Technicals",
      weight: 15,
      factors: [
        { n: "30年期拍卖", tag: "5.046% · 2.30x", v: "疲弱", score: -2, curve: 2, note: "30年期高收益率发行且出现尾部,长端需求疲弱。" },
        { n: "发行节奏 / QRA", tag: "息票规模高位", v: "压力大", score: -1, curve: 1, note: "赤字叠加再融资规模,长端供给压力结构性持续。" },
        { n: "TGA 与现金管理", tag: "~$0.81T", v: "抽水", score: -1, note: "TGA 高位对银行体系流动性仍有边际抽水压力。" }
      ]
    },
    {
      id: "g4",
      name: "需求与持仓",
      en: "Demand & Positioning",
      weight: 15,
      factors: [
        { n: "CFTC 杠杆基金持仓", tag: "长端净空 · 偏极端", v: "反向利多", score: 1, curve: -1, note: "长端净空头偏极端,存在轧空风险,反向温和利多。" },
        { n: "TIC 海外持仓", tag: "3月外资减持", v: "偏弱", score: -1, curve: 1, note: "日本、中国及多家主要海外持有者减持,外资支撑下降。" },
        { n: "一级交易商持仓", tag: "中性", v: "中性", score: 0, note: "交易商库存中性,未见明显被动累库压力。" }
      ]
    },
    {
      id: "g5",
      name: "相对价值",
      en: "Relative Value",
      weight: 10,
      factors: [
        { n: "期限溢价 (ACM)", tag: "长端抛售推升", v: "估值转吸引", score: 1, curve: -1, note: "长端抛售推升期限溢价,长端估值转吸引。" },
        { n: "实际利率 / 盈亏平衡", tag: "10Y TIPS 2.13% / BEI 2.48%", v: "偏空", score: -1, note: "实际利率快速上台阶,盈亏平衡通胀仍处高位。" },
        { n: "互换利差", tag: "中性", v: "中性", score: 0, note: "互换利差未见极端信号,跨产品基差大体均衡。" }
      ]
    },
    {
      id: "g6",
      name: "情绪与流动性",
      en: "Sentiment & Liquidity",
      weight: 10,
      factors: [
        { n: "利率波动 (MOVE 代理)", tag: "收益率创年内新高", v: "高波动", score: -1, note: "地缘风险推升利率波动,波动代理处高位。" },
        { n: "市场流动性", tag: "轻度承压", v: "偏紧", score: -1, curve: 1, note: "长端深度变薄、买卖价差走阔,流动性边际转差。" },
        { n: "新老券利差", tag: "中性", v: "中性", score: 0, note: "新老券利差未见明显挤压,融资市场大体平稳。" }
      ]
    }
  ],
  policy: {
    rates: [
      ["联邦基金目标区间", "3.50-3.75%", "连续三次持平"],
      ["有效联邦基金利率", "3.63%", "EFFR"],
      ["SOFR", "~3.65%", "担保隔夜"],
      ["上次会议", "4/28-29", "按兵不动"],
      ["投票分歧", "8-4", "1992年以来最多异议"],
      ["新任主席", "K. Warsh", "5/15 接任"]
    ],
    plumbing: [
      ["美联储资产负债表", "~$6.73T", "H.4.1"],
      ["缩表 (QT)", "已结束", "准备金管理转中性"],
      ["准备金余额", "~$3.0T", "充裕"],
      ["ON RRP", "~$0.004T", "近枯竭"],
      ["财政部一般账户", "~$0.81T", "TGA 高位"],
      ["流动性结论", "边际抽水", "财政现金压制银行体系"]
    ]
  },
  auctions: [
    { type: "30年期国债", size: "$25B", yield: "5.046%", btc: "2.30", rating: "疲弱·尾部" },
    { type: "10年期国债", size: "$42B", yield: "4.468%", btc: "2.40", rating: "中性偏弱" },
    { type: "3年期国债", size: "$58B", yield: "3.965%", btc: "2.54", rating: "偏软" },
    { type: "13周国库券", size: "$89B", yield: "~3.60%", btc: "2.86", rating: "稳健" }
  ],
  fiscal: [
    ["季度再融资 (QRA)", "息票规模高位", "供给压力"],
    ["净息票供给趋势", "上行", "长端压力"],
    ["国库券占比", "偏高", "前端滚动"],
    ["联邦赤字 / GDP", "~6%+", "财政扩张"],
    ["TGA 余额趋势", "~$0.81T", "高位抽水"]
  ],
  positioning: {
    cftc: [
      ["杠杆基金 · 长端", "10Y/30Y 净空头偏极端", "反向温和利多"],
      ["杠杆基金 · 前端", "2Y/5Y 净空头", "政策风险对冲"],
      ["资产管理人 · 长端", "净多头", "久期配置仍在"],
      ["基差交易", "现券-期货规模庞大", "需警惕去杠杆流动性事件"]
    ],
    tic: [
      ["日本", "~$1.192T", "下降"],
      ["中国", "~$0.652T", "下降"],
      ["全球外资总持仓", "~$9.35T", "边际走弱"],
      ["长债海外需求", "下降", "长端支撑削弱"]
    ],
    dealers: [
      ["Primary dealers · UST ex-TIPS", "$500.4B", "NY Fed周频统计"],
      ["Primary dealers · UST repo", "$3.19T", "融资余额"],
      ["Primary dealers · UST交易量", "$872.6B", "周成交额"]
    ]
  },
  cross: {
    yields: [
      ["美国 UST", 4.61],
      ["德国 Bund", 2.92],
      ["英国 Gilt", 4.88],
      ["日本 JGB", 1.92]
    ],
    risk: [
      ["标普 500", "近历史高位", "股票对加息预期相对钝化"],
      ["VIX", "偏低·小幅抬升", "风险定价开始变紧"],
      ["美元指数 DXY", "走强", "加息预期支撑美元"],
      ["IG / HY 信用利差", "温和走阔", "紧缩风险被嗅到"]
    ],
    inflation: [
      ["CPI通胀", "~3.8%", "FRED CPIAUCSL YoY"],
      ["PCE通胀", "~3.3%", "FRED PCEPI YoY"],
      ["核心PCE", "~2.5%", "FRED PCEPILFE YoY"],
      ["达拉斯联储Trimmed Mean PCE", "~2.4%", "FRED PCETRIM12M159SFRBDAL"],
      ["10年盈亏平衡通胀", "~2.48%", "通胀补偿高位"],
      ["10年实际利率 (TIPS)", "~2.13%", "真实回报要求上升"],
      ["5y5y 远期通胀", "上行", "通胀锚定受考验"],
      ["原油 / 贵金属", "高位·强势", "地缘与避险共振"]
    ],
    historySeries: [
      {
        id: "global",
        label: "全球利率",
        en: "Global Rates",
        series: [
          { displayName: "美国10Y", category: "curve_yield", name: "10Y收益率", label: "10Y", unit: "%", source: "U.S. Treasury yield curve XML" },
          { displayName: "德国10Y", category: "global_yield", name: "德国10Y", label: "IRLTLT01DEM156N", unit: "%", source: "FRED IRLTLT01DEM156N" },
          { displayName: "英国10Y", category: "global_yield", name: "英国10Y", label: "IRLTLT01GBM156N", unit: "%", source: "FRED IRLTLT01GBM156N" },
          { displayName: "日本10Y", category: "global_yield", name: "日本10Y", label: "IRLTLT01JPM156N", unit: "%", source: "FRED IRLTLT01JPM156N" }
        ]
      },
      {
        id: "risk",
        label: "风险与美元",
        en: "Risk & USD",
        series: [
          { displayName: "S&P 500", category: "risk", name: "S&P 500", label: "SP500", unit: "index", source: "FRED SP500" },
          { displayName: "VIX", category: "risk", name: "VIX", label: "VIXCLS", unit: "index", source: "FRED VIXCLS" },
          { displayName: "美元广义指数", category: "fx", name: "美元广义指数", label: "DTWEXBGS", unit: "index", source: "FRED DTWEXBGS" }
        ]
      },
      {
        id: "inflation",
        label: "通胀与商品",
        en: "Inflation & Commodities",
        series: [
          { displayName: "达拉斯Trimmed Mean PCE", category: "inflation", name: "达拉斯联储Trimmed Mean PCE", label: "PCETRIM12M159SFRBDAL", unit: "%YoY", source: "FRED PCETRIM12M159SFRBDAL" },
          { displayName: "10Y盈亏平衡通胀", category: "inflation", name: "10Y盈亏平衡通胀", label: "T10YIE", unit: "%", source: "FRED T10YIE" },
          { displayName: "WTI原油", category: "commodity", name: "WTI原油", label: "DCOILWTICO", unit: "$/bbl", source: "FRED DCOILWTICO" }
        ]
      }
    ]
  },
  percentiles: {
    method: "Static fallback snapshot; served mode reads data/dashboard.json with daily-updated public sources.",
    trends: [
      {
        name: "银行准备金",
        source: "FRED WRESBAL",
        window: "5Y",
        viewWindow: "3Y",
        unit: "$T",
        latestPercentile: 22,
        change: 19,
        points: [
          { date: "2023-05-24", percentile: 66, value: 3.24 },
          { date: "2023-12-27", percentile: 75, value: 3.45 },
          { date: "2024-07-24", percentile: 58, value: 3.31 },
          { date: "2025-02-26", percentile: 58, value: 3.33 },
          { date: "2025-09-24", percentile: 5, value: 3.00 },
          { date: "2026-05-20", percentile: 22, value: 3.13 }
        ]
      },
      {
        name: "净流动性",
        source: "FRED WALCL - WTREGEN - RRPONTSYD",
        window: "5Y",
        viewWindow: "3Y",
        unit: "$T",
        latestPercentile: 13,
        change: 8,
        points: [
          { date: "2023-05-24", percentile: 92, value: 8.37 },
          { date: "2023-12-27", percentile: 48, value: 6.98 },
          { date: "2024-07-24", percentile: 33, value: 6.43 },
          { date: "2025-02-26", percentile: 22, value: 6.08 },
          { date: "2025-09-24", percentile: 7, value: 5.80 },
          { date: "2026-05-20", percentile: 13, value: 5.93 }
        ]
      },
      {
        name: "流动性动量",
        source: "Net liquidity 1M change",
        window: "5Y",
        viewWindow: "3Y",
        unit: "$T",
        latestPercentile: 55,
        change: 10,
        points: [
          { date: "2023-05-24", percentile: 27, value: -0.05 },
          { date: "2023-12-27", percentile: 19, value: -0.12 },
          { date: "2024-07-24", percentile: 27, value: -0.10 },
          { date: "2025-02-26", percentile: 37, value: -0.07 },
          { date: "2025-09-24", percentile: 7, value: -0.30 },
          { date: "2026-05-20", percentile: 55, value: -0.02 }
        ]
      },
      {
        name: "SOFR-EFFR利差",
        source: "FRED SOFR - DFF",
        window: "5Y",
        viewWindow: "3Y",
        unit: "bp",
        latestPercentile: 1,
        change: -85,
        points: [
          { date: "2023-05-22", percentile: 29, value: -3 },
          { date: "2023-12-21", percentile: 52, value: -2 },
          { date: "2024-07-24", percentile: 88, value: 1 },
          { date: "2025-02-26", percentile: 82, value: 0 },
          { date: "2025-09-26", percentile: 98, value: 7 },
          { date: "2026-05-21", percentile: 1, value: -11 }
        ]
      },
      {
        name: "VIX",
        source: "FRED VIXCLS",
        window: "5Y",
        viewWindow: "3Y",
        unit: "",
        latestPercentile: 38,
        change: -2,
        points: [
          { date: "2023-05-22", percentile: 33, value: 17.21 },
          { date: "2023-12-20", percentile: 11, value: 13.67 },
          { date: "2024-07-24", percentile: 43, value: 18.04 },
          { date: "2025-02-24", percentile: 46, value: 18.98 },
          { date: "2025-09-25", percentile: 35, value: 16.74 },
          { date: "2026-05-21", percentile: 38, value: 16.76 }
        ]
      },
      {
        name: "HY信用利差",
        source: "FRED BAMLH0A0HYM2",
        window: "5Y",
        viewWindow: "3Y",
        unit: "%",
        latestPercentile: 12,
        change: -5,
        points: [
          { date: "2023-06-13", percentile: 0, value: 4.18 },
          { date: "2024-01-15", percentile: 8, value: 3.54 },
          { date: "2024-08-15", percentile: 34, value: 3.31 },
          { date: "2025-03-19", percentile: 40, value: 3.19 },
          { date: "2025-10-20", percentile: 29, value: 2.99 },
          { date: "2026-05-21", percentile: 12, value: 2.78 }
        ]
      },
      {
        name: "美元广义指数",
        source: "FRED DTWEXBGS",
        window: "5Y",
        viewWindow: "3Y",
        unit: "",
        latestPercentile: 30,
        change: 4,
        points: [
          { date: "2023-05-15", percentile: 75, value: 119.16 },
          { date: "2023-12-15", percentile: 71, value: 119.74 },
          { date: "2024-07-19", percentile: 89, value: 123.15 },
          { date: "2025-02-21", percentile: 94, value: 127.14 },
          { date: "2025-09-22", percentile: 44, value: 119.82 },
          { date: "2026-05-15", percentile: 30, value: 119.28 }
        ]
      }
    ],
    movers: [
      { change: -85, direction: "down", name: "SOFR-EFFR利差", percentile: 1, source: "FRED SOFR - DFF", window: "5Y" },
      { change: 65, direction: "up", name: "拍卖投标倍数", percentile: 100, source: "TreasuryDirect auctioned securities", window: "available sample" },
      { change: 19, direction: "up", name: "银行准备金", percentile: 22, source: "FRED WRESBAL", window: "5Y" },
      { change: 10, direction: "up", name: "流动性动量", percentile: 55, source: "Net liquidity 1M change", window: "5Y" },
      { change: 8, direction: "up", name: "净流动性", percentile: 13, source: "FRED WALCL - WTREGEN - RRPONTSYD", window: "5Y" }
    ],
    alerts: [
      { message: "处于历史低分位区间", name: "SOFR-EFFR利差", percentile: 1, severity: "extreme", side: "low", source: "FRED SOFR - DFF", value: "-11bp" },
      { message: "处于历史高分位区间", name: "拍卖投标倍数", percentile: 100, severity: "extreme", side: "high", source: "TreasuryDirect auctioned securities", value: "4.60" }
    ]
  },
  events: [
    ["5/20", "FOMC 4月会议纪要", "中"],
    ["5/27-29", "2Y / 5Y / 7Y 国债拍卖", "中"],
    ["6/5", "5月非农就业报告", "高"],
    ["6/10", "5月 CPI 通胀数据", "高"],
    ["6/16-17", "FOMC 决议 + 经济预测/点阵图", "高"],
    ["~8月初", "季度再融资公告 (QRA)", "高"]
  ],
  news: [
    ["5/18", "U.S. Treasury", "日度收益率曲线更新:10Y 收于 4.61%,30Y 收于 5.14%"],
    ["5/18", "U.S. Treasury TIC", "3月海外持仓下降:日本和中国均减持美债"],
    ["5/15", "CNBC", "通胀数据指向棘手的利率路径,美债收益率走高"],
    ["5/14", "CNBC", "进出口物价大幅超预期,收益率维持高位震荡"],
    ["5/13", "CNBC", "PPI 数据火热,10年期收益率刷新年内新高"],
    ["5/12", "BLS", "4月 CPI 同比 3.8%,核心 CPI 同比 2.8%"]
  ],
  ideas: [
    { title: "战术减久期 / 维持低于基准久期", tag: "SHORT 久期", text: "CPI/PCE/核心PCE/Dallas Trimmed PCE 通胀跟踪仍偏热、政策路径向加息倾斜之前,组合久期保持低配。等待 PCE、核心PCE或Dallas Trimmed PCE动能转弱作为加回久期的触发条件。", source: "宏观基本面 · 货币政策", confidenceLevel: "medium", confidenceLabel: "中等可信", confidenceNote: "静态兜底数据未运行结论审计。" },
    { title: "做陡 5s30s 曲线", tag: "CURVE 做陡", text: "前端被按兵不动的美联储锚定,长端受供给压力、期限溢价上行和海外需求走弱三重拖累。熊市变陡是当前结构最顺的曲线方向。", source: "供给与技术面 · 需求与持仓", confidenceLevel: "medium", confidenceLabel: "中等可信", confidenceNote: "静态兜底数据未运行结论审计。" },
    { title: "前端持有 · 吃 carry", tag: "LONG 前端", text: "2Y 收益率被政策锚定、波动相对可控,持有票息回报为正且 roll-down 友好。相对长端,前端是风险调整后更优的久期敞口。", source: "货币政策 · 相对价值", confidenceLevel: "medium", confidenceLabel: "中等可信", confidenceNote: "静态兜底数据未运行结论审计。" },
    { title: "战术做多盈亏平衡通胀", tag: "RV 通胀", text: "能源冲击向PCE、核心PCE和Dallas Trimmed PCE传导过程中,买入盈亏平衡可对冲通胀上行。属战术性头寸,需在PCE/核心PCE/Dallas Trimmed PCE或能源价格降温时了结。", source: "跨市场 · 宏观基本面", confidenceLevel: "medium", confidenceLabel: "中等可信", confidenceNote: "静态兜底数据未运行结论审计。" }
  ]
};

const STORAGE_KEY = "the-dial-treasury-v1-state";
const LANGUAGE_STORAGE_KEY = "the-dial-treasury-v1-language";
const RUNTIME_AUTO_REFRESH_MS = 5 * 60 * 1000;
const EQUITY_FRESHNESS_FAST_REFRESH_MS = 60 * 1000;
const EQUITY_FRESHNESS_NEAR_READY_MINUTES = 30;
const I18N = window.TreasuryI18n;
const IDEA_SPY_PROXY_LABEL = "S&P 500 price-index proxy for SPY";
let currentLanguage = I18N.normalizeLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY) || document.documentElement.lang);
let state = hydrateState(DEFAULT_DATA);
let runtimeDataStatus = {
  mode: "static",
  key: "status.static",
  values: {}
};
let runtimeRefreshInFlight = false;
let equityRefreshInFlight = false;
let runtimeSnapshotRefreshInFlight = false;
let equityFreshnessStatus = null;
let runtimeAutoRefreshTimer = null;
let equityFreshnessRefreshTimer = null;
let equityFreshnessRefreshInFlight = false;
let sourceStatusFilter = "all";
let sourceStatusQuery = "";
let percentileTrendCache = [];
let percentileModalMode = "all";
let percentileFocusedTrend = "";
let historySummaryCache = null;
let historyStatsCache = [];
let selectedHistorySeriesKey = "";
let historyRangeYears = 5;
let crossHistoryGroup = "global";
let selectedCrossHistorySeriesKey = "";
let crossHistoryRangeYears = 3;
const CORE_PERCENTILE_TRENDS = ["银行准备金", "净流动性", "13周净流动性动量", "TGA偏离度"];
const DEFAULT_PERCENTILE_TREND_LIMIT = 4;
const PREFERRED_HISTORY_SERIES = ["10Y收益率", "2Y收益率", "30Y收益率", "2s10s斜率", "净流动性", "13周净流动性动量", "TGA偏离度", "商票-TBill利差", "金融条件指数(NFCI)", "SOFR-EFFR利差", "VIX", "HY信用利差", "拍卖投标倍数"];
const SOURCE_STATUS_FILTERS = [
  { id: "all", label: "全部" },
  { id: "ok", label: "真实" },
  { id: "modeled", label: "模型" },
  { id: "problem", label: "问题" },
];
const CONCLUSION_SOURCE_QUALITY = {
  "real-public": 1,
  "derived-public": 0.9,
  "official-news": 0.8,
  "proxy-public": 0.65,
  "modeled": 0.55,
  "manual-placeholder": 0.25
};
const LOWER_CONFIDENCE_SOURCE_MODES = new Set(["proxy-public", "modeled", "manual-placeholder"]);
const PERCENTILE_MODAL_MODES = [
  { id: "all", label: "全部", title: "全部因子" },
  { id: "core", label: "核心", title: "核心4项" },
  { id: "stress", label: "极端/异动", title: "极端/异动因子" },
];

function t(key, values) {
  return values ? I18N.format(currentLanguage, key, values) : I18N.translate(currentLanguage, key);
}

function hydrateState(baseData = DEFAULT_DATA) {
  const data = structuredClone(baseData);
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    if (saved.groups) {
      data.groups.forEach((group) => {
        const savedGroup = saved.groups.find((item) => item.id === group.id);
        if (!savedGroup) return;
        if (Number.isFinite(savedGroup.weight)) group.weight = savedGroup.weight;
        group.factors.forEach((factor, index) => {
          const score = savedGroup.scores?.[index];
          if (Number.isFinite(score)) factor.score = score;
        });
      });
    }
    if (saved.ideas) {
      data.ideas.forEach((idea, index) => {
        if (typeof saved.ideas[index] === "string") idea.text = saved.ideas[index];
      });
    }
  } catch (error) {
    console.warn("Failed to load saved treasury state", error);
  }
  return data;
}

async function loadRuntimeData(options = {}) {
  const refreshHistory = options.refreshHistory !== false;
  const preserveOnError = options.preserveOnError === true;
  const refreshFreshness = options.refreshFreshness !== false;
  if (window.location.protocol === "file:") {
    runtimeDataStatus = {
      mode: "static",
      key: "status.file",
      values: {}
    };
    renderAll();
    renderEquityFreshnessStatus(null);
    if (refreshHistory) renderHistoryUnavailable("HTTP 服务模式下显示 SQLite 历史数据");
    return;
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    const response = await fetch(`data/dashboard.json?ts=${Date.now()}`, { cache: "no-store", signal: controller.signal });
    clearTimeout(timeout);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const liveData = await response.json();
    state = hydrateState(liveData);
    const generatedAt = liveData.generatedAt ? new Date(liveData.generatedAt).toLocaleString(currentLanguage === "en" ? "en-US" : "zh-CN") : t("status.unknown");
    const okCount = (liveData.sourceStatus || []).filter((source) => source.status === "ok").length;
    runtimeDataStatus = {
      mode: "live",
      key: "status.live",
      values: { asOf: liveData.asOf, generatedAt, okCount }
    };
  } catch (error) {
    console.warn("Failed to load generated treasury data", error);
    if (!preserveOnError) state = hydrateState(DEFAULT_DATA);
    runtimeDataStatus = {
      mode: "error",
      key: "status.error",
      values: { error: error.message }
    };
  }
  renderAll();
  if (refreshFreshness) await loadEquityFreshnessStatus();
  if (refreshHistory) await loadHistoryData();
}

async function loadEquityFreshnessStatus() {
  if (window.location.protocol === "file:") {
    renderEquityFreshnessStatus(null);
    return;
  }
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const response = await fetch(`/api/health?ts=${Date.now()}`, { cache: "no-store", signal: controller.signal });
    clearTimeout(timeout);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    equityFreshnessStatus = payload.equityRiskFreshness || null;
    renderEquityFreshnessStatus(equityFreshnessStatus);
    scheduleEquityFreshnessRefresh(equityFreshnessStatus);
  } catch (error) {
    console.warn("Failed to load equity risk freshness", error);
    equityFreshnessStatus = { stale: true, error: error.message };
    renderEquityFreshnessStatus(equityFreshnessStatus);
    scheduleEquityFreshnessRefresh(equityFreshnessStatus);
  }
}

function equityFreshnessRefreshDelay(freshness) {
  if (!freshness) return RUNTIME_AUTO_REFRESH_MS;
  const phase = freshness.phase || "";
  const minutesUntilExpected = Number(freshness.minutesUntilExpected);
  if (freshness.stale || freshness.timeliness === "catchup" || phase === "catchup") {
    return EQUITY_FRESHNESS_FAST_REFRESH_MS;
  }
  if (
    freshness.timeliness === "waiting"
    && Number.isFinite(minutesUntilExpected)
    && minutesUntilExpected <= EQUITY_FRESHNESS_NEAR_READY_MINUTES
  ) {
    return EQUITY_FRESHNESS_FAST_REFRESH_MS;
  }
  return RUNTIME_AUTO_REFRESH_MS;
}

function scheduleEquityFreshnessRefresh(freshness) {
  if (window.location.protocol === "file:") return;
  clearTimeout(equityFreshnessRefreshTimer);
  equityFreshnessRefreshTimer = window.setTimeout(
    refreshEquityFreshnessSilently,
    equityFreshnessRefreshDelay(freshness)
  );
}

async function refreshEquityFreshnessSilently() {
  if (equityFreshnessRefreshInFlight) return;
  if (document.visibilityState === "hidden") {
    scheduleEquityFreshnessRefresh(equityFreshnessStatus);
    return;
  }
  equityFreshnessRefreshInFlight = true;
  try {
    const fast = equityFreshnessRefreshDelay(equityFreshnessStatus) === EQUITY_FRESHNESS_FAST_REFRESH_MS;
    if (fast && canAutoRefreshRuntimeSnapshot()) {
      await refreshRuntimeSnapshotSilently();
    } else {
      await loadEquityFreshnessStatus();
    }
  } finally {
    equityFreshnessRefreshInFlight = false;
  }
}

function renderEquityFreshnessStatus(freshness) {
  const node = $("#equityFreshnessStatus");
  if (!node) return;
  node.classList.remove("equity-freshness-ok", "equity-freshness-waiting", "equity-freshness-stale", "equity-freshness-error");
  if (!freshness) {
    node.textContent = "股市日线 --";
    node.title = "短期股市日线同步状态";
    return;
  }
  const sourceDate = freshness.sourceDate || "--";
  const expectedDate = freshness.expectedDate || "--";
  const phase = freshness.phase || "";
  const minutesUntilExpected = Number(freshness.minutesUntilExpected);
  const minutesSinceExpected = Number(freshness.minutesSinceExpected);
  if (freshness.error) {
    node.classList.add("equity-freshness-error");
    node.textContent = "股市日线检查失败";
    node.title = String(freshness.error);
    return;
  }
  if (freshness.stale) {
    node.classList.add("equity-freshness-stale");
    const lagText = Number.isFinite(minutesSinceExpected) ? ` · 已到期${minutesSinceExpected}m` : "";
    node.textContent = `股市日线追赶中 ${sourceDate}`;
    node.title = `短期股市日线滞后: source ${sourceDate}, expected ${expectedDate}${lagText}; 后台将进入 catch-up 刷新。`;
    return;
  }
  if (freshness.timeliness === "waiting" || phase === "post_close_wait" || phase === "trading_session") {
    node.classList.add("equity-freshness-waiting");
    const waitText = Number.isFinite(minutesUntilExpected) ? `${minutesUntilExpected}m` : "--";
    node.textContent = phase === "trading_session" ? `股市日线盘中 ${sourceDate}` : `股市日线等待 ${waitText}`;
    node.title = `短期股市日线正常等待: source ${sourceDate}, expected ${expectedDate}, readyAt ${freshness.readyAt || "--"}`;
    return;
  }
  node.classList.add("equity-freshness-ok");
  node.textContent = `股市日线已同步 ${sourceDate}`;
  node.title = `短期股市日线已同步: source ${sourceDate}, expected ${expectedDate}, phase ${phase || "fresh"}`;
}

function setRuntimeRefreshBusy(isBusy) {
  const button = $("#refreshRuntimeData");
  if (!button) return;
  button.disabled = isBusy;
  button.textContent = isBusy ? "刷新中" : "刷新";
}

function setEquityRefreshBusy(isBusy) {
  const button = $("#refreshEquityRisk");
  if (!button) return;
  button.disabled = isBusy;
  button.textContent = isBusy ? "股市中" : "股市";
}

async function refreshRuntimeData() {
  if (runtimeRefreshInFlight) return;
  runtimeRefreshInFlight = true;
  setRuntimeRefreshBusy(true);
  try {
    if (window.location.protocol === "file:") {
      await loadRuntimeData();
      toast("file 模式只能读取静态快照");
      return;
    }
    const response = await fetch("/api/update", { method: "POST", cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json().catch(() => ({}));
    toast(payload.status === "running" ? "后台刷新正在运行" : "后台刷新已启动");
    window.setTimeout(() => loadRuntimeData(), 1800);
  } catch (error) {
    console.warn("Failed to trigger treasury data update", error);
    await loadRuntimeData();
    toast("刷新接口不可用,已重新读取当前快照");
  } finally {
    runtimeRefreshInFlight = false;
    setRuntimeRefreshBusy(false);
  }
}

async function refreshEquityRisk() {
  if (equityRefreshInFlight) return;
  equityRefreshInFlight = true;
  setEquityRefreshBusy(true);
  try {
    if (window.location.protocol === "file:") {
      await loadRuntimeData();
      toast("file 模式只能读取静态快照");
      return;
    }
    const response = await fetch("/api/update-equity", { method: "POST", cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json().catch(() => ({}));
    if (payload.equityRiskFreshness) {
      equityFreshnessStatus = payload.equityRiskFreshness;
      renderEquityFreshnessStatus(equityFreshnessStatus);
      scheduleEquityFreshnessRefresh(equityFreshnessStatus);
    }
    toast(payload.status === "running" ? "股市风险刷新正在运行" : "股市风险刷新已启动");
    window.setTimeout(() => loadRuntimeData({ refreshHistory: false }), 1200);
  } catch (error) {
    console.warn("Failed to trigger equity risk update", error);
    await loadRuntimeData({ refreshHistory: false });
    toast("股市刷新接口不可用,已重新读取当前快照");
  } finally {
    equityRefreshInFlight = false;
    setEquityRefreshBusy(false);
  }
}

function canAutoRefreshRuntimeSnapshot() {
  return window.location.protocol !== "file:"
    && document.visibilityState !== "hidden"
    && !runtimeRefreshInFlight
    && !equityRefreshInFlight
    && !runtimeSnapshotRefreshInFlight;
}

async function refreshRuntimeSnapshotSilently() {
  if (!canAutoRefreshRuntimeSnapshot()) return;
  runtimeSnapshotRefreshInFlight = true;
  try {
    await loadRuntimeData({ refreshHistory: false, preserveOnError: true });
  } finally {
    runtimeSnapshotRefreshInFlight = false;
  }
}

function startRuntimeAutoRefresh() {
  if (runtimeAutoRefreshTimer || window.location.protocol === "file:") return;
  runtimeAutoRefreshTimer = window.setInterval(refreshRuntimeSnapshotSilently, RUNTIME_AUTO_REFRESH_MS);
}

function persistState() {
  const payload = {
    groups: state.groups.map((group) => ({
      id: group.id,
      weight: group.weight,
      scores: group.factors.map((factor) => factor.score)
    })),
    ideas: state.ideas.map((idea) => idea.text)
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const fmt = (value, digits = 0) => `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
const scoreClass = (score) => (score > 0 ? "bull" : score < 0 ? "bear" : "neutral");
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "\"": "&quot;",
  "'": "&#39;"
})[char]);

function stanceLabel(score) {
  if (score <= -1.3) return [t("stance.strongDurationBear"), "SELL"];
  if (score <= -0.5) return [t("stance.durationBear"), "SELL"];
  if (score <= -0.18) return [t("stance.slightBear"), "HOLD"];
  if (score < 0.18) return [t("stance.neutral"), "HOLD"];
  if (score < 0.5) return [t("stance.slightBull"), "BUY"];
  if (score < 1.3) return [t("stance.durationBull"), "BUY"];
  return [t("stance.strongDurationBull"), "BUY"];
}

function curveLabel(score) {
  if (score <= -0.55) return [t("curve.flattener"), "FLATTENER"];
  if (score < -0.15) return [t("curve.slightFlat"), "FLATTENER"];
  if (score <= 0.15) return [t("curve.neutral"), "NEUTRAL"];
  if (score < 0.75) return [t("curve.steepener"), "STEEPENER"];
  return [t("curve.strongSteepener"), "STEEPENER"];
}

function conclusionSourceQuality(mode) {
  return CONCLUSION_SOURCE_QUALITY[String(mode || "real-public")] ?? 1;
}

function conclusionConfidenceLevel(evidenceQuality, concentration, warningCount, errorCount) {
  if (errorCount > 0) return "low";
  if (evidenceQuality >= 0.82 && concentration <= 0.45 && warningCount === 0) return "high";
  if (evidenceQuality >= 0.62 && concentration <= 0.65) return "medium";
  return "low";
}

function buildWeightRecommendation(evidenceQuality, concentration, proxyShare, warningCount, errorCount) {
  const notes = [];
  if (errorCount > 0) notes.push("存在关键数据源错误,结论应降级,暂不提高受影响因子的权重。");
  else if (warningCount > 0) notes.push("存在数据源警告,结论可信度不应上调到高。");
  if (proxyShare >= 0.25 || evidenceQuality < 0.82) {
    notes.push("代理/模型因子占比偏高,权重不宜继续提高代理因子;优先接入真实市场源或降低结论措辞强度。");
  }
  if (concentration > 0.45) notes.push("单一因子贡献集中,避免让一个模块主导总判断。");
  if (!notes.length) notes.push("当前权重暂不需要机械调整;保留模块权重,新增真实数据源后再重估。");
  return notes.join("");
}

function aggregateDetails(groups = state.groups, rows = sourceStatusRows()) {
  let durationWeighted = 0;
  let curveWeighted = 0;
  const drivers = [];
  const groupDiagnostics = [];
  const totalWeight = groups.reduce((sum, group) => sum + Math.max(0, Number(group.weight) || 0), 0);
  groups.forEach((group) => {
    const factors = Array.isArray(group.factors) ? group.factors : [];
    if (!factors.length) return;
    const weight = Math.max(0, Number(group.weight) || 0);
    const normalizedWeight = totalWeight ? weight / totalWeight : 0;
    const durationAvg = factors.reduce((sum, factor) => sum + (Number(factor.score) || 0), 0) / factors.length;
    const curveAvg = factors.reduce((sum, factor) => sum + (Number(factor.curve) || 0), 0) / factors.length;
    durationWeighted += durationAvg * normalizedWeight;
    curveWeighted += curveAvg * normalizedWeight;
    let qualityNumerator = 0;
    let qualityWeight = 0;
    factors.forEach((factor) => {
      const score = Number(factor.score) || 0;
      const curve = Number(factor.curve) || 0;
      const contribution = score * normalizedWeight / factors.length;
      const curveContribution = curve * normalizedWeight / factors.length;
      const mode = String(factor.sourceMode || "real-public");
      const quality = conclusionSourceQuality(mode);
      const qualityBase = Math.max(Math.abs(contribution), Math.abs(curveContribution), 0.01);
      qualityNumerator += quality * qualityBase;
      qualityWeight += qualityBase;
      if (contribution === 0 && curveContribution === 0) return;
      drivers.push({
        module: currentLanguage === "en" ? group.en : group.name,
        moduleEn: group.en || group.name,
        name: factor.n || factor.name || "",
        value: factor.v || factor.tag || "",
        sourceMode: mode,
        quality,
        contribution,
        curveContribution
      });
    });
    groupDiagnostics.push({
      name: currentLanguage === "en" ? group.en : group.name,
      weight,
      factorCount: factors.length,
      durationAverage: durationAvg,
      curveAverage: curveAvg,
      durationContribution: durationAvg * normalizedWeight,
      evidenceQuality: qualityWeight ? qualityNumerator / qualityWeight : 1
    });
  });
  const sortedDrivers = drivers.sort((left, right) => Math.abs(right.contribution) - Math.abs(left.contribution));
  const absoluteTotal = sortedDrivers.reduce((sum, item) => sum + Math.abs(item.contribution), 0);
  const evidenceQuality = absoluteTotal
    ? sortedDrivers.reduce((sum, item) => sum + Math.abs(item.contribution) * item.quality, 0) / absoluteTotal
    : 1;
  const proxyContribution = sortedDrivers.reduce((sum, item) => (
    LOWER_CONFIDENCE_SOURCE_MODES.has(item.sourceMode) ? sum + Math.abs(item.contribution) : sum
  ), 0);
  const concentration = absoluteTotal ? Math.abs(sortedDrivers[0]?.contribution || 0) / absoluteTotal : 0;
  const warningCount = rows.filter((source) => ["warning", "warn"].includes(normalizedSourceStatus(source))).length;
  const errorCount = rows.filter((source) => normalizedSourceStatus(source) === "error").length;
  const proxyShare = absoluteTotal ? proxyContribution / absoluteTotal : 0;
  const level = conclusionConfidenceLevel(evidenceQuality, concentration, warningCount, errorCount);
  return {
    duration: { score: durationWeighted, label: stanceLabel(durationWeighted)[0] },
    curve: { score: curveWeighted, label: curveLabel(curveWeighted)[0] },
    confidence: {
      level,
      label: ({ high: "高", medium: "中等", low: "低" })[level],
      evidenceQuality,
      concentration,
      proxyContributionShare: proxyShare
    },
    sourceWarningCount: warningCount,
    sourceErrorCount: errorCount,
    weightRecommendation: buildWeightRecommendation(evidenceQuality, concentration, proxyShare, warningCount, errorCount),
    drivers: sortedDrivers.slice(0, 8),
    groupDiagnostics
  };
}

function aggregates() {
  const details = aggregateDetails();
  return {
    duration: details.duration.score,
    curve: details.curve.score
  };
}

function renderAll() {
  applyLanguage();
  $("[data-field='asOf']").textContent = state.asOf;
  renderDataStatus();
  renderHero();
  renderCurve();
  renderDecomposition();
  renderScorecard();
  renderPolicy();
  renderSupply();
  renderPositioning();
  renderCrossMarket();
  renderEvents();
  renderIdeas();
  bindNavObserver();
}

function renderDataStatus() {
  const node = $("#dataStatus");
  if (!node) return;
  node.textContent = t(runtimeDataStatus.key, runtimeDataStatus.values);
  node.dataset.mode = runtimeDataStatus.mode;
}

function sourceStatusRows() {
  const rows = Array.isArray(state.sourceStatus) ? state.sourceStatus : [];
  if (rows.length) return rows;
  return [{
    latest: state.asOf || "--",
    name: runtimeDataStatus.mode === "file" || runtimeDataStatus.mode === "static" ? "Static fallback snapshot" : "Dashboard data",
    status: runtimeDataStatus.mode === "live" ? "unknown" : "static",
  }];
}

function sourceStatusCounts(rows = sourceStatusRows()) {
  return rows.reduce((counts, source) => {
    const status = normalizedSourceStatus(source);
    counts.total += 1;
    if (status === "ok") counts.ok += 1;
    else if (status === "modeled") counts.modeled += 1;
    else if (status === "error") counts.error += 1;
    else if (status === "warning" || status === "warn") counts.warning += 1;
    else counts.other += 1;
    return counts;
  }, { total: 0, ok: 0, modeled: 0, error: 0, warning: 0, other: 0 });
}

function normalizedSourceStatus(sourceOrStatus) {
  const raw = typeof sourceOrStatus === "object"
    ? sourceOrStatus?.status
    : sourceOrStatus;
  return String(raw || "unknown").toLowerCase();
}

function sourceStatusLabel(status) {
  const normalized = normalizedSourceStatus(status);
  if (normalized === "ok") return "真实公共源";
  if (normalized === "modeled") return "模型/代理";
  if (normalized === "error") return "错误";
  if (normalized === "warning" || normalized === "warn") return "警告";
  if (normalized === "static") return "静态备用";
  return "未知";
}

function sourceStatusClass(status) {
  return normalizedSourceStatus(status).replace(/[^a-z0-9_-]/g, "") || "unknown";
}

function sourceStatusMatchesFilter(source, filter = sourceStatusFilter) {
  const status = normalizedSourceStatus(source);
  if (filter === "ok") return status === "ok";
  if (filter === "modeled") return status === "modeled";
  if (filter === "problem") return status === "error" || status === "warning" || status === "warn";
  return true;
}

function sourceStatusSearchText(source) {
  return [source.name, source.status, source.latest, source.note]
    .map((value) => String(value || "").toLowerCase())
    .join(" ");
}

function filterSourceStatusRows(rows = sourceStatusRows()) {
  const query = sourceStatusQuery.trim().toLowerCase();
  return rows.filter((source) => {
    if (!sourceStatusMatchesFilter(source)) return false;
    if (!query) return true;
    return sourceStatusSearchText(source).includes(query);
  });
}

function renderSourceStatusControls(rows, visibleCount) {
  const group = $("#sourceStatusFilterGroup");
  const search = $("#sourceStatusSearch");
  const visible = $("#sourceStatusVisibleCount");
  if (group) {
    group.innerHTML = SOURCE_STATUS_FILTERS.map((filter) => {
      const count = rows.filter((source) => sourceStatusMatchesFilter(source, filter.id)).length;
      return `<button type="button" class="${sourceStatusFilter === filter.id ? "active" : ""}" data-source-filter="${filter.id}">${filter.label}<span>${count}</span></button>`;
    }).join("");
  }
  if (search && search.value !== sourceStatusQuery) search.value = sourceStatusQuery;
  if (visible) visible.textContent = `显示 ${visibleCount} / ${rows.length}`;
}

function renderSourceStatusModal() {
  const rows = sourceStatusRows();
  const counts = sourceStatusCounts(rows);
  const generatedAt = state.generatedAt ? new Date(state.generatedAt).toLocaleString(currentLanguage === "en" ? "en-US" : "zh-CN") : t("status.unknown");
  const summary = $("#sourceStatusSummary");
  const table = $("#sourceStatusTable");
  if (!summary || !table) return;
  summary.innerHTML = [
    ["真实公共源", counts.ok, "直接来自官方或公开市场数据"],
    ["模型/代理", counts.modeled, "明确标注的模型估算或公共代理"],
    ["错误/警告", counts.error + counts.warning, "刷新失败或低置信数据源"],
    ["快照", state.asOf || "--", generatedAt],
  ].map(([label, value, note]) => `
    <div class="source-status-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(note)}</small>
    </div>
  `).join("");
  const visibleRows = filterSourceStatusRows(rows);
  renderSourceStatusControls(rows, visibleRows.length);
  const statusOrder = { error: 0, warning: 1, warn: 1, modeled: 2, static: 3, unknown: 4, ok: 5 };
  const sorted = [...visibleRows].sort((a, b) => {
    const aStatus = normalizedSourceStatus(a);
    const bStatus = normalizedSourceStatus(b);
    return (statusOrder[aStatus] ?? 4) - (statusOrder[bStatus] ?? 4) || String(a.name || "").localeCompare(String(b.name || ""));
  });
  table.innerHTML = `
    <thead>
      <tr><th>状态</th><th>数据源</th><th>最新日期 / 说明</th></tr>
    </thead>
    <tbody>
      ${sorted.length ? sorted.map((source) => `
        <tr>
          <td><span class="status-badge ${sourceStatusClass(source.status)}">${sourceStatusLabel(source.status)}</span></td>
          <td>${escapeHtml(source.name || "--")}</td>
          <td>${escapeHtml(source.latest || source.note || "--")}</td>
        </tr>
      `).join("") : `<tr><td colspan="3" class="empty-table-cell">没有匹配数据源</td></tr>`}
    </tbody>
  `;
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function exportSourceStatusCsv() {
  const rows = filterSourceStatusRows();
  const csv = [
    ["status", "label", "name", "latest_or_note"].map(csvCell).join(","),
    ...rows.map((source) => [
      source.status || "unknown",
      sourceStatusLabel(source.status),
      source.name || "",
      source.latest || source.note || "",
    ].map(csvCell).join(",")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `treasury-source-status-${state.asOf || "snapshot"}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  toast("数据源CSV已导出");
}

function openSourceStatusModal() {
  const modal = $("#sourceStatusModal");
  if (!modal) return;
  renderSourceStatusModal();
  modal.hidden = false;
  document.body.classList.add("modal-open");
  $("#closeSourceStatusModal")?.focus();
}

function closeSourceStatusModal() {
  const modal = $("#sourceStatusModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function applyLanguage() {
  document.documentElement.lang = currentLanguage === "en" ? "en" : "zh-CN";
  $$("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  $$("[data-i18n-html]").forEach((node) => {
    node.innerHTML = t(node.dataset.i18nHtml);
  });
  $$("[data-i18n-title]").forEach((node) => {
    node.title = t(node.dataset.i18nTitle);
  });
  const toggle = $("#languageToggle");
  if (toggle) {
    toggle.textContent = currentLanguage === "en" ? "中" : "EN";
    toggle.setAttribute("aria-label", t("button.language"));
  }
}

function setLanguage(language) {
  currentLanguage = I18N.normalizeLanguage(language);
  localStorage.setItem(LANGUAGE_STORAGE_KEY, currentLanguage);
  renderAll();
}

function renderHero() {
  const C = state.curve;
  const idx = { "2Y": 4, "5Y": 6, "10Y": 8, "30Y": 10 };
  const tiles = Object.entries(idx).map(([label, index]) => ({
    label,
    value: `${C.today[index].toFixed(2)}%`,
    change: `${fmt(C.d1[index] * 100, 0).replace("-", "−")} bp`,
    cls: C.d1[index] > 0 ? "up" : C.d1[index] < 0 ? "down" : "flat"
  }));
  const s2s10 = (C.today[8] - C.today[4]) * 100;
  const s5s30 = (C.today[10] - C.today[6]) * 100;
  tiles.push(
    { label: t("curve.slope2s10s"), value: `${Math.round(s2s10)} bp`, change: t("curve.steepening"), cls: "flat" },
    { label: t("curve.slope5s30s"), value: `${Math.round(s5s30)} bp`, change: t("curve.steepening"), cls: "flat" }
  );
  $("#heroTiles").innerHTML = tiles.map((tile) => `
    <div class="tile">
      <div class="lab">${tile.label}</div>
      <div class="val">${tile.value}</div>
      <div class="chg ${tile.cls}">${tile.change}</div>
    </div>
  `).join("");

  const score = aggregates();
  const [durationText, durationCode] = stanceLabel(score.duration);
  const [curveText, curveCode] = curveLabel(score.curve);
  $("#durationStance").textContent = durationText;
  $("#durationScore").textContent = `${t("score.composite")} ${score.duration.toFixed(2)} · ${durationCode}`;
  $("#durationStance").parentElement.dataset.code = durationCode;
  $("#curveStance").textContent = curveText;
  $("#curveScore").textContent = `${t("score.curve")} ${score.curve.toFixed(2)} · ${curveCode}`;
  $("#curveStance").parentElement.dataset.code = curveCode === "STEEPENER" ? "STEEP" : curveCode;
  renderConclusionAudit();
}

function renderConclusionAudit() {
  const node = $("#conclusionAudit");
  if (!node) return;
  const audit = aggregateDetails();
  const topDrag = audit.drivers.find((item) => item.contribution < 0);
  const topBuffer = audit.drivers.find((item) => item.contribution > 0);
  const warningText = audit.sourceErrorCount > 0
    ? `${audit.sourceErrorCount} error`
    : audit.sourceWarningCount > 0
      ? `${audit.sourceWarningCount} warning`
      : "clean";
  const cards = [
    ["结论可信度", audit.confidence.label, audit.confidence.level],
    ["证据质量", `${Math.round(audit.confidence.evidenceQuality * 100)}%`, audit.confidence.evidenceQuality >= 0.82 ? "high" : "medium"],
    ["权重集中", `${Math.round(audit.confidence.concentration * 100)}%`, audit.confidence.concentration > 0.45 ? "low" : "high"],
    ["代理/模型占比", `${Math.round(audit.confidence.proxyContributionShare * 100)}%`, audit.confidence.proxyContributionShare >= 0.25 ? "medium" : "high"],
    ["数据源状态", warningText, audit.sourceErrorCount > 0 ? "low" : audit.sourceWarningCount > 0 ? "medium" : "high"]
  ];
  node.innerHTML = `
    <div class="conclusion-audit-head">
      <span>结论审计 · Conclusion Audit</span>
      <strong>${escapeHtml(audit.duration.label)} / ${escapeHtml(audit.curve.label)}</strong>
    </div>
    <div class="conclusion-audit-grid">
      ${cards.map(([label, value, tone]) => `
        <div class="audit-metric ${escapeHtml(tone)}">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `).join("")}
    </div>
    <div class="conclusion-audit-read">
      <span><b>主要拖累</b>${escapeHtml(topDrag ? `${topDrag.name} ${topDrag.contribution.toFixed(2)}` : "无")}</span>
      <span><b>主要缓冲</b>${escapeHtml(topBuffer ? `${topBuffer.name} +${topBuffer.contribution.toFixed(2)}` : "无")}</span>
      <span><b>权重建议</b>${escapeHtml(audit.weightRecommendation)}</span>
    </div>
  `;
}

function renderCurve() {
  const C = state.curve;
  drawCurveChart("#curveChart", C);
  const s2s10 = (C.today[8] - C.today[4]) * 100;
  const s5s30 = (C.today[10] - C.today[6]) * 100;
  const s3m10 = (C.today[8] - C.today[1]) * 100;
  const fly = (2 * C.today[6] - C.today[4] - C.today[8]) * 100;
  const metrics = [
    ["2s10s", `${Math.round(s2s10)} bp`, t("curve.positiveBearSteepener")],
    ["5s30s", `${Math.round(s5s30)} bp`, t("curve.longEndSteepening")],
    ["3m10y", `${Math.round(s3m10)} bp`, t("curve.positiveAgain")],
    [t("curve.butterfly"), `${fmt(Math.round(fly))} bp`, t("curve.bellyCheap")]
  ];
  $("#curveMetrics").innerHTML = metrics.map(metricCard).join("");
  $("#curveTable").innerHTML = `
    <thead><tr><th>${t("table.tenor")}</th><th>${t("table.yield")}</th><th>${t("table.day")}</th><th>${t("table.week")}</th><th>${t("table.month")}</th></tr></thead>
    <tbody>
      ${C.tenors.map((tenor, i) => `
        <tr>
          <td><strong>${tenor}</strong></td>
          <td class="mono">${C.today[i].toFixed(2)}%</td>
          <td class="${C.d1[i] > 0 ? "bear" : C.d1[i] < 0 ? "bull" : "neutral"}">${fmt(C.d1[i] * 100, 0)} bp</td>
          <td>${fmt((C.today[i] - C.w1[i]) * 100, 0)} bp</td>
          <td>${fmt((C.today[i] - C.m1[i]) * 100, 0)} bp</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function drawCurveChart(selector, C) {
  const W = 720;
  const H = 340;
  const pad = { l: 46, r: 18, t: 22, b: 42 };
  const series = [
    { name: "today", values: C.today, color: "var(--accent)", width: 3 },
    { name: "week", values: C.w1, color: "var(--accent-2)", width: 2 },
    { name: "month", values: C.m1, color: "var(--neutral)", width: 2 }
  ];
  const all = series.flatMap((item) => item.values);
  const min = Math.floor(Math.min(...all) * 10) / 10 - 0.05;
  const max = Math.ceil(Math.max(...all) * 10) / 10 + 0.05;
  const x = (i) => pad.l + (i / (C.tenors.length - 1)) * (W - pad.l - pad.r);
  const y = (value) => pad.t + ((max - value) / (max - min)) * (H - pad.t - pad.b);
  const path = (values) => values.map((value, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const yTicks = [min, (min + max) / 2, max];
  $(selector).innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Yield curve chart">
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      ${yTicks.map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(tick)}" y2="${y(tick)}" stroke="var(--line-soft)"></line>
        <text x="8" y="${y(tick) + 4}" fill="var(--muted)" font-size="12" font-family="var(--mono)">${tick.toFixed(1)}%</text>
      `).join("")}
      ${C.tenors.map((tenor, i) => `
        <text x="${x(i)}" y="${H - 12}" text-anchor="middle" fill="var(--muted)" font-size="11" font-family="var(--mono)">${tenor}</text>
      `).join("")}
      ${series.map((item) => `
        <path d="${path(item.values)}" fill="none" stroke="${item.color}" stroke-width="${item.width}" stroke-linejoin="round" stroke-linecap="round"></path>
        ${item.values.map((value, i) => `<circle cx="${x(i)}" cy="${y(value)}" r="${item.name === "today" ? 3.5 : 2.5}" fill="${item.color}"></circle>`).join("")}
      `).join("")}
    </svg>
  `;
}

function renderDecomposition() {
  const C = state.curve;
  const tenYearIndex = C.tenors.indexOf("10Y");
  const twoYearIndex = C.tenors.indexOf("2Y");
  const tenYear = C.today[tenYearIndex];
  const twoYear = C.today[twoYearIndex];
  const monthRow = state.decomposition.attribution.find((item) => item.window === "1 月");
  const measures = state.decomposition.marketMeasures || {};
  const realRate = measures.real10y || sourceValue("DFII10") || sourceValue("实际利率") || "--";
  const breakeven = measures.breakeven10y || sourceValue("T10YIE") || sourceValue("盈亏平衡") || "--";
  const dff = policyValue("有效联邦基金利率") || "--";
  const policyGap = Number.isFinite(tenYear) && parseFloat(dff) ? `${(tenYear - parseFloat(dff)).toFixed(2)}%` : "--";
  $("#nominalYield").textContent = `${tenYear.toFixed(2)}%`;
  $("#nominalMove").textContent = `${fmt(monthRow?.total || 0, 0)}bp · 1月`;
  $("#fundamentalEquation").textContent = `${tenYear.toFixed(2)}% = ${realRate} + ${breakeven}`;
  $("#fundamentalSummary").textContent = state.decomposition.regimeRead || state.decomposition.frameworkNote || `过去一个月 10Y 变动 ${bp(monthRow?.total || 0)},实际利率贡献约 ${bp(monthRow?.real || 0)},BEI 贡献约 ${bp(monthRow?.inflation || 0)}。`;
  $("#policyEquation").textContent = `${tenYear.toFixed(2)}% = ${dff} + ${policyGap}`;
  $("#policySummary").textContent = state.decomposition.policyRead || `短端由政策利率锚定,10Y-2Y 利差约 ${Math.round((tenYear - twoYear) * 100)}bp,用于判断曲线方向。`;
  $("#decompCards").innerHTML = state.decomposition.components.map((item) => `
    <div class="component-card">
      <span class="index">${item.index}</span>
      <h3>${item.name}</h3>
      <strong>${item.value}</strong>
      <p>${item.note}</p>
      <span class="tag">${item.driver}</span>
    </div>
  `).join("");
  drawAttributionChart();
  $("#attributionTable").innerHTML = `
    <thead><tr><th>${t("table.window")}</th><th>${t("table.total10y")}</th><th>${t("table.realRate")}</th><th>${t("table.inflationExpectation")}</th><th>${t("table.termPremium")}</th><th>${t("table.riskPremium")}</th><th>${t("table.mainDriver")}</th></tr></thead>
    <tbody>
      ${state.decomposition.attribution.map((row) => `
        <tr>
          <td>${row.window}</td>
          <td>${bp(row.total)}</td>
          <td>${bp(row.real)}</td>
          <td>${bp(row.inflation)}</td>
          <td>${row.term === null ? "--" : bp(row.term)}</td>
          <td>${row.risk === null ? "--" : bp(row.risk)}</td>
          <td>${row.driver}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  $("#expectationSources").innerHTML = state.decomposition.sources.map((source, i) => `
    <div class="source-card">
      <span>0${i + 1}</span>
      <strong>${source.name}</strong>
      <p><b>${source.value}</b></p>
      <p>${source.note}</p>
    </div>
  `).join("");
}

function sourceValue(fragment) {
  const source = state.decomposition.sources.find((item) => item.name.includes(fragment));
  return source?.value;
}

function policyValue(fragment) {
  const source = state.policy.rates.find((item) => item[0].includes(fragment));
  return source?.[1];
}

function drawAttributionChart() {
  const row = state.decomposition.attribution.find((item) => item.window === "1 月");
  const bars = [
    ["实际利率", row.real, "var(--bear)"],
    ["通胀预期", row.inflation, "var(--accent)"],
    ["期限溢价", row.term || 0, "var(--neutral)"],
    ["通胀风险", row.risk || 0, "var(--accent-2)"]
  ];
  const W = 520;
  const H = 220;
  const max = Math.max(...bars.map((bar) => Math.abs(bar[1])), 1);
  const x0 = 140;
  const scale = (W - x0 - 40) / max;
  $("#attributionChart").innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="10Y move attribution">
      ${bars.map((bar, i) => {
        const y = 28 + i * 44;
        const width = Math.abs(bar[1]) * scale;
        return `
          <text x="12" y="${y + 18}" fill="var(--muted)" font-size="13">${bar[0]}</text>
          <rect x="${x0}" y="${y}" width="${width}" height="24" rx="6" fill="${bar[2]}"></rect>
          <text x="${x0 + width + 8}" y="${y + 17}" fill="var(--ink)" font-size="12" font-family="var(--mono)">${bp(bar[1])}</text>
        `;
      }).join("")}
    </svg>
  `;
}

function renderScorecard() {
  const score = aggregates();
  const [durationText, durationCode] = stanceLabel(score.duration);
  const [curveText, curveCode] = curveLabel(score.curve);
  $("#scorecardDuration").textContent = durationText;
  $("#scorecardDurationValue").textContent = `${t("score.composite")} ${score.duration.toFixed(2)} · ${durationCode}`;
  $("#scorecardCurve").textContent = curveText;
  $("#scorecardCurveValue").textContent = `${t("score.curve")} ${score.curve.toFixed(2)} · ${curveCode}`;

  $("#scorecardGroups").innerHTML = state.groups.map((group, groupIndex) => {
    const avg = group.factors.reduce((sum, factor) => sum + factor.score, 0) / group.factors.length;
    return `
      <article class="score-group">
        <div class="score-group-header">
          <div>
            <h3>${currentLanguage === "en" ? group.en : group.name}</h3>
            <small>${currentLanguage === "en" ? group.name : group.en}</small>
          </div>
          <label class="weight-field">${t("score.weight")}
            <input type="number" min="0" max="100" value="${group.weight}" data-weight="${groupIndex}">
          </label>
          <span class="group-average ${scoreClass(avg)}">${t("score.average")} ${avg.toFixed(2)}</span>
        </div>
        ${group.factors.map((factor, factorIndex) => `
          <div class="factor-row">
            <div class="factor-name">
              <strong>${factor.n}</strong>
              <span>${factor.tag}</span>
            </div>
            <div class="factor-value">
              <strong class="${scoreClass(factor.score)}">${factor.v}</strong>
              <span>${t("score.current")} ${factor.score}</span>
            </div>
            <div class="factor-note">${factor.note}${renderFactorSourceMode(factor)}</div>
            <div class="score-buttons" aria-label="${factor.n} score controls">
              ${[-2, -1, 0, 1, 2].map((scoreValue) => `
                <button type="button" class="${scoreValue === factor.score ? "active" : ""}" data-score="${groupIndex}:${factorIndex}:${scoreValue}">${scoreValue}</button>
              `).join("")}
            </div>
          </div>
        `).join("")}
      </article>
    `;
  }).join("");
  renderScorecardSourceLegend();
  renderBhadialPanels();
  bindScorecardEvents();
  renderHero();
}

function renderFactorSourceMode(factor) {
  if (!factor || !factor.sourceMode) return "";
  const mode = String(factor.sourceMode);
  return `<span class="factor-source-mode ${escapeHtml(mode)}">${escapeHtml(sourceModeLabel(mode))}</span>`;
}

function sourceModeLabel(mode) {
  return {
    "real-public": "public",
    "derived-public": "derived",
    "proxy-public": "proxy",
    modeled: "modeled",
    "official-news": "official news",
    "manual-placeholder": "manual",
  }[mode] || mode;
}

function renderScorecardSourceLegend() {
  const node = $("#scorecardSourceLegend");
  if (!node) return;
  const items = sourceModeLegendItems();
  if (!items.length) {
    node.innerHTML = "";
    node.hidden = true;
    return;
  }
  node.hidden = false;
  node.innerHTML = `
    <strong>数据边界</strong>
    ${items.map((item) => `
      <span class="factor-source-mode ${escapeHtml(item.mode)}">
        ${escapeHtml(sourceModeLabel(item.mode))}<em>${item.count}</em>
      </span>
    `).join("")}
    <small>public/derived 为真实公开源或公开派生; proxy/model/manual 不伪装为实时市场报价</small>
  `;
}

function sourceModeLegendItems() {
  const order = ["real-public", "derived-public", "official-news", "proxy-public", "modeled", "manual-placeholder"];
  const counts = new Map();
  state.groups.forEach((group) => {
    group.factors.forEach((factor) => {
      if (!factor.sourceMode) return;
      counts.set(factor.sourceMode, (counts.get(factor.sourceMode) || 0) + 1);
    });
  });
  return order
    .filter((mode) => counts.has(mode))
    .map((mode) => ({ mode, count: counts.get(mode) }));
}

function renderBhadialPanels() {
  renderMacroLiquidityScore();
  renderMacroLiquidityEquityLead();
  renderBhadialCoverage();
  renderPercentileDashboard();
  renderDriverDashboard();
}

function renderBhadialCoverage() {
  const panel = $("#bhadialCoveragePanel");
  if (!panel) return;
  const coverage = state.meta?.bhadialCompatibility?.coverage;
  if (!coverage || !Array.isArray(coverage.modules)) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  panel.hidden = false;
  const modules = coverage.modules;
  const missing = Array.isArray(coverage.missingFactorNames) ? coverage.missingFactorNames : [];
  const proxy = Array.isArray(coverage.proxyFactorNames) ? coverage.proxyFactorNames : [];
  const total = Number(coverage.totalFactors) || modules.reduce((sum, item) => sum + (Number(item.total) || 0), 0);
  const covered = Number(coverage.coveredFactors) || Math.max(0, total - (Number(coverage.missingFactors) || 0));
  const coveragePct = Number.isFinite(Number(coverage.coveragePct)) ? Number(coverage.coveragePct) : Math.round((covered / Math.max(1, total)) * 100);
  panel.innerHTML = `
    <div class="panel-title bhadial-coverage-title">
      <div>
        <h3>Bhadial 覆盖度 · Factor Coverage</h3>
        <span class="panel-kicker">${covered}/${total} factors · ${coveragePct}% covered</span>
      </div>
      <div class="bhadial-coverage-score">${coveragePct}<small>%</small></div>
    </div>
    <div class="bhadial-coverage-grid">
      ${coverageMetric("公开源", Number(coverage.publicFactors) || 0, "public")}
      ${coverageMetric("公开派生", Number(coverage.derivedFactors) || 0, "derived")}
      ${coverageMetric("公开代理", Number(coverage.proxyFactors) || 0, "proxy")}
      ${coverageMetric("待接入", Number(coverage.missingFactors) || 0, "missing")}
    </div>
    <div class="bhadial-module-grid">
      ${modules.map((module) => {
        const pct = Math.max(0, Math.min(100, Number(module.coveragePct) || 0));
        return `
          <div class="bhadial-module-row ${module.missing ? "has-gap" : "complete"}">
            <div>
              <strong>${escapeHtml(module.module)}</strong>
              <span>${escapeHtml(String(module.covered ?? 0))}/${escapeHtml(String(module.total ?? 0))} · scored ${escapeHtml(String(module.scored ?? "--"))}</span>
            </div>
            <div class="bhadial-coverage-bar"><i style="width:${pct}%"></i></div>
            <em>${pct}%</em>
          </div>
        `;
      }).join("")}
    </div>
    <div class="bhadial-gap-list">
      ${coverageGap("Proxy", proxy, "FRED OAS proxies until ETF history is stored")}
      ${coverageGap("Missing", missing, coverage.nextDataSource || "market history source pending")}
    </div>
  `;
}

function coverageMetric(label, value, tone) {
  return `
    <div class="bhadial-coverage-metric ${escapeHtml(tone)}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `;
}

function coverageGap(label, items, note) {
  if (!items.length) {
    return `
      <div class="bhadial-gap-row clear">
        <span>${escapeHtml(label)}</span>
        <strong>none</strong>
        <small>${escapeHtml(note || "")}</small>
      </div>
    `;
  }
  return `
    <div class="bhadial-gap-row">
      <span>${escapeHtml(label)}</span>
      <strong>${items.map((item) => escapeHtml(item)).join(" · ")}</strong>
      <small>${escapeHtml(note || "")}</small>
    </div>
  `;
}

function renderMacroLiquidityScore() {
  const panel = state.macroLiquidity || DEFAULT_DATA.macroLiquidity;
  const scoreNode = $("#macroLiquidityScore");
  if (!panel || !scoreNode) return;
  const score = Number(panel.score);
  const safeScore = Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 50;
  scoreNode.textContent = safeScore.toFixed(0);
  scoreNode.className = macroLiquidityClass(safeScore);
  const regime = $("#macroLiquidityRegime");
  if (regime) {
    regime.textContent = panel.regime || macroLiquidityLabel(safeScore);
    regime.className = macroLiquidityClass(safeScore);
  }
  const method = $("#macroLiquidityMethod");
  if (method) method.textContent = panel.method || "5Y rolling percentile composite";
  const read = $("#macroLiquidityRead");
  if (read) read.textContent = panel.summary || `${panel.regime || macroLiquidityLabel(safeScore)} · ${panel.method || "5Y rolling percentile composite"}`;
  const trendNode = $("#macroLiquidityTrend");
  if (trendNode) trendNode.innerHTML = renderMacroLiquidityTrend(panel.trend || {});
  const trendChartNode = $("#macroLiquidityTrendChart");
  const equityPanel = macroLiquidityEquityPanel();
  if (trendChartNode) {
    trendChartNode.innerHTML = renderMacroLiquidityTrendChart(panel.trend || {}, {
      equity: equityPanel,
      warning: spyWarningTrendPanel(),
    });
    bindMacroLiquidityTrendInteractions(trendChartNode, panel.trend || {}, {
      equity: equityPanel,
      warning: spyWarningTrendPanel(),
      tooltipSelector: "#macroLiquidityTrendTooltip",
    });
  }
  if (!$("#macroLiquidityTrendModal")?.hidden) renderMacroLiquidityTrendModalChart();
  const balanceNode = $("#macroLiquidityBalance");
  if (balanceNode) balanceNode.innerHTML = renderMacroLiquidityBalance(panel.balance || []);
  const qualityNode = $("#macroLiquidityQuality");
  if (qualityNode) qualityNode.innerHTML = renderMacroLiquidityQuality(panel);
  const implicationsNode = $("#macroLiquidityImplications");
  if (implicationsNode) implicationsNode.innerHTML = renderMacroLiquidityImplications(panel.implications || []);
  const gauge = $("#macroLiquidityGauge");
  if (gauge) {
    gauge.innerHTML = `
      <div class="macro-gauge-track">
        <i class="${macroLiquidityClass(safeScore)}" style="width:${safeScore.toFixed(1)}%"></i>
      </div>
      <div class="macro-gauge-scale"><span>紧</span><span>中性</span><span>松</span></div>
    `;
  }
}

function renderMacroLiquidityQuality(panel) {
  const counts = sourceStatusCounts();
  const observed = Number(panel.observedFactorCount);
  const scored = Number(panel.scoredFactorCount);
  const total = Number(panel.totalFactorCount);
  const coverageText = Number.isFinite(observed) && Number.isFinite(scored)
    ? `${observed.toFixed(0)}/${scored.toFixed(0)} scored`
    : "-- scored";
  const totalText = Number.isFinite(total) ? `${total.toFixed(0)} total` : "47 total";
  const sourceParts = [
    `${counts.ok} ok`,
    counts.warning ? `${counts.warning} warn` : "",
    counts.error ? `${counts.error} err` : "",
    counts.modeled ? `${counts.modeled} model` : "",
  ].filter(Boolean);
  const benchmark = panel.benchmark || {};
  const benchmarkScore = Number(benchmark.score);
  const benchmarkDelta = Number(benchmark.delta);
  const benchmarkHtml = Number.isFinite(benchmarkScore)
    ? `<span class="${benchmarkDeltaClass(benchmarkDelta)}"><b>Public</b><em>${benchmarkScore.toFixed(1)} · Δ ${formatSignedMetric(benchmarkDelta, 1)}</em></span>`
    : `<span class="neutral"><b>Public</b><em>${escapeHtml(benchmark.latest || "benchmark pending")}</em></span>`;
  return `
    <span class="neutral"><b>Coverage</b><em>${coverageText} · ${totalText}</em></span>
    <span class="${counts.error ? "restrictive" : counts.warning ? "neutral" : "supportive"}"><b>Sources</b><em>${sourceParts.join(" · ") || "--"}</em></span>
    ${benchmarkHtml}
  `;
}

function benchmarkDeltaClass(delta) {
  const numeric = Number(delta);
  if (!Number.isFinite(numeric) || Math.abs(numeric) <= 2) return "supportive";
  if (Math.abs(numeric) <= 5) return "neutral";
  return "restrictive";
}

function renderMacroLiquidityEquityLead() {
  const panel = state.macroLiquidityEquity || DEFAULT_DATA.macroLiquidityEquity;
  const root = $("#macroLiquidityEquityLead");
  if (!root || !panel) return;
  const method = $("#liquidityEquityMethod");
  if (method) method.textContent = panel.method || "monthly sample · forward return test";
  const coverage = $("#liquidityEquityCoverage");
  if (coverage) {
    const count = Number(panel.observationCount) || 0;
    coverage.textContent = panel.available ? `${count} monthly obs · asOf ${panel.asOf || "--"}` : "waiting for public history";
  }
  const read = $("#liquidityEquityRead");
  if (read) read.textContent = panel.conclusion || "暂无历史领先性检验。";
  const warningNode = $("#spyEarlyWarning");
  if (warningNode) warningNode.innerHTML = renderSpyEarlyWarning(state.spyEarlyWarning || DEFAULT_DATA.spyEarlyWarning);
  const shortTermNode = $("#equityShortTermRisk");
  if (shortTermNode) shortTermNode.innerHTML = renderEquityShortTermRisk(state.equityShortTermRisk || DEFAULT_DATA.equityShortTermRisk);
  if (!$("#equityRiskHistoryModal")?.hidden) renderEquityRiskHistoryModalChart();
  const globalLpplNode = $("#globalLpplRisk");
  if (globalLpplNode) globalLpplNode.innerHTML = renderGlobalLpplRisk(state.globalLpplRisk || DEFAULT_DATA.globalLpplRisk);
  if (!$("#globalLpplRiskHistoryModal")?.hidden) renderGlobalLpplRiskHistoryModalChart();
  const signalNode = $("#liquidityEquitySignal");
  if (signalNode) signalNode.innerHTML = renderLiquidityCurrentSignal(panel.currentSignal || {});
  const stateGridNode = $("#liquidityEquityStateGrid");
  if (stateGridNode) stateGridNode.innerHTML = renderLiquidityStateGrid(panel.stateGrid || []);
  const statsNode = $("#liquidityEquityStats");
  const stats = Array.isArray(panel.stats) ? panel.stats : [];
  if (statsNode) {
    statsNode.innerHTML = stats.length ? stats.map((item) => `
      <div class="liquidity-equity-stat ${escapeHtml(item.tone || "neutral")}">
        <span>${escapeHtml(item.label || "")}</span>
        <strong>${escapeHtml(item.value || "--")}</strong>
      </div>
    `).join("") : `<div class="empty-state compact">需要实时数据生成后显示相关性统计</div>`;
  }
  const chartNode = $("#liquidityEquityChart");
  if (chartNode) chartNode.innerHTML = renderLiquidityEquityChart(panel);
  const bucketsNode = $("#liquidityEquityBuckets");
  const buckets = Array.isArray(panel.buckets) ? panel.buckets : [];
  if (bucketsNode) {
    bucketsNode.innerHTML = buckets.length ? buckets.map((bucket) => {
      const avg = Number(bucket.avgForward3m);
      const hit = Number(bucket.hitRate);
      return `
        <div class="liquidity-equity-bucket">
          <span>${escapeHtml(bucket.label || "")}<small>score ${escapeHtml(bucket.scoreRange || "--")} · n=${Number(bucket.count) || 0}</small></span>
          <strong>${Number.isFinite(avg) ? `${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%` : "--"}</strong>
          <em>${Number.isFinite(hit) ? `${hit.toFixed(0)}% hit` : "--"}</em>
        </div>
      `;
    }).join("") : `<div class="empty-state compact">暂无分位桶统计</div>`;
  }
  const leadLagNode = $("#liquidityEquityLeadLag");
  if (leadLagNode) leadLagNode.innerHTML = renderLiquidityLeadLag(panel.leadLag || []);
  const changeNode = $("#liquidityEquityChangeBuckets");
  if (changeNode) changeNode.innerHTML = renderLiquidityChangeBuckets(panel.changeBuckets || []);
  const rollingNode = $("#liquidityEquityRolling");
  if (rollingNode) rollingNode.innerHTML = renderLiquidityRolling(panel.rollingCorrelation || {}, panel.drawdownRisk || {});
}

function renderSpyEarlyWarning(warning) {
  const item = warning && typeof warning === "object" ? warning : DEFAULT_DATA.spyEarlyWarning;
  if (!item.available) {
    return `<div class="empty-state compact">${escapeHtml(item.summary || "暂无SPY预警指标")}</div>`;
  }
  const score = Number(item.score);
  const baseScore = Number(item.baseScore);
  const riskClass = spyWarningClass(score);
  const allocation = item.allocation && typeof item.allocation === "object" ? item.allocation : {};
  const amplifiers = Array.isArray(item.amplifiers) ? item.amplifiers : [];
  const dampeners = Array.isArray(item.dampeners) ? item.dampeners : [];
  const amplifierText = amplifiers.length ? amplifiers.map((amplifier) => {
    const label = escapeHtml(amplifier && (amplifier.label || amplifier.key) ? amplifier.label || amplifier.key : "风险放大");
    const boost = Number(amplifier && amplifier.scoreBoost);
    return `${label}${Number.isFinite(boost) ? ` +${boost.toFixed(0)}` : ""}`;
  }).join(" · ") : "无";
  const dampenerText = dampeners.length ? dampeners.map((dampener) => {
    const label = escapeHtml(dampener && (dampener.label || dampener.key) ? dampener.label || dampener.key : "风险降噪");
    const offset = Number(dampener && dampener.scoreOffset);
    return `${label}${Number.isFinite(offset) ? ` ${offset.toFixed(0)}` : ""}`;
  }).join(" · ") : "无";
  const sleeves = Array.isArray(item.sleeves) ? item.sleeves : [];
  const drivers = Array.isArray(item.drivers) ? item.drivers : [];
  const backtest = item.backtest && typeof item.backtest === "object" ? item.backtest : {};
  return `
    <div class="spy-warning-head ${riskClass}">
      <div>
        <span>SPY Early Warning</span>
        <strong>${Number.isFinite(score) ? score.toFixed(1) : "--"}</strong>
      </div>
      <div>
        <b>${escapeHtml(item.regimeCn || item.regime || "--")}</b>
        <small>${escapeHtml(allocation.stance || "--")} · ${escapeHtml(allocation.equityExposure || "--")}</small>
      </div>
    </div>
    <p class="spy-warning-summary">${escapeHtml(item.summary || "")}</p>
    <div class="spy-warning-calibration">
      <span><b>基础分</b><strong>${Number.isFinite(baseScore) ? baseScore.toFixed(1) : "--"}</strong></span>
      <span><b>风险放大</b><strong>${amplifierText}</strong></span>
      <span><b>风险降噪</b><strong>${dampenerText}</strong></span>
    </div>
    <div class="spy-warning-sleeves">
      ${sleeves.map((sleeve) => {
        const sleeveScore = Number(sleeve.score);
        return `
          <div class="spy-warning-sleeve ${spyWarningClass(sleeveScore)}">
            <span>${escapeHtml(sleeve.label || sleeve.key || "")}</span>
            <strong>${Number.isFinite(sleeveScore) ? sleeveScore.toFixed(0) : "--"}</strong>
          </div>
        `;
      }).join("")}
    </div>
    <div class="spy-warning-drivers">
      <span>主要驱动</span>
      ${drivers.length ? drivers.slice(0, 4).map((driver) => `
        <b>${escapeHtml(driver.name || "")}<small>${escapeHtml(driver.sleeve || "")} · ${Number.isFinite(Number(driver.riskScore)) ? Number(driver.riskScore).toFixed(0) : "--"}</small></b>
      `).join("") : `<em>暂无高风险驱动</em>`}
    </div>
    <div class="spy-warning-foot">
      <span>${escapeHtml(allocation.hedgeAction || "")}</span>
      <em>${Number(backtest.sampleSize) || 0} obs · ${escapeHtml(backtest.target || "3M warning test")}</em>
    </div>
  `;
}

function renderEquityShortTermRisk(risk) {
  const item = risk && typeof risk === "object" ? risk : DEFAULT_DATA.equityShortTermRisk;
  if (!item.available) {
    return `<div class="empty-state compact">${escapeHtml(item.summary || "暂无短期股市风险指标")}</div>`;
  }
  const score = Number(item.score);
  const baseScore = Number(item.baseScore);
  const riskClass = spyWarningClass(score);
  const allocation = item.allocation && typeof item.allocation === "object" ? item.allocation : {};
  const components = Array.isArray(item.components) ? item.components : [];
  const drivers = Array.isArray(item.drivers) ? item.drivers : [];
  const guard = item.lookAheadGuard && typeof item.lookAheadGuard === "object" ? item.lookAheadGuard : {};
  const backtest = item.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const thresholdTests = Array.isArray(backtest.thresholdTests) ? backtest.thresholdTests : [];
  const threshold75 = thresholdTests.find((test) => Number(test.threshold) === 75) || {};
  const preferredThreshold = backtest.preferredThresholdTest && typeof backtest.preferredThresholdTest === "object" ? backtest.preferredThresholdTest : threshold75;
  const preferredHorizon = Number(preferredThreshold.horizon || backtest.preferredHorizon || 10);
  const tieredThresholdTests = Array.isArray(backtest.tieredThresholdTests) ? backtest.tieredThresholdTests : [];
  const cautionTier = tieredThresholdTests.find((test) => Number(test.threshold) === 60)
    || (Array.isArray(backtest.horizonTests) ? backtest.horizonTests.find((test) => Number(test.threshold) === 60 && Number(test.horizon) === preferredHorizon) : null)
    || {};
  const recommendedCautionThreshold = backtest.recommendedCautionThreshold && typeof backtest.recommendedCautionThreshold === "object"
    ? backtest.recommendedCautionThreshold
    : {};
  const highPrecisionThreshold = backtest.highPrecisionThresholdTest && typeof backtest.highPrecisionThresholdTest === "object"
    ? backtest.highPrecisionThresholdTest
    : {};
  const cautionDisplay = Number.isFinite(Number(recommendedCautionThreshold.threshold)) ? recommendedCautionThreshold : cautionTier;
  const strongTier = tieredThresholdTests.find((test) => Number(test.threshold) === 75) || preferredThreshold || {};
  const clusterTest = backtest.alertClusterTest && typeof backtest.alertClusterTest === "object" ? backtest.alertClusterTest : {};
  const regressionTests = Array.isArray(backtest.regressionTests) ? backtest.regressionTests : [];
  const componentDiagnostics = Array.isArray(backtest.componentDiagnostics) ? backtest.componentDiagnostics : [];
  const factorAuditRows = componentDiagnostics.length ? componentDiagnostics.slice(0, 5) : [];
  const firstTrimDiagnostic = componentDiagnostics.find((row) => row && row.decision === "trim");
  if (firstTrimDiagnostic && !factorAuditRows.some((row) => row && row.component === firstTrimDiagnostic.component)) {
    factorAuditRows.splice(Math.max(0, factorAuditRows.length - 1), 1, firstTrimDiagnostic);
  }
  const drawdownRegression = regressionTests.find((test) => test.target === `maxDrawdown${preferredHorizon}d`) || regressionTests.find((test) => test.target === "maxDrawdown10d") || {};
  const eventRegression = regressionTests.find((test) => test.target === `drawdownEvent${preferredHorizon}d`) || regressionTests.find((test) => test.target === "drawdownEvent10d") || {};
  const scoreBuckets = Array.isArray(backtest.scoreBuckets) ? backtest.scoreBuckets : [];
  const strongBucket = scoreBuckets.find((bucket) => bucket.label === "Strong Alert") || {};
  const worstWindows = Array.isArray(backtest.worstWindows) ? backtest.worstWindows : [];
  const dateRange = backtest.dateRange && typeof backtest.dateRange === "object" ? backtest.dateRange : {};
  const shock = item.nextSessionShock && typeof item.nextSessionShock === "object" ? item.nextSessionShock : {};
  const snapshot = item.marketSnapshot && typeof item.marketSnapshot === "object" ? item.marketSnapshot : {};
  const sourceQuality = item.sourceQuality && typeof item.sourceQuality === "object" ? item.sourceQuality : {};
  const weightCalibration = item.weightCalibration && typeof item.weightCalibration === "object" ? item.weightCalibration : {};
  const forwardCatalystRisk = item.forwardCatalystRisk && typeof item.forwardCatalystRisk === "object" ? item.forwardCatalystRisk : {};
  const factorEvidence = Array.isArray(item.factorEvidence) ? item.factorEvidence : [];
  const scoreUseLabel = (value) => ({
    scored: "计分",
    auditOnly: "审计",
    missing: "缺失"
  })[value] || "未分类";
  const shockText = shock.available ? `${escapeHtml(shock.date || "--")} ${formatSignedPercentMetric(shock.returnPct)}` : "next session --";
  const trendHistory = renderEquityRiskHistoryChart(item);
  const qualitySummary = `
    <div class="equity-risk-quality">
      <span><b>数据可信度</b><strong>${escapeHtml(sourceQuality.verdict || "--")}</strong><small>${escapeHtml(sourceQuality.detail || "等待证据评估")}</small></span>
      <span><b>计分权重</b><strong>${formatPercentMetric(sourceQuality.scoreEligibleWeightPct)}</strong><small>${Number(sourceQuality.scoredComponentCount) || 0} factors scored</small></span>
      <span><b>历史可回放</b><strong>${formatPercentMetric(sourceQuality.historicalReplayableWeightPct)}</strong><small>high-quality ${formatPercentMetric(sourceQuality.highQualityWeightPct)}</small></span>
      <span><b>权重校准</b><strong>${formatPercentMetric(weightCalibration.validatedWeightPct)}</strong><small>降权 ${formatPercentMetric(weightCalibration.downweightedWeightPct)} · 背景 ${formatPercentMetric(weightCalibration.contextWeightPct)}</small></span>
      <span><b>前瞻窗口</b><strong>${Number(forwardCatalystRisk.windowDays) || 5}D</strong><small>${Number(forwardCatalystRisk.eventCount) || 0} events · ${escapeHtml(forwardCatalystRisk.scoreUse ? scoreUseLabel(forwardCatalystRisk.scoreUse) : "--")}</small></span>
    </div>
    ${weightCalibration.available ? `
      <div class="equity-risk-weight-calibration">
        <span>权重校准</span>
        <b>${escapeHtml(weightCalibration.summary || "")}<small>${escapeHtml(weightCalibration.basis || "")}</small></b>
      </div>
    ` : ""}
    ${factorEvidence.length ? `
      <div class="equity-risk-evidence">
        <span>因子证据</span>
        ${factorEvidence.slice(0, 5).map((row) => `
          <b>${escapeHtml(row.label || row.component || "")}<small>${escapeHtml(scoreUseLabel(row.scoreUse))} · ${escapeHtml(row.sourceQuality || "--")} · ${escapeHtml(row.source || "--")}</small></b>
        `).join("")}
      </div>
    ` : ""}
  `;
  const regressionSummary = backtest.available ? `
    <div class="equity-risk-regression">
      <span>回归检验</span>
      <b>${preferredHorizon}D回撤<small>score+10: ${formatSignedPercentMetric(drawdownRegression.slopePer10Score)} · R² ${formatNumberMetric(drawdownRegression.rSquared, 2)}</small></b>
      <b>回撤概率<small>score+10: ${formatSignedPercentMetric(eventRegression.slopePer10Score)} · R² ${formatNumberMetric(eventRegression.rSquared, 2)}</small></b>
    </div>
  ` : "";
  const factorAudit = factorAuditRows.length ? `
    <div class="equity-risk-factor-audit">
      <span>全局因子审计</span>
      ${factorAuditRows.map((row) => `
        <b class="${escapeHtml(row.decision || "context")}">
          ${escapeHtml(row.label || row.component || "")}
          <small>${escapeHtml(row.decisionCn || "--")} · score≥${Number(row.threshold) || 75} ${formatPercentMetric(row.precision)} · recall ${formatPercentMetric(row.recall)} · false ${Number(row.falsePositives) || 0}</small>
        </b>
      `).join("")}
    </div>
  ` : "";
  const historicalAnalysis = backtest.available ? `
    <div class="equity-risk-backtest">
      <div class="equity-risk-backtest-head">
        <span>历史回放</span>
        <b>${Number(backtest.sampleSize) || 0} obs</b>
        <small>${escapeHtml(dateRange.start || "--")} → ${escapeHtml(dateRange.end || "--")}</small>
      </div>
      <div class="equity-risk-backtest-grid">
        <span><b>score≥75 ${preferredHorizon}D精确率</b><strong>${formatPercentMetric(preferredThreshold.precision)}</strong><small>${Number(preferredThreshold.alertDays) || 0} alerts · recall ${formatPercentMetric(preferredThreshold.recall)} · lead ${formatNumberMetric(preferredThreshold.avgDrawdownLeadDaysWhenHit, 1)}D</small></span>
        <span><b>告警簇命中率</b><strong>${formatPercentMetric(clusterTest.precision)}</strong><small>${Number(clusterTest.clusterCount) || 0} clusters · hit ${Number(clusterTest.hitClusters) || 0} · lead ${formatNumberMetric(clusterTest.avgLeadDays, 1)}D</small></span>
        <span><b>强告警${preferredHorizon}D回撤</b><strong>${formatSignedPercentMetric(strongBucket[`avgMaxDrawdown${preferredHorizon}d`] ?? strongBucket.avgMaxDrawdown10d)}</strong><small>${Number(strongBucket.count) || 0} obs · hit ${formatPercentMetric(strongBucket[`drawdownHitRate${preferredHorizon}d`] ?? strongBucket.drawdownHitRate10d)}</small></span>
      </div>
      <div class="equity-risk-tiered">
        <span><b>强告警</b><strong>${formatPercentMetric(strongTier.precision)}</strong><small>高精度 · recall ${formatPercentMetric(strongTier.recall)} · false ${Number(strongTier.falsePositives) || 0}</small></span>
        <span><b>中等预警 · 警戒以上</b><strong>${formatPercentMetric(cautionDisplay.precision)}</strong><small>推荐观察 score≥${Number(cautionDisplay.threshold) || 60} · 覆盖 ${formatPercentMetric(cautionDisplay.recall)} · false ${Number(cautionDisplay.falsePositives) || 0}</small></span>
        <span><b>高精度执行阈值</b><strong>${formatPercentMetric(highPrecisionThreshold.precision)}</strong><small>score≥${Number(highPrecisionThreshold.threshold) || 75} · recall ${formatPercentMetric(highPrecisionThreshold.recall)} · false ${Number(highPrecisionThreshold.falsePositives) || 0}</small></span>
      </div>
      ${factorAudit}
      ${trendHistory}
      <div class="equity-risk-worst">
        <span>最差窗口</span>
        ${worstWindows.slice(0, 3).map((row) => `<b>${escapeHtml(row.date || "--")}<small>score ${Number.isFinite(Number(row.score)) ? Number(row.score).toFixed(1) : "--"} · DD ${formatSignedPercentMetric(row[`maxDrawdown${preferredHorizon}d`] ?? row.maxDrawdown10d)}</small></b>`).join("")}
      </div>
      ${regressionSummary}
    </div>
  ` : `
    <div class="equity-risk-backtest muted"><span>历史回放</span><b>${escapeHtml(backtest.summary || "样本不足")}</b></div>
    ${trendHistory}
  `;
  return `
    <div class="equity-risk-head ${riskClass}">
      <div>
        <span>Equity Short-Term Risk · 短期股市风险</span>
        <strong>${Number.isFinite(score) ? score.toFixed(1) : "--"}</strong>
      </div>
      <div>
        <b>${escapeHtml(item.regimeCn || item.regime || "--")} · ${escapeHtml(item.asOf || "--")}</b>
        <small>${escapeHtml(allocation.stance || "--")} · ${escapeHtml(allocation.equityExposure || "--")}</small>
      </div>
    </div>
    <p class="equity-risk-summary">${escapeHtml(item.summary || "")}</p>
    <div class="equity-risk-metrics">
      <span><b>基础分</b><strong>${Number.isFinite(baseScore) ? baseScore.toFixed(1) : "--"}</strong></span>
      <span><b>SPY 63D</b><strong>${formatSignedPercentMetric(snapshot.spy63dReturn)}</strong></span>
      <span><b>SMH 当日</b><strong>${formatSignedPercentMetric(snapshot.smhDayReturn)}</strong></span>
      <span><b>次日审计</b><strong>${shockText}</strong></span>
    </div>
    ${qualitySummary}
    ${historicalAnalysis}
    <div class="equity-risk-components">
      ${components.map((component) => {
        const componentScore = Number(component.score);
        const componentClass = component.available ? spyWarningClass(componentScore) : "neutral";
        return `
          <div class="equity-risk-component ${componentClass}">
            <span>${escapeHtml(component.label || component.key || "")}</span>
            <strong>${component.available && Number.isFinite(componentScore) ? componentScore.toFixed(0) : "--"}</strong>
            <small>${escapeHtml(component.detail || "")}</small>
            <em>${escapeHtml(scoreUseLabel(component.scoreUse))} · ${escapeHtml(component.sourceQuality || "--")}</em>
          </div>
        `;
      }).join("")}
    </div>
    <div class="equity-risk-drivers">
      <span>短期驱动</span>
      ${drivers.length ? drivers.slice(0, 5).map((driver) => `
        <b>${escapeHtml(driver.name || "")}<small>${escapeHtml(driver.component || "")} · ${Number.isFinite(Number(driver.riskScore)) ? Number(driver.riskScore).toFixed(0) : "--"}</small></b>
      `).join("") : `<em>暂无高风险驱动</em>`}
    </div>
    <div class="equity-risk-foot">
      <span>${escapeHtml(allocation.hedgeAction || "")}</span>
      <em>dataThrough ${escapeHtml(guard.dataThrough || item.asOf || "--")}</em>
    </div>
  `;
}

function prepareEquityRiskHistorySeries(item) {
  const trendPoints = Array.isArray(item?.trend?.points) ? item.trend.points : [];
  const dataThroughTime = Date.parse(item?.lookAheadGuard?.dataThrough || item?.asOf || "");
  const series = trendPoints
    .map((point, index, rows) => {
      const spyClose = Number(point.spyClose);
      const previousSpyClose = index > 0 ? Number(rows[index - 1]?.spyClose) : NaN;
      const spyDayReturn = Number(point.spyDayReturn);
      return {
        time: Date.parse(point.date),
        date: point.date,
        score: Number(point.score),
        spyClose,
        spyDayReturn: Number.isFinite(spyDayReturn)
          ? spyDayReturn
          : Number.isFinite(spyClose) && Number.isFinite(previousSpyClose) && previousSpyClose > 0
            ? ((spyClose / previousSpyClose - 1) * 100)
            : null,
        regime: point.regime || "",
        regimeCn: point.regimeCn || "",
      };
    })
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.score))
    .filter((point) => !Number.isFinite(dataThroughTime) || point.time <= dataThroughTime);
  const priceSeries = series.filter((point) => Number.isFinite(point.spyClose) && point.spyClose > 0);
  const baseClose = priceSeries[0]?.spyClose || null;
  priceSeries.forEach((point) => {
    point.spyIndexed = baseClose ? (point.spyClose / baseClose) * 100 : null;
  });
  return { series, priceSeries, baseClose };
}

function prepareEquityRiskAlertWindows(item) {
  const backtest = item?.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const dataThroughTime = Date.parse(item?.lookAheadGuard?.dataThrough || item?.asOf || "");
  return (Array.isArray(backtest.alertWindows) ? backtest.alertWindows : [])
    .map((row) => ({
      ...row,
      time: Date.parse(row?.date || ""),
      score: Number(row?.score),
      horizon: Number(row?.horizon || backtest.preferredHorizon || 15),
    }))
    .filter((row) => Number.isFinite(row.time) && Number.isFinite(row.score))
    .filter((row) => !Number.isFinite(dataThroughTime) || row.time <= dataThroughTime);
}

function equityRiskHistoryScale(series, priceSeries, options = {}) {
  const W = options.large ? 1180 : 840;
  const H = options.large ? 420 : 180;
  const pad = options.large ? { l: 48, r: 72, t: 34, b: 40 } : { l: 34, r: 48, t: 24, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const spxValues = priceSeries.map((point) => point.spyIndexed).filter(Number.isFinite);
  const spxMin = spxValues.length ? Math.min(...spxValues) : 100;
  const spxMax = spxValues.length ? Math.max(...spxValues) : 100;
  const spxPad = Math.max(4, (spxMax - spxMin) * 0.12);
  const spxLow = Math.max(0, spxMin - spxPad);
  const spxHigh = spxMax + spxPad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yRisk = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const ySpy = (value) => pad.t + ((spxHigh - value) / Math.max(1, spxHigh - spxLow)) * (H - pad.t - pad.b);
  return { W, H, pad, minTime, maxTime, spxLow, spxHigh, x, yRisk, ySpy };
}

function renderEquityRiskHistoryChart(item, options = {}) {
  const { series, priceSeries } = prepareEquityRiskHistorySeries(item);
  if (series.length < 2) return `<div class="empty-state compact">历史曲线样本不足</div>`;
  const scale = equityRiskHistoryScale(series, priceSeries, options);
  const { W, H, pad, spxLow, spxHigh, x, yRisk, ySpy } = scale;
  const riskPath = macroLiquidityPath(series, x, yRisk, "score");
  const spyPath = priceSeries.length >= 2 ? macroLiquidityPath(priceSeries, x, ySpy, "spyIndexed") : "";
  const latestRisk = series[series.length - 1];
  const latestSpy = priceSeries[priceSeries.length - 1];
  const ticks = buildDateTicks(series, options.large ? 8 : 5);
  const alertMarkers = options.large || options.showAlerts ? prepareEquityRiskAlertWindows(item) : [];
  const markerLayer = alertMarkers.length ? `
        <g class="equity-risk-alert-markers" aria-label="score>=75 alert markers">
          ${alertMarkers.map((alert) => {
            const drawdown = alert[`maxDrawdown${alert.horizon}d`] ?? alert.maxDrawdown15d ?? alert.maxDrawdown10d;
            const lead = alert[`drawdownLeadDays${alert.horizon}d`] ?? alert.leadDays;
            const title = `${alert.date || "--"} · score ${alert.score.toFixed(1)} · DD ${formatSignedPercentMetric(drawdown)} · lead ${Number.isFinite(Number(lead)) ? `${Number(lead).toFixed(0)}D` : "--"}`;
            return `
              <circle class="equity-risk-alert-marker ${alert.hit === true ? "hit" : "miss"}" data-alert-date="${escapeHtml(alert.date || "")}" cx="${x(alert.time).toFixed(1)}" cy="${yRisk(alert.score).toFixed(1)}" r="${alert.hit === true ? "4.5" : "3.8"}">
                <title>${escapeHtml(title)}</title>
              </circle>
            `;
          }).join("")}
        </g>
  ` : "";
  const interactiveLayer = options.interactive ? `
        <line class="equity-risk-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke-opacity="0"></line>
        <circle class="equity-risk-hover-dot risk" cx="${x(latestRisk.time).toFixed(1)}" cy="${yRisk(latestRisk.score).toFixed(1)}" r="5" opacity="0"></circle>
        <circle class="equity-risk-hover-dot spy" cx="${latestSpy ? x(latestSpy.time).toFixed(1) : pad.l}" cy="${latestSpy ? ySpy(latestSpy.spyIndexed).toFixed(1) : pad.t}" r="4.5" opacity="0"></circle>
        <rect x="${pad.l}" y="${pad.t}" width="${W - pad.l - pad.r}" height="${H - pad.t - pad.b}" fill="transparent"></rect>
  ` : "";
  return `
    <div class="equity-risk-history-chart ${options.large ? "large" : ""}">
      <div class="equity-risk-history-head">
        <span>历史曲线</span>
        <div class="equity-risk-history-actions">
          <b>Risk score vs SPY indexed</b>
          ${options.large ? "" : `<button id="expandEquityRiskHistory" class="icon-btn chart-expand-btn" type="button" title="放大查看短期股市风险历史曲线" aria-label="放大查看短期股市风险历史曲线">⛶</button>`}
        </div>
      </div>
      <svg data-equity-risk-history-chart viewBox="0 0 ${W} ${H}" role="img" aria-label="equityShortTermRisk historical curve versus SPY indexed price">
        <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
        ${[40, 60, 75].map((tick) => `
          <line x1="${pad.l}" x2="${W - pad.r}" y1="${yRisk(tick).toFixed(1)}" y2="${yRisk(tick).toFixed(1)}" class="${tick === 75 ? "equity-risk-threshold-line strong" : "equity-risk-threshold-line"}"></line>
          <text x="8" y="${yRisk(tick).toFixed(1)}" dy="4">${tick}</text>
        `).join("")}
        ${ticks.map((point) => `
          <text x="${x(point.time).toFixed(1)}" y="${H - 8}" text-anchor="middle">${formatMonthLabel(point.time)}</text>
        `).join("")}
        ${spyPath ? `<path d="${spyPath}" class="equity-risk-spy-line"></path>` : ""}
        <path d="${riskPath}" class="equity-risk-score-line"></path>
        ${markerLayer}
        <circle class="equity-risk-score-dot" cx="${x(latestRisk.time).toFixed(1)}" cy="${yRisk(latestRisk.score).toFixed(1)}" r="4.2"></circle>
        ${latestSpy ? `<circle class="equity-risk-spy-dot" cx="${x(latestSpy.time).toFixed(1)}" cy="${ySpy(latestSpy.spyIndexed).toFixed(1)}" r="3.8"></circle>` : ""}
        <text x="${W - pad.r}" y="15" text-anchor="end">equityShortTermRisk ${latestRisk.score.toFixed(1)}</text>
        ${latestSpy ? `<text x="${W - pad.r}" y="30" text-anchor="end" class="equity-risk-spy-label">SPY indexed ${latestSpy.spyIndexed.toFixed(0)}</text>` : ""}
        <text x="${W - 8}" y="${ySpy(spxHigh).toFixed(1) + 4}" text-anchor="end" class="equity-risk-spy-axis">${spxHigh.toFixed(0)}</text>
        <text x="${W - 8}" y="${ySpy(spxLow).toFixed(1) + 4}" text-anchor="end" class="equity-risk-spy-axis">${spxLow.toFixed(0)}</text>
        ${interactiveLayer}
      </svg>
    </div>
  `;
}

function renderEquityRiskHistoryModalStats(item) {
  const { series, priceSeries } = prepareEquityRiskHistorySeries(item);
  if (series.length < 2) return `<div class="empty-state compact">历史样本不足</div>`;
  const latest = series[series.length - 1];
  const minScore = Math.min(...series.map((point) => point.score));
  const maxScore = Math.max(...series.map((point) => point.score));
  const alertCount = series.filter((point) => point.score >= 75).length;
  const latestSpy = priceSeries[priceSeries.length - 1];
  return [
    ["样本", `${series.length} obs`],
    ["区间", `${series[0].date} / ${latest.date}`],
    ["最新风险", latest.score.toFixed(1)],
    ["强告警日", alertCount],
    ["分数区间", `${minScore.toFixed(1)} / ${maxScore.toFixed(1)}`],
    ["SPY close", latestSpy ? latestSpy.spyClose.toFixed(2) : "--"],
  ].map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `).join("");
}

function renderEquityRiskHistoryModalAlerts(item) {
  const backtest = item?.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const alertWindows = prepareEquityRiskAlertWindows(item);
  if (!alertWindows.length) return `<div class="empty-state compact">暂无score≥75历史告警明细</div>`;
  const preferredHorizon = Number(backtest.preferredHorizon || alertWindows[0]?.horizon || 15);
  const hitCount = alertWindows.filter((row) => row.hit === true).length;
  const rows = alertWindows.slice(0, 10);
  return `
    <div class="equity-risk-modal-alert-head">
      <span>score≥75历史告警</span>
      <b>${alertWindows.length} days · hit ${formatPercentMetric(100 * hitCount / alertWindows.length)}</b>
      <small>${preferredHorizon}D max drawdown audit, sorted by strongest score</small>
    </div>
    <div class="equity-risk-modal-alert-grid">
      ${rows.map((row) => {
        const horizon = Number(row.horizon || preferredHorizon);
        const drawdown = row[`maxDrawdown${horizon}d`] ?? row.maxDrawdown15d ?? row.maxDrawdown10d;
        const forward = row[`forward${horizon}d`] ?? row.forward15d ?? row.forward10d;
        const lead = row[`drawdownLeadDays${horizon}d`] ?? row.leadDays;
        const leadText = row.hit === true
          ? (Number.isFinite(Number(lead)) ? `${Number(lead).toFixed(0)}D` : "--")
          : "未命中";
        return `
          <div class="equity-risk-alert-row ${row.hit === true ? "hit" : "miss"}">
            <b>${escapeHtml(row.date || "--")}<small>score ${Number.isFinite(row.score) ? row.score.toFixed(1) : "--"} · ${escapeHtml(row.regimeCn || row.regime || "--")}</small></b>
            <span><em>${horizon}D DD</em><strong>${formatSignedPercentMetric(drawdown)}</strong></span>
            <span><em>Lead</em><strong>${escapeHtml(leadText)}</strong></span>
            <span><em>${horizon}D Ret</em><strong>${formatSignedPercentMetric(forward)}</strong></span>
            <span><em>SPY</em><strong>${formatNumberMetric(row.spyClose, 2)}</strong></span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function openEquityRiskHistoryModal() {
  const modal = $("#equityRiskHistoryModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  renderEquityRiskHistoryModalChart();
  $("#closeEquityRiskHistoryModal")?.focus();
}

function closeEquityRiskHistoryModal() {
  const modal = $("#equityRiskHistoryModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderEquityRiskHistoryModalChart() {
  const item = state.equityShortTermRisk || DEFAULT_DATA.equityShortTermRisk;
  const chartNode = $("#equityRiskHistoryModalChart");
  const statsNode = $("#equityRiskHistoryModalStats");
  const alertsNode = $("#equityRiskHistoryModalAlerts");
  if (statsNode) statsNode.innerHTML = renderEquityRiskHistoryModalStats(item);
  if (alertsNode) alertsNode.innerHTML = renderEquityRiskHistoryModalAlerts(item);
  if (!chartNode) return;
  chartNode.innerHTML = renderEquityRiskHistoryChart(item, { large: true, interactive: true, showAlerts: true });
  bindEquityRiskHistoryInteractions(chartNode, item, { large: true, tooltipSelector: "#equityRiskHistoryModalTooltip" });
}

function bindEquityRiskHistoryInteractions(chartNode, item, options = {}) {
  const svg = chartNode?.querySelector("[data-equity-risk-history-chart]");
  const tooltip = $(options.tooltipSelector || "#equityRiskHistoryModalTooltip");
  if (!svg || !tooltip) return;
  const { series, priceSeries } = prepareEquityRiskHistorySeries(item);
  if (series.length < 2) return;
  const scale = equityRiskHistoryScale(series, priceSeries, options);
  const guide = svg.querySelector(".equity-risk-hover-guide");
  const riskDot = svg.querySelector(".equity-risk-hover-dot.risk");
  const spyDot = svg.querySelector(".equity-risk-hover-dot.spy");
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * scale.W;
    const point = nearestEquityRiskHistoryPoint(series, svgX, scale);
    if (!point) return;
    const pointX = scale.x(point.time);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.42");
    riskDot?.setAttribute("cx", pointX.toFixed(1));
    riskDot?.setAttribute("cy", scale.yRisk(point.score).toFixed(1));
    riskDot?.setAttribute("opacity", "1");
    if (Number.isFinite(point.spyIndexed)) {
      spyDot?.setAttribute("cx", pointX.toFixed(1));
      spyDot?.setAttribute("cy", scale.ySpy(point.spyIndexed).toFixed(1));
      spyDot?.setAttribute("opacity", "1");
    } else {
      spyDot?.setAttribute("opacity", "0");
    }
    renderEquityRiskHistoryTooltip(tooltip, chartNode, event, point);
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    riskDot?.setAttribute("opacity", "0");
    spyDot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function nearestEquityRiskHistoryPoint(points, svgX, scale) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  points.forEach((point) => {
    const distance = Math.abs(scale.x(point.time) - svgX);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  });
  return best;
}

function renderEquityRiskHistoryTooltip(tooltip, chartNode, event, point) {
  const spyCloseText = Number.isFinite(point.spyClose) ? `SPY close ${point.spyClose.toFixed(2)}` : "SPY close --";
  const spyIndexedText = Number.isFinite(point.spyIndexed) ? `SPY indexed ${point.spyIndexed.toFixed(1)}` : "SPY indexed --";
  const spyReturnText = Number.isFinite(point.spyDayReturn) ? `SPY day ${formatSignedPercentMetric(point.spyDayReturn)}` : "SPY day --";
  tooltip.innerHTML = `
    <b>${escapeHtml(point.date)} · score ${point.score.toFixed(1)}</b>
    <span>${escapeHtml(point.regimeCn || point.regime || "--")} · ${escapeHtml(spyCloseText)}</span>
    <small>${escapeHtml(spyIndexedText)} · ${escapeHtml(spyReturnText)}</small>
  `;
  const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
  tooltip.hidden = false;
  const left = Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8));
  const top = Math.min(Math.max(8, event.clientY - parentRect.top - 58), Math.max(8, parentRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function renderGlobalLpplRisk(payload) {
  const item = payload && typeof payload === "object" ? payload : DEFAULT_DATA.globalLpplRisk;
  if (!item.available) {
    const indices = Array.isArray(item.indices) ? item.indices : [];
    return `
      <div class="global-lppl-empty">
        <div>
          <span>Global LPPL Risk · 全球指数泡沫临界风险</span>
          <strong>--</strong>
        </div>
        <p>${escapeHtml(item.summary || "暂无全球LPPL风险评估")}</p>
        ${indices.length ? renderGlobalLpplIndexGrid(indices) : ""}
      </div>
    `;
  }
  const score = Number(item.score);
  const riskClass = spyWarningClass(score);
  const indices = Array.isArray(item.indices) ? item.indices : [];
  const backtest = item.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const indexValidation = item.indexValidation && typeof item.indexValidation === "object" ? item.indexValidation : {};
  const horizonTests = Array.isArray(backtest.horizonTests) ? backtest.horizonTests : [];
  const preferred = horizonTests.find((row) => Number(row.horizon) === 15) || horizonTests[0] || {};
  const cluster = backtest.alertClusterTest && typeof backtest.alertClusterTest === "object" ? backtest.alertClusterTest : {};
  return `
    <div class="global-lppl-head ${riskClass}">
      <div>
        <span>Global LPPL Risk · 全球指数泡沫临界风险</span>
        <strong>${Number.isFinite(score) ? score.toFixed(1) : "--"}</strong>
      </div>
      <div>
        <b>${escapeHtml(item.regimeCn || item.regime || "--")} · ${escapeHtml(item.asOf || "--")}</b>
        <small>${escapeHtml(item.scoreUse || "independent")} · ${escapeHtml(item.method || "LPPL")}</small>
      </div>
    </div>
    <p class="global-lppl-summary">${escapeHtml(item.summary || "")}</p>
    ${indexValidation.summary ? `<p class="global-lppl-validation-summary">${escapeHtml(indexValidation.summary)}</p>` : ""}
    <div class="global-lppl-backtest">
      <span><b>历史验证</b><strong>${Number(backtest.sampleSize) || 0} obs</strong><small>threshold score≥${Number(backtest.threshold) || 65}</small></span>
      <span><b>15D精确率</b><strong>${formatPercentMetric(preferred.precision)}</strong><small>${Number(preferred.alertDays) || 0} alerts · false ${Number(preferred.falsePositives) || 0}</small></span>
      <span><b>15D覆盖率</b><strong>${formatPercentMetric(preferred.recall)}</strong><small>${escapeHtml(backtest.drawdownEvent || "forward drawdown audit")}</small></span>
      <span><b>告警簇</b><strong>${formatPercentMetric(cluster.precision)}</strong><small>false clusters ${Number(cluster.falseClusters) || 0} · max ${Number(cluster.maxFalseClusterDays) || 0}</small></span>
    </div>
    ${renderGlobalLpplIndexGrid(indices)}
    ${renderGlobalLpplRiskHistoryChart(item)}
  `;
}

function renderGlobalLpplIndexGrid(indices) {
  return `
    <div class="global-lppl-index-grid">
      ${indices.map((row) => {
        const score = Number(row.score);
        const confidence = Number(row.confidence);
        const validation = row.validation && typeof row.validation === "object" ? row.validation : {};
        const weightMultiplier = Number(row.effectiveWeightMultiplier);
        const riskClass = row.available ? spyWarningClass(score) : "neutral";
        const validationText = row.available && validation.symbol
          ? `15D验证 ${formatPercentMetric(validation.precision15d)} · w×${Number.isFinite(weightMultiplier) ? weightMultiplier.toFixed(2) : "--"} · ${escapeHtml(validation.validationRoleCn || validation.validationRole || "")}`
          : "";
        return `
          <div class="global-lppl-index-card ${riskClass} ${row.available ? "" : "missing"}">
            <span>${escapeHtml(row.name || row.symbol || "")}<small>${escapeHtml(row.region || row.symbol || "")}</small></span>
            <strong>${row.available && Number.isFinite(score) ? score.toFixed(0) : "--"}</strong>
            <b>${escapeHtml(row.statusCn || row.status || "--")}</b>
            <small>${row.available ? `criticalDate ${escapeHtml(row.criticalDate || "--")} · ${Number(row.daysToCritical) || "--"}D · fitR2 ${formatNumberMetric(row.fitR2, 2)} · conf ${formatPercentMetric(confidence * 100)}` : escapeHtml(row.reason || "source unavailable")}</small>
            ${validationText ? `<small>${validationText}</small>` : ""}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function prepareGlobalLpplHistorySeries(item) {
  const raw = Array.isArray(item?.history?.points) ? item.history.points : [];
  const series = raw.map((point) => ({
    date: point.date,
    time: Date.parse(point.date || ""),
    score: Number(point.score),
    spyIndexed: Number(point.spyIndexed),
    qqqIndexed: Number(point.qqqIndexed),
    topSymbol: point.topSymbol || "",
    availableIndices: Number(point.availableIndices),
  })).filter((point) => Number.isFinite(point.time) && Number.isFinite(point.score));
  return {
    series,
    spySeries: series.filter((point) => Number.isFinite(point.spyIndexed)),
    qqqSeries: series.filter((point) => Number.isFinite(point.qqqIndexed)),
  };
}

function globalLpplHistoryScale(series, spySeries, qqqSeries, options = {}) {
  const W = options.large ? 1180 : 840;
  const H = options.large ? 420 : 190;
  const pad = options.large ? { l: 48, r: 72, t: 34, b: 40 } : { l: 34, r: 48, t: 24, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const priceValues = [...spySeries.map((point) => point.spyIndexed), ...qqqSeries.map((point) => point.qqqIndexed)].filter(Number.isFinite);
  const priceMin = priceValues.length ? Math.min(...priceValues) : 100;
  const priceMax = priceValues.length ? Math.max(...priceValues) : 100;
  const pricePad = Math.max(4, (priceMax - priceMin) * 0.12);
  const priceLow = Math.max(0, priceMin - pricePad);
  const priceHigh = priceMax + pricePad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yRisk = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const yPrice = (value) => pad.t + ((priceHigh - value) / Math.max(1, priceHigh - priceLow)) * (H - pad.t - pad.b);
  return { W, H, pad, minTime, maxTime, priceLow, priceHigh, x, yRisk, yPrice };
}

function renderGlobalLpplRiskHistoryChart(item, options = {}) {
  const { series, spySeries, qqqSeries } = prepareGlobalLpplHistorySeries(item);
  if (series.length < 2) return `<div class="empty-state compact">LPPL历史曲线样本不足</div>`;
  const scale = globalLpplHistoryScale(series, spySeries, qqqSeries, options);
  const { W, H, pad, priceLow, priceHigh, x, yRisk, yPrice } = scale;
  const riskPath = macroLiquidityPath(series, x, yRisk, "score");
  const spyPath = spySeries.length >= 2 ? macroLiquidityPath(spySeries, x, yPrice, "spyIndexed") : "";
  const qqqPath = qqqSeries.length >= 2 ? macroLiquidityPath(qqqSeries, x, yPrice, "qqqIndexed") : "";
  const latest = series[series.length - 1];
  const ticks = buildDateTicks(series, options.large ? 8 : 5);
  const interactiveLayer = options.interactive ? `
        <line class="global-lppl-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke-opacity="0"></line>
        <circle class="global-lppl-hover-dot risk" cx="${x(latest.time).toFixed(1)}" cy="${yRisk(latest.score).toFixed(1)}" r="5" opacity="0"></circle>
        <rect x="${pad.l}" y="${pad.t}" width="${W - pad.l - pad.r}" height="${H - pad.t - pad.b}" fill="transparent"></rect>
  ` : "";
  return `
    <div class="global-lppl-history-chart ${options.large ? "large" : ""}">
      <div class="equity-risk-history-head">
        <span>LPPL历史曲线</span>
        <div class="equity-risk-history-actions">
          <b>Global LPPL risk vs SPY/QQQ indexed</b>
          ${options.large ? "" : `<button id="expandGlobalLpplRiskHistory" class="icon-btn chart-expand-btn" type="button" title="放大查看全球LPPL风险历史曲线" aria-label="放大查看全球LPPL风险历史曲线">⛶</button>`}
        </div>
      </div>
      <svg data-global-lppl-history-chart viewBox="0 0 ${W} ${H}" role="img" aria-label="Global LPPL risk historical curve versus SPY and QQQ indexed price">
        <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
        ${[45, 65, 75].map((tick) => `
          <line x1="${pad.l}" x2="${W - pad.r}" y1="${yRisk(tick).toFixed(1)}" y2="${yRisk(tick).toFixed(1)}" class="${tick === 65 ? "global-lppl-threshold-line strong" : "global-lppl-threshold-line"}"></line>
          <text x="8" y="${yRisk(tick).toFixed(1)}" dy="4">${tick}</text>
        `).join("")}
        ${ticks.map((point) => `<text x="${x(point.time).toFixed(1)}" y="${H - 8}" text-anchor="middle">${formatMonthLabel(point.time)}</text>`).join("")}
        ${spyPath ? `<path d="${spyPath}" class="global-lppl-spy-line"></path>` : ""}
        ${qqqPath ? `<path d="${qqqPath}" class="global-lppl-qqq-line"></path>` : ""}
        <path d="${riskPath}" class="global-lppl-score-line"></path>
        <circle class="global-lppl-score-dot" cx="${x(latest.time).toFixed(1)}" cy="${yRisk(latest.score).toFixed(1)}" r="4.2"></circle>
        <text x="${W - pad.r}" y="15" text-anchor="end">Global LPPL Risk ${latest.score.toFixed(1)}</text>
        ${Number.isFinite(latest.spyIndexed) ? `<text x="${W - pad.r}" y="30" text-anchor="end" class="global-lppl-price-label">SPY indexed ${latest.spyIndexed.toFixed(0)}</text>` : ""}
        ${Number.isFinite(latest.qqqIndexed) ? `<text x="${W - pad.r}" y="45" text-anchor="end" class="global-lppl-qqq-label">QQQ indexed ${latest.qqqIndexed.toFixed(0)}</text>` : ""}
        <text x="${W - 8}" y="${yPrice(priceHigh).toFixed(1) + 4}" text-anchor="end" class="global-lppl-price-axis">${priceHigh.toFixed(0)}</text>
        <text x="${W - 8}" y="${yPrice(priceLow).toFixed(1) + 4}" text-anchor="end" class="global-lppl-price-axis">${priceLow.toFixed(0)}</text>
        ${interactiveLayer}
      </svg>
    </div>
  `;
}

function renderGlobalLpplRiskHistoryModalStats(item) {
  const { series } = prepareGlobalLpplHistorySeries(item);
  const backtest = item?.backtest && typeof item.backtest === "object" ? item.backtest : {};
  const horizonTests = Array.isArray(backtest.horizonTests) ? backtest.horizonTests : [];
  const preferred = horizonTests.find((row) => Number(row.horizon) === 15) || horizonTests[0] || {};
  const cluster = backtest.alertClusterTest && typeof backtest.alertClusterTest === "object" ? backtest.alertClusterTest : {};
  if (series.length < 2) return `<div class="empty-state compact">LPPL历史样本不足</div>`;
  const latest = series[series.length - 1];
  return [
    ["样本", `${series.length} pts`],
    ["区间", `${series[0].date} / ${latest.date}`],
    ["最新LPPL", latest.score.toFixed(1)],
    ["阈值", `score≥${Number(backtest.threshold) || 65}`],
    ["15D精确率", formatPercentMetric(preferred.precision)],
    ["误报", `${Number(preferred.falsePositives) || 0}`],
    ["簇命中率", formatPercentMetric(cluster.precision)],
    ["最大误报簇", `${Number(cluster.maxFalseClusterDays) || 0} pts`],
  ].map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `).join("");
}

function openGlobalLpplRiskHistoryModal() {
  const modal = $("#globalLpplRiskHistoryModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  renderGlobalLpplRiskHistoryModalChart();
  $("#closeGlobalLpplRiskHistoryModal")?.focus();
}

function closeGlobalLpplRiskHistoryModal() {
  const modal = $("#globalLpplRiskHistoryModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderGlobalLpplRiskHistoryModalChart() {
  const item = state.globalLpplRisk || DEFAULT_DATA.globalLpplRisk;
  const chartNode = $("#globalLpplRiskHistoryModalChart");
  const statsNode = $("#globalLpplRiskHistoryModalStats");
  if (statsNode) statsNode.innerHTML = renderGlobalLpplRiskHistoryModalStats(item);
  if (!chartNode) return;
  chartNode.innerHTML = renderGlobalLpplRiskHistoryChart(item, { large: true, interactive: true });
  bindGlobalLpplRiskHistoryInteractions(chartNode, item, { large: true, tooltipSelector: "#globalLpplRiskHistoryModalTooltip" });
}

function bindGlobalLpplRiskHistoryInteractions(chartNode, item, options = {}) {
  const svg = chartNode?.querySelector("[data-global-lppl-history-chart]");
  const tooltip = $(options.tooltipSelector || "#globalLpplRiskHistoryModalTooltip");
  if (!svg || !tooltip) return;
  const { series, spySeries, qqqSeries } = prepareGlobalLpplHistorySeries(item);
  if (series.length < 2) return;
  const scale = globalLpplHistoryScale(series, spySeries, qqqSeries, options);
  const guide = svg.querySelector(".global-lppl-hover-guide");
  const riskDot = svg.querySelector(".global-lppl-hover-dot.risk");
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * scale.W;
    const point = nearestEquityRiskHistoryPoint(series, svgX, scale);
    if (!point) return;
    const pointX = scale.x(point.time);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.42");
    riskDot?.setAttribute("cx", pointX.toFixed(1));
    riskDot?.setAttribute("cy", scale.yRisk(point.score).toFixed(1));
    riskDot?.setAttribute("opacity", "1");
    tooltip.innerHTML = `
      <b>${escapeHtml(point.date)} · LPPL ${point.score.toFixed(1)}</b>
      <span>SPY ${Number.isFinite(point.spyIndexed) ? point.spyIndexed.toFixed(1) : "--"} · QQQ ${Number.isFinite(point.qqqIndexed) ? point.qqqIndexed.toFixed(1) : "--"}</span>
      <small>top ${escapeHtml(point.topSymbol || "--")} · indices ${Number(point.availableIndices) || "--"}</small>
    `;
    const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8))}px`;
    tooltip.style.top = `${Math.min(Math.max(8, event.clientY - parentRect.top - 58), Math.max(8, parentRect.height - tooltip.offsetHeight - 8))}px`;
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    riskDot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function spyWarningClass(score) {
  const numeric = Number(score);
  if (!Number.isFinite(numeric)) return "neutral";
  if (numeric >= 60) return "restrictive";
  if (numeric >= 40) return "neutral";
  return "supportive";
}

function renderLiquidityCurrentSignal(signal) {
  const cards = Array.isArray(signal.cards) ? signal.cards : [];
  if (!signal.available || !cards.length) {
    return `<div class="empty-state compact">${escapeHtml(signal.verdict || "暂无当前信号")}</div>`;
  }
  return `
    <div class="liquidity-signal-read ${escapeHtml(signal.confidence || "low")}">
      <strong>${escapeHtml(signal.changeBucket || "--")}</strong>
      <span>${escapeHtml(signal.verdict || "")}</span>
    </div>
    <div class="liquidity-signal-cards">
      ${cards.map((card) => `
        <div class="liquidity-signal-card ${escapeHtml(card.tone || "neutral")}">
          <span>${escapeHtml(card.label || "")}</span>
          <strong>${escapeHtml(card.value || "--")}</strong>
          <small>${escapeHtml(card.detail || "")}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function renderLiquidityStateGrid(cells) {
  if (!Array.isArray(cells) || !cells.length) {
    return `<div class="empty-state compact">暂无状态分布统计</div>`;
  }
  const levelLabels = ["低评分", "中位评分", "高评分"];
  const changeLabels = ["评分下行", "变化不大", "评分上行"];
  const lookup = new Map(cells.map((cell) => [`${cell.levelBucket}::${cell.changeBucket}`, cell]));
  return `
    <div class="liquidity-state-head">
      <strong>历史状态分布</strong>
      <span>当前状态与相似样本3M表现</span>
    </div>
    <div class="liquidity-state-axis">
      ${changeLabels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}
    </div>
    <div class="liquidity-state-matrix">
      ${levelLabels.map((level) => `
        <div class="liquidity-state-row">
          <b>${escapeHtml(level)}</b>
          ${changeLabels.map((change) => {
            const cell = lookup.get(`${level}::${change}`) || {};
            const avg = Number(cell.avgForward3m);
            const dd = Number(cell.avgMaxDrawdown3m);
            const hit = Number(cell.hitRate);
            return `
              <div class="liquidity-state-cell ${escapeHtml(cell.tone || "neutral")} ${cell.isCurrent ? "current" : ""}">
                <span>${Number(cell.count) || 0} obs</span>
                <strong>${Number.isFinite(avg) ? `${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%` : "--"}</strong>
                <small>${Number.isFinite(hit) ? `${hit.toFixed(0)}% hit` : "hit --"} · DD ${Number.isFinite(dd) ? `${dd.toFixed(2)}%` : "--"}</small>
              </div>
            `;
          }).join("")}
        </div>
      `).join("")}
    </div>
  `;
}

function renderLiquidityEquityChart(panel) {
  const series = Array.isArray(panel.series) ? panel.series
    .map((point) => ({
      time: Date.parse(point.date),
      date: point.date,
      score: Number(point.liquidityScore),
      spx: Number(point.sp500Indexed),
    }))
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.score) && Number.isFinite(point.spx)) : [];
  if (series.length < 2) {
    return `<div class="empty-state">暂无足够历史点生成对比图</div>`;
  }
  const W = 840;
  const H = 230;
  const pad = { l: 34, r: 44, t: 16, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const spxMin = Math.min(...series.map((point) => point.spx));
  const spxMax = Math.max(...series.map((point) => point.spx));
  const spxPad = Math.max(6, (spxMax - spxMin) * 0.12);
  const spxLow = Math.max(0, spxMin - spxPad);
  const spxHigh = spxMax + spxPad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yScore = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const ySpx = (value) => pad.t + ((spxHigh - value) / Math.max(1, spxHigh - spxLow)) * (H - pad.t - pad.b);
  const path = (key, yFn) => series.map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${yFn(point[key]).toFixed(1)}`).join(" ");
  const dateTicks = buildDateTicks(series, 4);
  return `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Conditions score versus indexed S&P 500">
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      ${[25, 50, 75].map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${yScore(tick)}" y2="${yScore(tick)}" stroke="var(--line-soft)"></line>
        <text x="8" y="${yScore(tick) + 4}" fill="var(--muted)" font-size="10" font-family="var(--mono)">${tick}</text>
      `).join("")}
      ${dateTicks.map((point) => `
        <text x="${x(point.time).toFixed(1)}" y="${H - 9}" text-anchor="middle" fill="var(--faint)" font-size="10.5" font-family="var(--mono)">${formatMonthLabel(point.time)}</text>
      `).join("")}
      <path d="${path("spx", ySpx)}" class="liquidity-equity-line spx"></path>
      <path d="${path("score", yScore)}" class="liquidity-equity-line score"></path>
      <circle cx="${x(series[series.length - 1].time).toFixed(1)}" cy="${yScore(series[series.length - 1].score).toFixed(1)}" r="3.5" class="liquidity-equity-dot score"></circle>
      <circle cx="${x(series[series.length - 1].time).toFixed(1)}" cy="${ySpx(series[series.length - 1].spx).toFixed(1)}" r="3.5" class="liquidity-equity-dot spx"></circle>
      <text x="${W - pad.r}" y="15" text-anchor="end" fill="var(--accent)" font-size="11" font-family="var(--mono)">Macro score</text>
      <text x="${W - pad.r}" y="30" text-anchor="end" fill="var(--bear)" font-size="11" font-family="var(--mono)">S&P 500 indexed</text>
      <text x="${W - 8}" y="${ySpx(spxHigh).toFixed(1) + 4}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="var(--mono)">${spxHigh.toFixed(0)}</text>
      <text x="${W - 8}" y="${ySpx(spxLow).toFixed(1) + 4}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="var(--mono)">${spxLow.toFixed(0)}</text>
    </svg>
  `;
}

function renderLiquidityLeadLag(rows) {
  if (!Array.isArray(rows) || !rows.length) return `<div class="empty-state compact">暂无领先矩阵</div>`;
  return `
    <table class="liquidity-equity-mini-table">
      <thead><tr><th>Signal</th><th>1M</th><th>3M</th><th>6M</th></tr></thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.signal || "")}</td>
            ${["forward1m", "forward3m", "forward6m"].map((key) => `<td class="${correlationToneClass(row[key])}">${formatSignedMetric(row[key], 2)}</td>`).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderLiquidityChangeBuckets(buckets) {
  if (!Array.isArray(buckets) || !buckets.length) return `<div class="empty-state compact">暂无变化分组</div>`;
  return buckets.map((bucket) => {
    const avg = Number(bucket.avgForward3m);
    const dd = Number(bucket.avgMaxDrawdown3m);
    return `
      <div class="liquidity-change-row">
        <span>${escapeHtml(bucket.label || "")}<small>${escapeHtml(bucket.changeRange || "--")} · n=${Number(bucket.count) || 0}</small></span>
        <strong>${Number.isFinite(avg) ? `${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%` : "--"}</strong>
        <em>DD ${Number.isFinite(dd) ? `${dd.toFixed(2)}%` : "--"}</em>
      </div>
    `;
  }).join("");
}

function renderLiquidityRolling(rolling, drawdown) {
  const latest = Number(rolling.latest);
  const min = Number(rolling.range?.min);
  const max = Number(rolling.range?.max);
  const worst = Number(drawdown.maxDrawdown);
  const worstDate = drawdown.worstDate || "--";
  return `
    <div class="liquidity-rolling-grid">
      <div>
        <span>${Number(rolling.windowMonths) || 24}M rolling corr</span>
        <strong class="${correlationToneClass(latest)}">${formatSignedMetric(latest, 2)}</strong>
        <small>${Number.isFinite(min) && Number.isFinite(max) ? `range ${formatSignedMetric(min, 2)} / ${formatSignedMetric(max, 2)}` : "range --"}</small>
      </div>
      <div>
        <span>Worst 3M drawdown</span>
        <strong class="restrictive">${Number.isFinite(worst) ? `${worst.toFixed(2)}%` : "--"}</strong>
        <small>${escapeHtml(worstDate)}</small>
      </div>
    </div>
  `;
}

function formatSignedMetric(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(digits)}`;
}

function correlationToneClass(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || Math.abs(numeric) < 0.15) return "neutral";
  return numeric > 0 ? "supportive" : "restrictive";
}

function renderMacroLiquidityTrend(trend) {
  if (!trend.available) {
    return `<div class="empty-state compact">${escapeHtml(trend.summary || "综合评分历史分位样本不足")}</div>`;
  }
  const percentile = Number(trend.historicalPercentile);
  const score1m = Number(trend.score1mChange);
  const score3m = Number(trend.score3mChange);
  const percentile3m = Number(trend.percentile3mChange);
  return `
    <div class="macro-trend-card ${macroLiquidityTrendClass(trend.direction)}">
      <span>历史分位</span>
      <strong>${Number.isFinite(percentile) ? `p${percentile.toFixed(0)}` : "p--"}</strong>
      <small>${escapeHtml(trend.direction || "--")}</small>
    </div>
    <div class="macro-trend-card ${macroLiquidityTrendClass(score1m)}">
      <span>1M评分</span>
      <strong>${formatSignedMetric(score1m, 1)}</strong>
      <small>score change</small>
    </div>
    <div class="macro-trend-card ${macroLiquidityTrendClass(score3m)}">
      <span>3M评分</span>
      <strong>${formatSignedMetric(score3m, 1)}</strong>
      <small>${Number.isFinite(percentile3m) ? `p ${formatSignedMetric(percentile3m, 0)}` : "p --"}</small>
    </div>
  `;
}

function renderMacroLiquidityTrendChart(trend, options = {}) {
  const prepared = prepareMacroLiquidityComparisonSeries(trend, options.equity || macroLiquidityEquityPanel(), options.warning || spyWarningTrendPanel());
  const series = prepared.series;
  if (series.length < 2) return `<div class="empty-state compact">综合评分历史趋势样本不足</div>`;
  const scale = macroLiquidityComparisonScale(series, options);
  const { W, H, pad, x, yPercentile, ySpx } = scale;
  const liquidityPath = macroLiquidityPath(series, x, yPercentile, "percentile");
  const areaPath = `${liquidityPath} L${x(series[series.length - 1].time).toFixed(1)},${yPercentile(0).toFixed(1)} L${x(series[0].time).toFixed(1)},${yPercentile(0).toFixed(1)} Z`;
  const spxSeries = series.filter((point) => Number.isFinite(point.spxIndexed));
  const spxPath = spxSeries.length >= 2 ? macroLiquidityPath(spxSeries, x, ySpx, "spxIndexed") : "";
  const warningSeries = series.filter((point) => Number.isFinite(point.spyWarning));
  const warningPath = warningSeries.length >= 2 ? macroLiquidityPath(warningSeries, x, yPercentile, "spyWarning") : "";
  const latest = series[series.length - 1];
  const latestSpx = [...spxSeries].reverse().find((point) => point.time <= latest.time) || spxSeries[spxSeries.length - 1];
  const latestWarning = [...warningSeries].reverse().find((point) => point.time <= latest.time) || warningSeries[warningSeries.length - 1];
  const dateTicks = buildDateTicks(series, options.large ? 7 : 5);
  const spxLabel = spxSeries.length >= 2 ? `S&P 500 indexed ${latestSpx?.spxIndexed?.toFixed(0) || "--"}` : "S&P 500 indexed --";
  const warningLabel = warningSeries.length >= 2 ? `SPY Early Warning ${latestWarning?.spyWarning?.toFixed(0) || "--"}` : "SPY Early Warning --";
  return `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Conditions score historical percentile trend versus S&P 500 and SPY Early Warning" data-macro-liquidity-chart>
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      ${[20, 50, 80].map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${yPercentile(tick).toFixed(1)}" y2="${yPercentile(tick).toFixed(1)}"></line>
        <text x="8" y="${yPercentile(tick).toFixed(1)}" dy="4">p${tick}</text>
      `).join("")}
      ${dateTicks.map((point) => `
        <text x="${x(point.time).toFixed(1)}" y="${H - 8}" text-anchor="middle">${formatMonthLabel(point.time)}</text>
      `).join("")}
      <path d="${areaPath}" class="macro-liquidity-trend-area"></path>
      ${spxPath ? `<path d="${spxPath}" class="macro-liquidity-spx-line"></path>` : ""}
      ${warningPath ? `<path d="${warningPath}" class="macro-liquidity-spy-warning-line"></path>` : ""}
      <path d="${liquidityPath}" class="macro-liquidity-trend-line"></path>
      <line class="macro-liquidity-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}"></line>
      <circle class="macro-liquidity-hover-dot liquidity" cx="${pad.l}" cy="${pad.t}" r="${options.large ? "5.2" : "4.2"}"></circle>
      <circle class="macro-liquidity-hover-dot spx" cx="${pad.l}" cy="${pad.t}" r="${options.large ? "5.0" : "4.0"}"></circle>
      <circle class="macro-liquidity-hover-dot spy-warning" cx="${pad.l}" cy="${pad.t}" r="${options.large ? "5.0" : "4.0"}"></circle>
      <circle class="macro-liquidity-trend-dot" cx="${x(latest.time).toFixed(1)}" cy="${yPercentile(latest.percentile).toFixed(1)}" r="${options.large ? "5.0" : "4.2"}"></circle>
      ${latestSpx ? `<circle class="macro-liquidity-spx-dot" cx="${x(latestSpx.time).toFixed(1)}" cy="${ySpx(latestSpx.spxIndexed).toFixed(1)}" r="${options.large ? "4.8" : "3.8"}"></circle>` : ""}
      ${latestWarning ? `<circle class="macro-liquidity-spy-warning-dot" cx="${x(latestWarning.time).toFixed(1)}" cy="${yPercentile(latestWarning.spyWarning).toFixed(1)}" r="${options.large ? "4.8" : "3.8"}"></circle>` : ""}
      <text x="${W - pad.r}" y="16" text-anchor="end">综合评分历史分位 · ${series.length} obs</text>
      <text x="${W - pad.r}" y="31" text-anchor="end" class="macro-liquidity-spx-label">${spxLabel}</text>
      <text x="${W - pad.r}" y="46" text-anchor="end" class="macro-liquidity-spy-warning-label">${warningLabel}</text>
      <text x="${W - 8}" y="${ySpx(scale.spxHigh).toFixed(1) + 4}" text-anchor="end" class="macro-liquidity-spx-axis">${scale.spxHigh.toFixed(0)}</text>
      <text x="${W - 8}" y="${ySpx(scale.spxLow).toFixed(1) + 4}" text-anchor="end" class="macro-liquidity-spx-axis">${scale.spxLow.toFixed(0)}</text>
      <text x="${x(latest.time).toFixed(1) - 8}" y="${Math.max(16, yPercentile(latest.percentile) - 8).toFixed(1)}" text-anchor="end">p${latest.percentile.toFixed(0)}</text>
    </svg>
  `;
}

function macroLiquidityEquityPanel() {
  return state.macroLiquidityEquity || DEFAULT_DATA.macroLiquidityEquity || {};
}

function spyWarningTrendPanel() {
  return state.spyEarlyWarning || DEFAULT_DATA.spyEarlyWarning || {};
}

function prepareMacroLiquidityComparisonSeries(trend, equityPanel = {}, warningPanel = {}) {
  const equityRows = Array.isArray(equityPanel.series) ? equityPanel.series : [];
  const spxByMonth = new Map();
  equityRows.forEach((point) => {
    const time = Date.parse(point.date);
    const spxIndexed = Number(point.sp500Indexed);
    if (!Number.isFinite(time) || !Number.isFinite(spxIndexed)) return;
    spxByMonth.set(monthKeyFromTime(time), {
      spxIndexed,
      sp500: Number(point.sp500),
      trailing3m: Number(point.sp500Trailing3m),
    });
  });
  const warningRows = Array.isArray(warningPanel?.trend?.points) ? warningPanel.trend.points : [];
  const warningByMonth = new Map();
  warningRows.forEach((point) => {
    const time = Date.parse(point.date);
    const score = Number(point.score);
    if (!Number.isFinite(time) || !Number.isFinite(score)) return;
    warningByMonth.set(monthKeyFromTime(time), {
      score: Math.max(0, Math.min(100, score)),
      regime: point.regime || "",
      regimeCn: point.regimeCn || "",
    });
  });
  const points = Array.isArray(trend?.points) ? trend.points : [];
  const series = points
    .map((point) => {
      const time = Date.parse(point.date);
      const spx = Number.isFinite(time) ? spxByMonth.get(monthKeyFromTime(time)) : null;
      const warning = Number.isFinite(time) ? warningByMonth.get(monthKeyFromTime(time)) : null;
      return {
        time,
        date: point.date,
        percentile: Number(point.percentile),
        score: Number(point.score),
        spxIndexed: spx?.spxIndexed,
        sp500: spx?.sp500,
        sp500Trailing3m: spx?.trailing3m,
        spyWarning: warning?.score,
        spyWarningRegime: warning?.regime,
        spyWarningRegimeCn: warning?.regimeCn,
      };
    })
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.percentile));
  return {
    series,
    hasSpx: series.some((point) => Number.isFinite(point.spxIndexed)),
    hasSpyWarning: series.some((point) => Number.isFinite(point.spyWarning)),
  };
}

function monthKeyFromTime(time) {
  const date = new Date(time);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function macroLiquidityComparisonScale(series, options = {}) {
  const W = options.large ? 980 : 620;
  const H = options.large ? 380 : 190;
  const pad = options.large ? { l: 46, r: 58, t: 30, b: 42 } : { l: 34, r: 44, t: 24, b: 28 };
  const minTime = Math.min(...series.map((point) => point.time));
  const maxTime = Math.max(...series.map((point) => point.time));
  const spxValues = series.map((point) => point.spxIndexed).filter(Number.isFinite);
  const spxMin = spxValues.length ? Math.min(...spxValues) : 100;
  const spxMax = spxValues.length ? Math.max(...spxValues) : 100;
  const spxPad = Math.max(6, (spxMax - spxMin) * 0.12);
  const spxLow = Math.max(0, spxMin - spxPad);
  const spxHigh = spxMax + spxPad;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const yPercentile = (value) => pad.t + ((100 - Math.max(0, Math.min(100, value))) / 100) * (H - pad.t - pad.b);
  const ySpx = (value) => pad.t + ((spxHigh - value) / Math.max(1, spxHigh - spxLow)) * (H - pad.t - pad.b);
  return { W, H, pad, x, yPercentile, ySpx, spxLow, spxHigh };
}

function macroLiquidityPath(points, x, y, key) {
  return points
    .filter((point) => Number.isFinite(point[key]))
    .map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${y(point[key]).toFixed(1)}`)
    .join(" ");
}

function bindMacroLiquidityTrendInteractions(chartNode, trend, options = {}) {
  const svg = chartNode?.querySelector("[data-macro-liquidity-chart]");
  const tooltip = $(options.tooltipSelector || "#macroLiquidityTrendTooltip");
  if (!svg || !tooltip) return;
  const prepared = prepareMacroLiquidityComparisonSeries(trend, options.equity || macroLiquidityEquityPanel(), options.warning || spyWarningTrendPanel());
  if (prepared.series.length < 2) return;
  const scale = macroLiquidityComparisonScale(prepared.series, options);
  const guide = svg.querySelector(".macro-liquidity-hover-guide");
  const liquidityDot = svg.querySelector(".macro-liquidity-hover-dot.liquidity");
  const spxDot = svg.querySelector(".macro-liquidity-hover-dot.spx");
  const spyWarningDot = svg.querySelector(".macro-liquidity-hover-dot.spy-warning");
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * scale.W;
    const point = nearestMacroLiquidityPoint(prepared.series, svgX, scale);
    if (!point) return;
    const pointX = scale.x(point.time);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.42");
    liquidityDot?.setAttribute("cx", pointX.toFixed(1));
    liquidityDot?.setAttribute("cy", scale.yPercentile(point.percentile).toFixed(1));
    liquidityDot?.setAttribute("opacity", "1");
    if (Number.isFinite(point.spxIndexed)) {
      spxDot?.setAttribute("cx", pointX.toFixed(1));
      spxDot?.setAttribute("cy", scale.ySpx(point.spxIndexed).toFixed(1));
      spxDot?.setAttribute("opacity", "1");
    } else {
      spxDot?.setAttribute("opacity", "0");
    }
    if (Number.isFinite(point.spyWarning)) {
      spyWarningDot?.setAttribute("cx", pointX.toFixed(1));
      spyWarningDot?.setAttribute("cy", scale.yPercentile(point.spyWarning).toFixed(1));
      spyWarningDot?.setAttribute("opacity", "1");
    } else {
      spyWarningDot?.setAttribute("opacity", "0");
    }
    renderMacroLiquidityComparisonTooltip(tooltip, chartNode, event, point);
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    liquidityDot?.setAttribute("opacity", "0");
    spxDot?.setAttribute("opacity", "0");
    spyWarningDot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function nearestMacroLiquidityPoint(points, svgX, scale) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  points.forEach((point) => {
    const distance = Math.abs(scale.x(point.time) - svgX);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  });
  return best;
}

function renderMacroLiquidityComparisonTooltip(tooltip, chartNode, event, point) {
  const spxText = Number.isFinite(point.spxIndexed) ? `S&P 500 indexed ${point.spxIndexed.toFixed(1)}` : "S&P 500 indexed --";
  const warningText = Number.isFinite(point.spyWarning)
    ? `SPY Early Warning ${point.spyWarning.toFixed(1)}${point.spyWarningRegimeCn ? ` · ${point.spyWarningRegimeCn}` : ""}`
    : "SPY Early Warning --";
  const trailing = Number.isFinite(point.sp500Trailing3m) ? ` · 3M ${formatSignedMetric(point.sp500Trailing3m, 2)}%` : "";
  tooltip.innerHTML = `
    <b>${escapeHtml(point.date)} · p${point.percentile.toFixed(0)}</b>
    <span>综合评分 ${Number.isFinite(point.score) ? point.score.toFixed(1) : "--"} · ${escapeHtml(spxText)}</span>
    <small>${escapeHtml(warningText)} · ${Number.isFinite(point.sp500) ? `SPX ${point.sp500.toFixed(2)}` : "SPX --"}${trailing}</small>
  `;
  const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
  tooltip.hidden = false;
  const left = Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8));
  const top = Math.min(Math.max(8, event.clientY - parentRect.top - 54), Math.max(8, parentRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function openMacroLiquidityTrendModal() {
  const modal = $("#macroLiquidityTrendModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  renderMacroLiquidityTrendModalChart();
  $("#closeMacroLiquidityTrendModal")?.focus();
}

function closeMacroLiquidityTrendModal() {
  const modal = $("#macroLiquidityTrendModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderMacroLiquidityTrendModalChart() {
  const node = $("#macroLiquidityTrendModalChart");
  if (!node) return;
  const panel = state.macroLiquidity || DEFAULT_DATA.macroLiquidity || {};
  const equityPanel = macroLiquidityEquityPanel();
  const warningPanel = spyWarningTrendPanel();
  node.innerHTML = renderMacroLiquidityTrendChart(panel.trend || {}, { equity: equityPanel, warning: warningPanel, large: true });
  bindMacroLiquidityTrendInteractions(node, panel.trend || {}, {
    equity: equityPanel,
    warning: warningPanel,
    large: true,
    tooltipSelector: "#macroLiquidityTrendModalTooltip",
  });
}

function macroLiquidityTrendClass(value) {
  if (value === "上行") return "supportive";
  if (value === "下行") return "restrictive";
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || Math.abs(numeric) < 1) return "neutral";
  return numeric > 0 ? "supportive" : "restrictive";
}

function renderMacroLiquidityBalance(balance) {
  if (!Array.isArray(balance) || !balance.length) return "";
  return balance.map((item) => {
    const contribution = Number(item.contribution) || 0;
    const direction = item.direction || (contribution > 0 ? "supportive" : contribution < 0 ? "restrictive" : "neutral");
    return `
      <span class="${escapeHtml(direction)}">
        <b>${escapeHtml(item.label || "")}</b>
        <em>${Number(item.count) || 0}项</em>
        <strong>${contribution >= 0 ? "+" : ""}${contribution.toFixed(1)}</strong>
      </span>
    `;
  }).join("");
}

function renderMacroLiquidityImplications(implications) {
  if (!Array.isArray(implications) || !implications.length) return "";
  return implications.map((item) => `
    <span class="${escapeHtml(item.tone || "neutral")}">
      <b>${escapeHtml(item.label || "")}</b>
      <em>${escapeHtml(item.text || "")}</em>
    </span>
  `).join("");
}

function macroLiquidityLabel(score) {
  if (score >= 70) return "流动性宽松";
  if (score >= 55) return "边际宽松";
  if (score > 45) return "中性";
  if (score > 30) return "偏紧";
  return "紧缩压力";
}

function macroLiquidityClass(score) {
  if (score >= 55) return "supportive";
  if (score <= 45) return "restrictive";
  return "neutral";
}

async function loadHistoryData() {
  const statsNode = $("#historyStats");
  const chartNode = $("#historyInteractiveChart");
  const crossChartNode = $("#crossHistoryChart");
  if ((!statsNode || !chartNode) && !crossChartNode) return;
  if (window.location.protocol === "file:") {
    renderCrossHistoryUnavailable("HTTP 服务模式下显示跨市场历史数据");
    return;
  }
  try {
    const [summaryResponse, statsResponse] = await Promise.all([
      fetch(`/api/history?ts=${Date.now()}`, { cache: "no-store" }),
      fetch(`/api/history/stats?limit=180&ts=${Date.now()}`, { cache: "no-store" }),
    ]);
    if (!summaryResponse.ok) throw new Error(`history summary HTTP ${summaryResponse.status}`);
    if (!statsResponse.ok) throw new Error(`history stats HTTP ${statsResponse.status}`);
    historySummaryCache = await summaryResponse.json();
    historyStatsCache = orderHistoryStats(await statsResponse.json());
    renderHistorySelectors();
    renderHistoryStats();
    renderCrossMarketHistoryControls();
    const tasks = [];
    if (chartNode) {
      tasks.push(loadSelectedHistorySeries().catch((error) => {
        console.warn("Failed to load selected history series", error);
        renderHistoryUnavailable("历史序列加载失败");
      }));
    }
    if (crossChartNode) {
      tasks.push(loadSelectedCrossMarketHistory().catch((error) => {
        console.warn("Failed to load cross-market history series", error);
        renderCrossHistoryUnavailable("跨市场历史序列加载失败");
      }));
    }
    await Promise.all(tasks);
  } catch (error) {
    console.warn("Failed to load historical series", error);
    renderHistoryUnavailable("历史库暂不可用");
    renderCrossHistoryUnavailable("跨市场历史库暂不可用");
  }
}

function orderHistoryStats(stats) {
  const rows = Array.isArray(stats) ? stats : [];
  return rows.sort((left, right) => {
    const leftPreferred = PREFERRED_HISTORY_SERIES.indexOf(left.name);
    const rightPreferred = PREFERRED_HISTORY_SERIES.indexOf(right.name);
    const leftRank = leftPreferred === -1 ? 999 : leftPreferred;
    const rightRank = rightPreferred === -1 ? 999 : rightPreferred;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return (right.count || 0) - (left.count || 0);
  });
}

function renderHistorySelectors() {
  const select = $("#historySeriesSelect");
  const coverage = $("#historyCoverage");
  if (!select) return;
  const options = historyStatsCache.slice(0, 140);
  if (!options.length) {
    select.innerHTML = `<option>暂无历史序列</option>`;
    select.disabled = true;
    if (coverage) coverage.textContent = "no historical rows";
    return;
  }
  select.disabled = false;
  if (!selectedHistorySeriesKey || !options.some((item) => historySeriesKey(item) === selectedHistorySeriesKey)) {
    selectedHistorySeriesKey = historySeriesKey(options[0]);
  }
  select.innerHTML = options.map((item) => `
    <option value="${escapeHtml(historySeriesKey(item))}" ${historySeriesKey(item) === selectedHistorySeriesKey ? "selected" : ""}>
      ${escapeHtml(historySeriesLabel(item))}
    </option>
  `).join("");
  if (coverage && historySummaryCache) {
    const start = historySummaryCache.historicalStartDate || "--";
    const end = historySummaryCache.historicalEndDate || "--";
    coverage.textContent = `${start} → ${end} · ${historySummaryCache.historicalObservationCount || 0} rows · ${historySummaryCache.historicalSeriesCount || 0} series`;
  }
}

function renderHistoryStats() {
  const node = $("#historyStats");
  if (!node) return;
  const selected = selectedHistorySeries();
  if (!selected) {
    node.innerHTML = `<div class="empty-state compact">暂无历史统计</div>`;
    return;
  }
  const unit = selected.unit ? ` ${selected.unit}` : "";
  const stats = [
    ["最新", formatHistoryValue(selected.latest, unit)],
    ["样本数", selected.count ?? "--"],
    ["区间", `${selected.startDate || "--"} / ${selected.endDate || "--"}`],
    ["P10 / P50 / P90", `${formatHistoryValue(selected.p10, unit)} / ${formatHistoryValue(selected.p50, unit)} / ${formatHistoryValue(selected.p90, unit)}`],
    ["Min / Max", `${formatHistoryValue(selected.min, unit)} / ${formatHistoryValue(selected.max, unit)}`],
  ];
  node.innerHTML = stats.map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function crossHistoryGroups() {
  const groups = state.cross?.historySeries;
  return Array.isArray(groups) ? groups : [];
}

function crossHistoryGroupLabel(group) {
  return currentLanguage === "en" ? (group.en || group.label || group.id) : (group.label || group.en || group.id);
}

function matchingHistoryStat(target) {
  return historyStatsCache.find((item) => (
    item.category === target.category
    && item.name === target.name
    && String(item.label || "") === String(target.label || "")
  ));
}

function crossHistoryOptions(groupId = crossHistoryGroup) {
  const group = crossHistoryGroups().find((item) => item.id === groupId) || crossHistoryGroups()[0];
  if (!group) return [];
  return (group.series || []).map((target) => ({
    group,
    target,
    stat: matchingHistoryStat(target)
  })).filter((item) => item.stat);
}

function allCrossHistoryOptionsByGroup() {
  return crossHistoryGroups().map((group) => ({
    group,
    options: crossHistoryOptions(group.id)
  })).filter((item) => item.options.length);
}

function renderCrossMarketHistoryControls() {
  const groupNode = $("#crossHistoryGroupControls");
  const select = $("#crossHistorySeriesSelect");
  const coverage = $("#crossHistoryCoverage");
  if (!groupNode || !select) return;
  const groups = allCrossHistoryOptionsByGroup();
  if (!groups.length) {
    select.innerHTML = `<option>暂无跨市场历史序列</option>`;
    select.disabled = true;
    groupNode.innerHTML = "";
    renderCrossHistoryStats(null);
    if (coverage) coverage.textContent = historyStatsCache.length ? "no cross-market history series" : "loading public history";
    return;
  }
  if (!groups.some((item) => item.group.id === crossHistoryGroup)) {
    crossHistoryGroup = groups[0].group.id;
  }
  groupNode.innerHTML = groups.map(({ group, options }) => `
    <button type="button" class="${group.id === crossHistoryGroup ? "active" : ""}" data-cross-history-group="${escapeHtml(group.id)}">
      ${escapeHtml(crossHistoryGroupLabel(group))}<span>${options.length}</span>
    </button>
  `).join("");
  const options = crossHistoryOptions(crossHistoryGroup);
  if (!selectedCrossHistorySeriesKey || !options.some((item) => historySeriesKey(item.target) === selectedCrossHistorySeriesKey)) {
    selectedCrossHistorySeriesKey = historySeriesKey(options[0].target);
  }
  select.disabled = false;
  select.innerHTML = options.map(({ target }) => `
    <option value="${escapeHtml(historySeriesKey(target))}" ${historySeriesKey(target) === selectedCrossHistorySeriesKey ? "selected" : ""}>
      ${escapeHtml(target.displayName || historySeriesLabel(target))}
    </option>
  `).join("");
  const selected = selectedCrossHistoryOption();
  renderCrossHistoryStats(selected);
  if (coverage && selected) {
    const stat = selected.stat;
    coverage.textContent = `${crossHistoryGroupLabel(selected.group)} · ${stat.startDate || "--"} → ${stat.endDate || "--"} · ${crossHistoryRangeYears}Y dynamic`;
  }
}

function selectedCrossHistoryOption() {
  return crossHistoryOptions(crossHistoryGroup).find((item) => historySeriesKey(item.target) === selectedCrossHistorySeriesKey) || crossHistoryOptions(crossHistoryGroup)[0];
}

function renderCrossHistoryStats(selected) {
  const node = $("#crossHistoryStats");
  if (!node) return;
  if (!selected) {
    node.innerHTML = `<div class="empty-state compact">暂无跨市场历史统计</div>`;
    return;
  }
  const stat = selected.stat;
  const unit = stat.unit ? ` ${stat.unit}` : "";
  const rows = [
    ["最新", formatHistoryValue(stat.latest, unit)],
    ["样本数", stat.count ?? "--"],
    ["区间", `${stat.startDate || "--"} / ${stat.endDate || "--"}`],
    ["P10 / P50 / P90", `${formatHistoryValue(stat.p10, unit)} / ${formatHistoryValue(stat.p50, unit)} / ${formatHistoryValue(stat.p90, unit)}`],
    ["来源", selected.target.source || stat.source || "--"],
  ];
  node.innerHTML = rows.map(([label, value]) => `
    <div class="history-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

async function loadSelectedCrossMarketHistory() {
  renderCrossMarketHistoryControls();
  const selected = selectedCrossHistoryOption();
  if (!selected) {
    renderCrossHistoryUnavailable("暂无可绘制跨市场历史序列");
    return;
  }
  const target = selected.target;
  const params = new URLSearchParams({
    category: target.category,
    name: target.name,
    years: String(crossHistoryRangeYears),
    limit: "1100",
  });
  if (target.label) params.set("label", target.label);
  const response = await fetch(`/api/history/series?${params.toString()}&ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`cross history series HTTP ${response.status}`);
  renderCrossMarketHistoryChart(await response.json());
}

async function loadSelectedHistorySeries() {
  const selected = selectedHistorySeries();
  if (!selected) {
    renderHistoryUnavailable("暂无可绘制历史序列");
    return;
  }
  const params = new URLSearchParams({
    category: selected.category,
    name: selected.name,
    years: String(historyRangeYears),
    limit: "1100",
  });
  if (selected.label) params.set("label", selected.label);
  const response = await fetch(`/api/history/series?${params.toString()}&ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`history series HTTP ${response.status}`);
  renderInteractiveHistoryChart(await response.json());
}

function renderInteractiveHistoryChart(payload) {
  renderHistoricalLineChart(payload, {
    chartSelector: "#historyInteractiveChart",
    tooltipSelector: "#historyChartTooltip",
    emptyMessage: "历史点数不足,等待回填或下一次后台更新",
  });
}

function renderCrossMarketHistoryChart(payload) {
  renderHistoricalLineChart(payload, {
    chartSelector: "#crossHistoryChart",
    tooltipSelector: "#crossHistoryTooltip",
    emptyMessage: "跨市场历史点数不足,等待回填或下一次后台更新",
  });
}

function renderHistoricalLineChart(payload, options = {}) {
  const node = $(options.chartSelector || "#historyInteractiveChart");
  if (!node) return;
  const points = (payload?.points || [])
    .map((point) => ({ ...point, time: Date.parse(point.date), value: Number(point.value) }))
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));
  const series = payload?.series || selectedHistorySeries() || {};
  if (points.length < 2) {
    node.innerHTML = `<div class="empty-state">${escapeHtml(options.emptyMessage || "历史点数不足")}</div>`;
    $(options.tooltipSelector || "#historyChartTooltip")?.setAttribute("hidden", "");
    return;
  }
  const W = 1040;
  const H = 300;
  const pad = { l: 52, r: 22, t: 18, b: 36 };
  const minTime = Math.min(...points.map((point) => point.time));
  const maxTime = Math.max(...points.map((point) => point.time));
  const rawMin = Math.min(...points.map((point) => point.value));
  const rawMax = Math.max(...points.map((point) => point.value));
  const spread = rawMax - rawMin || Math.max(1, Math.abs(rawMax) * 0.04);
  const minValue = rawMin - spread * 0.08;
  const maxValue = rawMax + spread * 0.08;
  const x = (time) => pad.l + ((time - minTime) / Math.max(1, maxTime - minTime)) * (W - pad.l - pad.r);
  const y = (value) => pad.t + ((maxValue - value) / Math.max(1e-9, maxValue - minValue)) * (H - pad.t - pad.b);
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
  const yTicks = buildTicks(minValue, maxValue, 5);
  const xTicks = buildDateTicks(points, 5);
  const unit = series.unit || points[0]?.unit || "";
  node.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHtml(series.name || "Historical series")}" data-history-chart>
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      ${yTicks.map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(tick).toFixed(1)}" y2="${y(tick).toFixed(1)}" stroke="var(--line-soft)"></line>
        <text x="10" y="${y(tick).toFixed(1)}" dy="4" fill="var(--faint)" font-size="11" font-family="var(--mono)">${formatAxisTick(tick)}</text>
      `).join("")}
      ${xTicks.map((point) => `
        <text x="${x(point.time).toFixed(1)}" y="${H - 10}" text-anchor="middle" fill="var(--faint)" font-size="11" font-family="var(--mono)">${formatMonthLabel(point.time)}</text>
      `).join("")}
      <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.1" stroke-linejoin="round" stroke-linecap="round"></path>
      <circle cx="${x(points[points.length - 1].time).toFixed(1)}" cy="${y(points[points.length - 1].value).toFixed(1)}" r="4" fill="var(--accent)"></circle>
      <line class="history-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke="var(--ink)" stroke-opacity="0" stroke-dasharray="3 4"></line>
      <circle class="history-hover-dot" cx="${pad.l}" cy="${pad.t}" r="4" fill="var(--bear)" opacity="0"></circle>
      <text x="${pad.l}" y="13" fill="var(--muted)" font-size="11" font-family="var(--mono)">${escapeHtml(series.source || "")}</text>
      <text x="${W - pad.r}" y="13" text-anchor="end" fill="var(--muted)" font-size="11" font-family="var(--mono)">${escapeHtml(unit)}</text>
    </svg>
  `;
  bindHistoryChartHover(node, points, { minTime, maxTime, minValue, maxValue, W, H, pad }, series, options.tooltipSelector || "#historyChartTooltip");
}

function bindHistoryChartHover(chartNode, points, scale, series, tooltipSelector = "#historyChartTooltip") {
  const svg = chartNode.querySelector("[data-history-chart]");
  const tooltip = $(tooltipSelector);
  if (!svg || !tooltip) return;
  const guide = svg.querySelector(".history-hover-guide");
  const dot = svg.querySelector(".history-hover-dot");
  const x = (time) => scale.pad.l + ((time - scale.minTime) / Math.max(1, scale.maxTime - scale.minTime)) * (scale.W - scale.pad.l - scale.pad.r);
  const y = (value) => scale.pad.t + ((scale.maxValue - value) / Math.max(1e-9, scale.maxValue - scale.minValue)) * (scale.H - scale.pad.t - scale.pad.b);
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const targetTime = scale.minTime + ratio * (scale.maxTime - scale.minTime);
    const point = nearestPoint(points, targetTime);
    if (!point) return;
    const pointX = x(point.time);
    const pointY = y(point.value);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.35");
    dot?.setAttribute("cx", pointX.toFixed(1));
    dot?.setAttribute("cy", pointY.toFixed(1));
    dot?.setAttribute("opacity", "1");
    const unit = series.unit || point.unit || "";
    tooltip.innerHTML = `<b>${escapeHtml(point.date)}</b>${escapeHtml(series.name || point.name)} · ${escapeHtml(formatHistoryValue(point.value, unit ? ` ${unit}` : ""))}`;
    tooltip.hidden = false;
    const chartRect = chartNode.getBoundingClientRect();
    tooltip.style.left = `${Math.min(chartNode.clientWidth - 250, Math.max(8, event.clientX - chartRect.left + 12))}px`;
    tooltip.style.top = `${Math.max(8, event.clientY - chartRect.top - 42)}px`;
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    dot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function renderHistoryUnavailable(message) {
  const statsNode = $("#historyStats");
  const chartNode = $("#historyInteractiveChart");
  const coverage = $("#historyCoverage");
  if (coverage) coverage.textContent = message;
  if (statsNode) statsNode.innerHTML = `<div class="empty-state compact">${escapeHtml(message)}</div>`;
  if (chartNode) chartNode.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderCrossHistoryUnavailable(message) {
  const statsNode = $("#crossHistoryStats");
  const chartNode = $("#crossHistoryChart");
  const coverage = $("#crossHistoryCoverage");
  if (coverage) coverage.textContent = message;
  if (statsNode) statsNode.innerHTML = `<div class="empty-state compact">${escapeHtml(message)}</div>`;
  if (chartNode) chartNode.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  $("#crossHistoryTooltip")?.setAttribute("hidden", "");
}

function selectedHistorySeries() {
  return historyStatsCache.find((item) => historySeriesKey(item) === selectedHistorySeriesKey) || historyStatsCache[0];
}

function historySeriesKey(item) {
  return `${item.category || ""}||${item.name || ""}||${item.label || ""}`;
}

function historySeriesLabel(item) {
  const label = item.label ? ` · ${item.label}` : "";
  const unit = item.unit ? ` (${item.unit})` : "";
  return `${item.name}${label}${unit}`;
}

function formatHistoryValue(value, unit = "") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  const digits = Math.abs(numeric) >= 100 ? 1 : Math.abs(numeric) >= 10 ? 2 : 3;
  return `${numeric.toLocaleString(currentLanguage === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: digits })}${unit}`;
}

function buildTicks(minValue, maxValue, count) {
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue) || count <= 1) return [];
  const step = (maxValue - minValue) / (count - 1);
  return Array.from({ length: count }, (_, index) => minValue + step * index);
}

function buildDateTicks(points, count) {
  if (!points.length) return [];
  if (points.length <= count) return points;
  const last = points.length - 1;
  return Array.from({ length: count }, (_, index) => points[Math.round(index * last / (count - 1))]);
}

function formatAxisTick(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  if (Math.abs(numeric) >= 1000) return `${(numeric / 1000).toFixed(1)}k`;
  if (Math.abs(numeric) >= 100) return numeric.toFixed(0);
  return numeric.toFixed(2);
}

function formatMonthLabel(time) {
  return new Date(time).toLocaleDateString(currentLanguage === "en" ? "en-US" : "zh-CN", { year: "2-digit", month: "2-digit" });
}

function nearestPoint(points, targetTime) {
  if (!points.length) return null;
  let best = points[0];
  let bestDistance = Math.abs(points[0].time - targetTime);
  for (const point of points) {
    const distance = Math.abs(point.time - targetTime);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

function renderPercentileDashboard() {
  const percentiles = state.percentiles || {};
  const trends = (percentiles.trends || []).filter((trend) => Array.isArray(trend.points) && trend.points.length);
  percentileTrendCache = trends;
  const compactTrends = visiblePercentileTrends(trends);
  const method = $("#percentileMethod");
  if (method) {
    method.textContent = trends.length ? `核心${compactTrends.length}项 · 放大查看全部${trends.length}项` : "等待历史百分位数据";
  }
  drawPercentileTrendChart(compactTrends, {
    chartSelector: "#percentileTrendChart",
    legendSelector: "#percentileTrendLegend",
    large: false,
    hiddenCount: Math.max(0, trends.length - compactTrends.length),
  });
  renderPercentileMovers(percentiles.movers || []);
  renderPercentileAlerts(percentiles.alerts || []);
}

function visiblePercentileTrends(trends) {
  const byName = new Map(trends.map((trend) => [trend.name, trend]));
  const ordered = CORE_PERCENTILE_TRENDS.map((name) => byName.get(name)).filter(Boolean);
  const fill = trends.filter((trend) => !CORE_PERCENTILE_TRENDS.includes(trend.name));
  return [...ordered, ...fill].slice(0, DEFAULT_PERCENTILE_TREND_LIMIT);
}

function percentileStressRank(trend) {
  const latest = Number(trend.latestPercentile);
  const change = Math.abs(Number(trend.change) || 0);
  const edgeDistance = Number.isFinite(latest) ? Math.abs(latest - 50) : 0;
  return edgeDistance + change * 0.35;
}

function selectPercentileModalTrends(mode, trends = percentileTrendCache) {
  if (mode === "core") return visiblePercentileTrends(trends);
  if (mode === "stress") {
    const stress = trends
      .filter((trend) => {
        const latest = Number(trend.latestPercentile);
        const change = Math.abs(Number(trend.change) || 0);
        return (Number.isFinite(latest) && (latest <= 15 || latest >= 85)) || change >= 50;
      })
      .sort((a, b) => percentileStressRank(b) - percentileStressRank(a));
    return stress.length ? stress : [...trends].sort((a, b) => percentileStressRank(b) - percentileStressRank(a)).slice(0, DEFAULT_PERCENTILE_TREND_LIMIT);
  }
  return trends;
}

function renderPercentileModalControls() {
  const controls = $("#percentileModalControls");
  if (!controls) return;
  controls.innerHTML = PERCENTILE_MODAL_MODES.map((mode) => {
    const count = selectPercentileModalTrends(mode.id).length;
    return `<button type="button" class="${percentileModalMode === mode.id ? "active" : ""}" data-percentile-mode="${mode.id}">${mode.label}<span>${count}</span></button>`;
  }).join("");
}

function renderPercentileModalChart() {
  const selectedMode = PERCENTILE_MODAL_MODES.find((mode) => mode.id === percentileModalMode) || PERCENTILE_MODAL_MODES[0];
  const selectedTrends = selectPercentileModalTrends(selectedMode.id);
  const title = $("#percentileModalTitle");
  if (title) title.textContent = `历史百分位趋势 · ${selectedMode.title}`;
  renderPercentileModalControls();
  drawPercentileTrendChart(selectedTrends, {
    chartSelector: "#percentileModalChart",
    legendSelector: "#percentileModalLegend",
    large: true,
  });
}

function drawPercentileTrendChart(trends, options = {}) {
  const node = $(options.chartSelector || "#percentileTrendChart");
  const legend = $(options.legendSelector || "#percentileTrendLegend");
  if (!node || !legend) return;
  if (!trends.length) {
    node.innerHTML = `<div class="empty-state">暂无可绘制的历史百分位趋势</div>`;
    legend.innerHTML = "";
    return;
  }
  const colors = ["var(--accent)", "var(--bear)", "#3267a8", "var(--neutral)", "var(--accent-2)", "#7a5a9e", "#5d7f38", "#a05c42"];
  const W = options.large ? 1040 : 760;
  const H = options.large ? 460 : 252;
  const pad = options.large ? { l: 50, r: 30, t: 24, b: 42 } : { l: 42, r: 20, t: 18, b: 34 };
  const prepared = trends.map((trend, index) => ({
    trend,
    index,
    color: colors[index % colors.length],
    points: trend.points
      .map((point) => ({ ...point, time: Date.parse(point.date), percentile: Number(point.percentile) }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.percentile)),
  }));
  const allPoints = prepared.flatMap((item) => item.points);
  if (!allPoints.length) {
    node.innerHTML = `<div class="empty-state">暂无可绘制的历史百分位趋势</div>`;
    legend.innerHTML = "";
    return;
  }
  const minTime = Math.min(...allPoints.map((point) => point.time));
  const maxTime = Math.max(...allPoints.map((point) => point.time));
  const x = (time) => {
    if (maxTime === minTime) return pad.l + (W - pad.l - pad.r) / 2;
    return pad.l + ((time - minTime) / (maxTime - minTime)) * (W - pad.l - pad.r);
  };
  const y = (percentile) => pad.t + ((100 - percentile) / 100) * (H - pad.t - pad.b);
  const linePath = (points) => points
    .map((point, index) => `${index ? "L" : "M"}${x(point.time).toFixed(1)},${y(point.percentile).toFixed(1)}`)
    .join(" ");
  const dateLabel = (time) => new Date(time).toLocaleDateString(currentLanguage === "en" ? "en-US" : "zh-CN", { year: "2-digit", month: "2-digit" });
  node.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Historical percentile trends" data-percentile-chart>
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
      <rect x="${pad.l}" y="${y(100)}" width="${W - pad.l - pad.r}" height="${Math.max(1, y(90) - y(100))}" class="percentile-zone high"></rect>
      <rect x="${pad.l}" y="${y(10)}" width="${W - pad.l - pad.r}" height="${Math.max(1, y(0) - y(10))}" class="percentile-zone low"></rect>
      ${[0, 25, 50, 75, 100].map((tick) => `
        <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(tick)}" y2="${y(tick)}" stroke="var(--line-soft)"></line>
        <text x="9" y="${y(tick) + 4}" fill="var(--muted)" font-size="11" font-family="var(--mono)">p${tick}</text>
      `).join("")}
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(90)}" y2="${y(90)}" stroke="var(--bear)" stroke-opacity=".25" stroke-dasharray="4 5"></line>
      <line x1="${pad.l}" x2="${W - pad.r}" y1="${y(10)}" y2="${y(10)}" stroke="var(--accent)" stroke-opacity=".25" stroke-dasharray="4 5"></line>
      <text x="${pad.l}" y="${H - 9}" fill="var(--faint)" font-size="11" font-family="var(--mono)">${dateLabel(minTime)}</text>
      <text x="${W - pad.r}" y="${H - 9}" text-anchor="end" fill="var(--faint)" font-size="11" font-family="var(--mono)">${dateLabel(maxTime)}</text>
      ${prepared.map(({ trend, color, points }) => {
        const latest = points[points.length - 1];
        const isFocused = percentileFocusedTrend === trend.name;
        const isDimmed = Boolean(percentileFocusedTrend && !isFocused);
        const lineClass = isDimmed ? "percentile-focus-dim" : isFocused ? "percentile-focus-active" : "";
        const strokeWidth = isFocused ? (options.large ? 3.1 : 3.4) : (options.large ? 1.9 : 2.5);
        return `
          <g class="${lineClass}" data-percentile-series="${escapeHtml(trend.name)}">
            <path d="${linePath(points)}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-opacity="${options.large ? "0.72" : "0.92"}" stroke-linejoin="round" stroke-linecap="round" data-percentile-line="${escapeHtml(trend.name)}"></path>
            ${latest ? `<circle cx="${x(latest.time).toFixed(1)}" cy="${y(latest.percentile).toFixed(1)}" r="${isFocused ? 4.5 : 3.2}" fill="${color}"></circle>` : ""}
            ${latest && (!options.large || isFocused) ? `<text x="${Math.min(W - pad.r - 4, x(latest.time) + 8).toFixed(1)}" y="${y(latest.percentile).toFixed(1)}" dy="4" fill="${color}" font-size="10.5" font-family="var(--mono)">${escapeHtml(trend.name)}</text>` : ""}
          </g>
        `;
      }).join("")}
      <line class="percentile-hover-guide" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}" stroke="var(--ink)" stroke-opacity="0" stroke-dasharray="3 4"></line>
      <circle class="percentile-hover-dot" cx="${pad.l}" cy="${pad.t}" r="4" fill="var(--accent)" opacity="0"></circle>
    </svg>
  `;
  const hiddenNote = options.hiddenCount ? `<span class="muted-chip">+${options.hiddenCount} 项在放大图</span>` : "";
  legend.innerHTML = prepared.map(({ trend, color }) => `
    <button type="button" class="${percentileFocusedTrend === trend.name ? "active" : ""}" data-percentile-focus="${escapeHtml(trend.name)}" aria-pressed="${percentileFocusedTrend === trend.name ? "true" : "false"}">
      <i style="background:${color}"></i><span>${escapeHtml(trend.name)}</span> <b>p${trend.latestPercentile ?? "--"}</b>
    </button>
  `).join("") + hiddenNote;
  bindPercentileTrendInteractions(node, legend, prepared, { minTime, maxTime, W, H, pad, x, y }, options);
}

function bindPercentileTrendInteractions(chartNode, legendNode, prepared, scale, options = {}) {
  const svg = chartNode.querySelector("[data-percentile-chart]");
  const tooltip = $(options.tooltipSelector || (options.large ? "#percentileModalTooltip" : "#percentileTrendTooltip"));
  if (!svg || !tooltip) return;
  legendNode.querySelectorAll("[data-percentile-focus]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.percentileFocus || "";
      percentileFocusedTrend = percentileFocusedTrend === name ? "" : name;
      renderPercentileDashboard();
      if (!$("#percentileModal")?.hidden) renderPercentileModalChart();
    });
  });
  const guide = svg.querySelector(".percentile-hover-guide");
  const dot = svg.querySelector(".percentile-hover-dot");
  const points = prepared.flatMap(({ trend, color, points: trendPoints }) => trendPoints.map((point) => ({ ...point, trend, color })));
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * scale.W;
    const svgY = ((event.clientY - rect.top) / rect.height) * scale.H;
    const point = nearestPercentilePoint(points, svgX, svgY, scale);
    if (!point) return;
    const pointX = scale.x(point.time);
    const pointY = scale.y(point.percentile);
    guide?.setAttribute("x1", pointX.toFixed(1));
    guide?.setAttribute("x2", pointX.toFixed(1));
    guide?.setAttribute("stroke-opacity", "0.35");
    dot?.setAttribute("cx", pointX.toFixed(1));
    dot?.setAttribute("cy", pointY.toFixed(1));
    dot?.setAttribute("fill", point.color);
    dot?.setAttribute("opacity", "1");
    renderPercentileTooltip(tooltip, chartNode, event, point);
  });
  svg.addEventListener("mouseleave", () => {
    guide?.setAttribute("stroke-opacity", "0");
    dot?.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });
}

function nearestPercentilePoint(points, svgX, svgY, scale) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const point of points) {
    const distance = Math.hypot((scale.x(point.time) - svgX) * 0.75, scale.y(point.percentile) - svgY);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

function renderPercentileTooltip(tooltip, chartNode, event, point) {
  const valueText = point.value == null ? "" : ` · ${escapeHtml(point.value)}${escapeHtml(point.trend.unit || "")}`;
  tooltip.innerHTML = `
    <b>${escapeHtml(point.trend.name)} · p${escapeHtml(point.percentile)}</b>
    <span>${escapeHtml(point.date)}${valueText}</span>
    <small>${escapeHtml(point.trend.source || point.trend.window || "")}</small>
  `;
  const parentRect = (tooltip.offsetParent || chartNode).getBoundingClientRect();
  tooltip.hidden = false;
  const left = Math.min(Math.max(8, event.clientX - parentRect.left + 12), Math.max(8, parentRect.width - tooltip.offsetWidth - 8));
  const top = Math.min(Math.max(8, event.clientY - parentRect.top - 46), Math.max(8, parentRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function openPercentileModal() {
  const modal = $("#percentileModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  percentileModalMode = "all";
  renderPercentileModalChart();
  $("#closePercentileModal")?.focus();
}

function closePercentileModal() {
  const modal = $("#percentileModal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

function renderPercentileMovers(movers) {
  const node = $("#percentileMovers");
  if (!node) return;
  if (!movers.length) {
    node.innerHTML = `<div class="empty-state compact">暂无显著变化</div>`;
    return;
  }
  node.innerHTML = movers.slice(0, 5).map((item) => `
    <div class="mini-row">
      <span>${escapeHtml(item.name)}<small>${escapeHtml(item.window || "")}</small></span>
      <strong class="${item.change > 0 ? "bear" : "bull"}">${item.change > 0 ? "+" : ""}${item.change}p</strong>
    </div>
  `).join("");
}

function renderPercentileAlerts(alerts) {
  const node = $("#percentileAlerts");
  if (!node) return;
  if (!alerts.length) {
    node.innerHTML = `<div class="empty-state compact">无极端分位</div>`;
    return;
  }
  node.innerHTML = alerts.slice(0, 5).map((item) => `
    <div class="mini-row alert ${item.side === "high" ? "high" : "low"}">
      <span>${escapeHtml(item.name)}<small>${escapeHtml(item.value)} · ${escapeHtml(item.message)}</small></span>
      <strong>p${item.percentile}</strong>
    </div>
  `).join("");
}

function renderDriverDashboard() {
  const driverNode = $("#factorDrivers");
  const pulseNode = $("#modulePulse");
  if (!driverNode || !pulseNode) return;
  const drivers = factorDrivers();
  driverNode.innerHTML = drivers.length ? drivers.map((item) => `
    <div class="driver-row">
      <div>
        <strong>${escapeHtml(item.name)}</strong>
        <span>${escapeHtml(item.module)} · ${escapeHtml(item.value)}</span>
      </div>
      <em class="${item.contribution > 0 ? "bull" : "bear"}">${item.contribution > 0 ? "+" : ""}${item.contribution.toFixed(2)}</em>
    </div>
  `).join("") : `<div class="empty-state compact">暂无有效驱动</div>`;
  pulseNode.innerHTML = state.groups.map((group) => {
    const average = group.factors.reduce((sum, factor) => sum + factor.score, 0) / group.factors.length;
    const width = Math.min(50, Math.abs(average) / 2 * 50);
    const left = average < 0 ? 50 - width : 50;
    return `
      <div class="pulse-row">
        <span>${escapeHtml(currentLanguage === "en" ? group.en : group.name)}</span>
        <div class="pulse-track"><i class="${scoreClass(average)}" style="left:${left.toFixed(1)}%;width:${width.toFixed(1)}%"></i></div>
        <strong class="${scoreClass(average)}">${average.toFixed(2)}</strong>
      </div>
    `;
  }).join("");
}

function factorDrivers() {
  return aggregateDetails().drivers
    .filter((item) => item.contribution !== 0)
    .slice(0, 6)
    .map((item) => ({
      module: item.module,
      name: item.name,
      value: item.value,
      contribution: item.contribution
    }));
}

function bindScorecardEvents() {
  $$("[data-score]").forEach((button) => {
    button.addEventListener("click", () => {
      const [groupIndex, factorIndex, score] = button.dataset.score.split(":").map(Number);
      state.groups[groupIndex].factors[factorIndex].score = score;
      persistState();
      renderScorecard();
      showScoreUpdate();
    });
  });
  $$("[data-weight]").forEach((input) => {
    input.addEventListener("change", () => {
      const group = state.groups[Number(input.dataset.weight)];
      group.weight = Math.max(0, Math.min(100, Number(input.value) || 0));
      persistState();
      renderScorecard();
      showScoreUpdate();
    });
  });
}

function renderPolicy() {
  $("#policyCards").innerHTML = state.policy.rates.map(metricCard).join("");
  $("#plumbingCards").innerHTML = state.policy.plumbing.map(metricCard).join("");
  $("#fedPathChart").innerHTML = state.fedPath.map((row) => `
    <div class="fed-row">
      <div class="fed-date">${row.m}</div>
      <div class="fed-stack" title="Hike ${row.hike}% · Hold ${row.hold}% · Cut ${row.cut}%">
        <span class="hike" style="width:${row.hike}%">${row.hike ? `${row.hike}%` : ""}</span>
        <span class="hold" style="width:${row.hold}%">${row.hold}%</span>
        <span class="cut" style="width:${row.cut}%">${row.cut ? `${row.cut}%` : ""}</span>
      </div>
    </div>
  `).join("");
}

function renderSupply() {
  $("#auctionTable").innerHTML = `
    <thead><tr><th>${t("table.security")}</th><th>${t("table.size")}</th><th>${t("table.highRate")}</th><th>${t("table.bidToCover")}</th><th>${t("table.rating")}</th></tr></thead>
    <tbody>
      ${state.auctions.map((row) => `
        <tr><td>${row.type}</td><td>${row.size}</td><td>${row.yield}</td><td>${row.btc}</td><td>${row.rating}</td></tr>
      `).join("")}
    </tbody>
  `;
  $("#fiscalCards").innerHTML = state.fiscal.map(metricCard).join("");
}

function renderPositioning() {
  $("#cftcList").innerHTML = (state.positioning.cftc || []).map(signalItem).join("");
  $("#dealerCards").innerHTML = (state.positioning.dealers || []).map(metricCard).join("");
  $("#ticCards").innerHTML = (state.positioning.tic || []).map(metricCard).join("");
}

function renderCrossMarket() {
  const max = Math.max(...state.cross.yields.map((item) => item[1]));
  $("#globalYields").innerHTML = state.cross.yields.map(([label, value]) => `
    <div class="bar-item">
      <span>${label}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(value / max) * 100}%"></div></div>
      <strong>${value.toFixed(2)}%</strong>
    </div>
  `).join("");
  $("#riskUsd").innerHTML = state.cross.risk.map(signalItem).join("");
  $("#inflationCommodity").innerHTML = state.cross.inflation.map(signalItem).join("");
  renderCrossMarketHistoryControls();
}

function renderEvents() {
  $("#eventTimeline").innerHTML = state.events.map(([date, title, severity]) => `
    <div class="event-item">
      <strong>${date} · ${title}</strong>
      <span class="severity ${severity === "高" ? "high" : "medium"}">${severity} ${t("event.impact")}</span>
    </div>
  `).join("");
  $("#newsFlow").innerHTML = state.news.map(([date, source, text]) => `
    <div class="news-item">
      <strong>${date} · ${source}</strong>
      <span>${text}</span>
    </div>
  `).join("");
}

function renderIdeas() {
  $("#ideaCards").innerHTML = state.ideas.map((idea, index) => `
    <article class="idea-card">
      <span class="num">${String(index + 1).padStart(2, "0")}</span>
      <h3>${escapeHtml(idea.title)}</h3>
      <div class="idea-card-meta">
        <span class="tag">${escapeHtml(idea.tag)}</span>
        ${idea.confidenceLabel ? `<span class="idea-confidence ${escapeHtml(idea.confidenceLevel || "medium")}">${escapeHtml(idea.confidenceLabel)}</span>` : ""}
      </div>
      <p contenteditable="true" data-idea="${index}">${escapeHtml(idea.text)}</p>
      <small>${t("idea.factorSource")} -> ${escapeHtml(idea.source || "--")}</small>
      ${idea.confidenceNote ? `<small class="idea-confidence-note">${escapeHtml(idea.confidenceNote)}</small>` : ""}
      ${renderIdeaEquityImpact(idea.equityImpact)}
    </article>
  `).join("");
  $$("[data-idea]").forEach((node) => {
    node.addEventListener("blur", () => {
      state.ideas[Number(node.dataset.idea)].text = node.textContent.trim();
      persistState();
      toast(t("toast.idea"));
    });
  });
}

function renderIdeaEquityImpact(impact) {
  const item = impact && typeof impact === "object"
    ? impact
    : {
      available: false,
      proxy: IDEA_SPY_PROXY_LABEL,
      basis: "同类宏观评分水平 + 3M评分变化",
      sampleSize: 0,
      summary: "HTTP模式读取历史样本后显示历史SPY影响。",
      confidenceLabel: "低",
      tone: "neutral"
    };
  const allowedTones = new Set(["positive", "negative", "mixed", "neutral"]);
  const tone = allowedTones.has(item.tone) ? item.tone : "neutral";
  const sampleSize = Number(item.sampleSize);
  const sampleText = Number.isFinite(sampleSize) ? `n=${sampleSize}` : "n=--";
  const confidence = item.confidenceLabel || item.confidence || "低";
  const stats = item.available ? [
    ["1M中位", item.forward1mMedian],
    ["3M中位", item.forward3mMedian],
    ["6M中位", item.forward6mMedian],
    ["3M最大回撤", item.avgMaxDrawdown3m]
  ].map(([label, value]) => `${label} ${formatSignedPercentMetric(value)}`) : [];
  const hitRate = Number(item.hitRate3m);
  if (item.available && Number.isFinite(hitRate)) stats.push(`3M胜率 ${hitRate.toFixed(0)}%`);

  return `
    <div class="idea-equity-impact ${escapeHtml(tone)}">
      <div class="idea-equity-impact-head">
        <strong>历史SPY影响</strong>
        <span>${escapeHtml(confidence)} · ${escapeHtml(sampleText)}</span>
      </div>
      ${stats.length ? `<p>${stats.map((part) => escapeHtml(part)).join(" · ")}</p>` : ""}
      <small>${escapeHtml(item.summary || "历史同类样本不足,暂不显示SPY影响。")}</small>
      <em>${escapeHtml(item.proxy || IDEA_SPY_PROXY_LABEL)} · ${escapeHtml(item.basis || "historical similar-state sample")}</em>
    </div>
  `;
}

function formatSignedPercentMetric(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)}%`;
}

function formatPercentMetric(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return `${numeric.toFixed(1)}%`;
}

function formatNumberMetric(value, digits = 1) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return numeric.toFixed(digits);
}

function metricCard([label, value, note]) {
  return `
    <div class="metric">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${note}</small>
    </div>
  `;
}

function signalItem([label, value, note]) {
  return `
    <div class="signal-item">
      <strong>${label}</strong>
      <span>${value}</span>
      <span>${note}</span>
    </div>
  `;
}

function bp(value) {
  return `${value > 0 ? "+" : ""}${value}bp`;
}

function showScoreUpdate() {
  $("#viewUpdateHint").textContent = t("hint.viewUpdate");
  toast(t("toast.score"));
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 2400);
}

function inlineExportStylesheets(clone) {
  const liveLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"]'));
  const liveStyleSheets = Array.from(document.styleSheets);
  clone.querySelectorAll('link[rel="stylesheet"]').forEach((link, index) => {
    const sourceLink = liveLinks[index];
    const sourceHref = sourceLink?.getAttribute("href") || link.getAttribute("href") || "";
    const sourceUrl = sourceLink?.href || link.href;
    const styleSheet = liveStyleSheets.find((sheet) => sheet.href === sourceUrl);
    let cssRules = null;
    try {
      if (styleSheet) cssRules = styleSheet.cssRules;
    } catch (error) {
      cssRules = null;
    }
    if (!cssRules?.length) return;
    const style = document.createElement("style");
    style.setAttribute("data-export-inline-stylesheet", sourceHref);
    style.textContent = Array.from(cssRules).map((rule) => rule.cssText).join("\n");
    link.replaceWith(style);
  });
}

function buildCurrentHtmlExport() {
  const clone = document.documentElement.cloneNode(true);
  inlineExportStylesheets(clone);
  return `<!DOCTYPE html>\n${clone.outerHTML}\n`;
}

function exportState() {
  const payload = buildCurrentHtmlExport();
  const blob = new Blob([payload], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `macro-liquidity-monitor-${state.asOf || "snapshot"}.html`;
  link.click();
  URL.revokeObjectURL(url);
  toast(t("toast.export"));
}

function resetState() {
  localStorage.removeItem(STORAGE_KEY);
  window.location.reload();
}

function bindNavObserver() {
  const links = $$(".top-nav a");
  const sections = links.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      links.forEach((link) => link.classList.toggle("active", link.getAttribute("href") === `#${entry.target.id}`));
    });
  }, { rootMargin: "-30% 0px -60% 0px" });
  sections.forEach((section) => observer.observe(section));
}

$("#exportState").addEventListener("click", exportState);
$("#resetState").addEventListener("click", resetState);
$("#refreshRuntimeData")?.addEventListener("click", refreshRuntimeData);
$("#refreshEquityRisk")?.addEventListener("click", refreshEquityRisk);
$("#openSourceStatus")?.addEventListener("click", openSourceStatusModal);
$("#closeSourceStatusModal")?.addEventListener("click", closeSourceStatusModal);
$("#sourceStatusControls")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-source-filter]");
  if (!button) return;
  sourceStatusFilter = button.dataset.sourceFilter || "all";
  renderSourceStatusModal();
});
$("#sourceStatusSearch")?.addEventListener("input", (event) => {
  sourceStatusQuery = event.target.value || "";
  renderSourceStatusModal();
});
$("#exportSourceStatusCsv")?.addEventListener("click", exportSourceStatusCsv);
$$("[data-close-source-status-modal]").forEach((node) => {
  node.addEventListener("click", closeSourceStatusModal);
});
$("#expandMacroLiquidityTrend")?.addEventListener("click", openMacroLiquidityTrendModal);
$("#closeMacroLiquidityTrendModal")?.addEventListener("click", closeMacroLiquidityTrendModal);
$$("[data-close-macro-liquidity-trend-modal]").forEach((node) => {
  node.addEventListener("click", closeMacroLiquidityTrendModal);
});
document.addEventListener("click", (event) => {
  if (event.target.closest("#expandEquityRiskHistory")) openEquityRiskHistoryModal();
  if (event.target.closest("#expandGlobalLpplRiskHistory")) openGlobalLpplRiskHistoryModal();
});
$("#closeEquityRiskHistoryModal")?.addEventListener("click", closeEquityRiskHistoryModal);
$$("[data-close-equity-risk-history-modal]").forEach((node) => {
  node.addEventListener("click", closeEquityRiskHistoryModal);
});
$("#closeGlobalLpplRiskHistoryModal")?.addEventListener("click", closeGlobalLpplRiskHistoryModal);
$$("[data-close-global-lppl-risk-history-modal]").forEach((node) => {
  node.addEventListener("click", closeGlobalLpplRiskHistoryModal);
});
$("#expandPercentileChart")?.addEventListener("click", openPercentileModal);
$("#closePercentileModal")?.addEventListener("click", closePercentileModal);
$("#percentileModalControls")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-percentile-mode]");
  if (!button) return;
  percentileModalMode = button.dataset.percentileMode || "all";
  renderPercentileModalChart();
});
$("#historySeriesSelect")?.addEventListener("change", async (event) => {
  selectedHistorySeriesKey = event.target.value;
  renderHistoryStats();
  try {
    await loadSelectedHistorySeries();
  } catch (error) {
    console.warn("Failed to load selected history series", error);
    renderHistoryUnavailable("历史序列加载失败");
  }
});
$("#historyRangeControls")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-history-range]");
  if (!button) return;
  historyRangeYears = Number(button.dataset.historyRange) || 5;
  $$("[data-history-range]").forEach((node) => node.classList.toggle("active", node === button));
  try {
    await loadSelectedHistorySeries();
  } catch (error) {
    console.warn("Failed to change history range", error);
    renderHistoryUnavailable("历史区间加载失败");
  }
});
$("#crossHistoryGroupControls")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-cross-history-group]");
  if (!button) return;
  crossHistoryGroup = button.dataset.crossHistoryGroup || crossHistoryGroup;
  selectedCrossHistorySeriesKey = "";
  try {
    await loadSelectedCrossMarketHistory();
  } catch (error) {
    console.warn("Failed to change cross-market history group", error);
    renderCrossHistoryUnavailable("跨市场历史分组加载失败");
  }
});
$("#crossHistorySeriesSelect")?.addEventListener("change", async (event) => {
  selectedCrossHistorySeriesKey = event.target.value;
  renderCrossMarketHistoryControls();
  try {
    await loadSelectedCrossMarketHistory();
  } catch (error) {
    console.warn("Failed to load selected cross-market history series", error);
    renderCrossHistoryUnavailable("跨市场历史序列加载失败");
  }
});
$("#crossHistoryRangeControls")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-cross-history-range]");
  if (!button) return;
  crossHistoryRangeYears = Number(button.dataset.crossHistoryRange) || 3;
  $$("#crossHistoryRangeControls [data-cross-history-range]").forEach((node) => node.classList.toggle("active", node === button));
  try {
    await loadSelectedCrossMarketHistory();
  } catch (error) {
    console.warn("Failed to change cross-market history range", error);
    renderCrossHistoryUnavailable("跨市场历史区间加载失败");
  }
});
$$("[data-close-percentile-modal]").forEach((node) => {
  node.addEventListener("click", closePercentileModal);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#macroLiquidityTrendModal")?.hidden) closeMacroLiquidityTrendModal();
  if (event.key === "Escape" && !$("#equityRiskHistoryModal")?.hidden) closeEquityRiskHistoryModal();
  if (event.key === "Escape" && !$("#globalLpplRiskHistoryModal")?.hidden) closeGlobalLpplRiskHistoryModal();
  if (event.key === "Escape" && !$("#percentileModal")?.hidden) closePercentileModal();
  if (event.key === "Escape" && !$("#sourceStatusModal")?.hidden) closeSourceStatusModal();
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshRuntimeSnapshotSilently();
});
$("#languageToggle").addEventListener("click", () => {
  setLanguage(currentLanguage === "en" ? "zh" : "en");
  toast(t("toast.language"));
});
renderAll();
loadRuntimeData();
startRuntimeAutoRefresh();
