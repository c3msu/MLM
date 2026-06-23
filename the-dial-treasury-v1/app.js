const GLOBAL_LPPL_INLINE_HISTORY_MAX_POINTS = 120;

const DEFAULT_DATA = {
  asOf: "2026-05-18",
  conclusionSourceQuality: {
    "real-public": 1,
    "derived-public": 0.9,
    "official-news": 0.8,
    "proxy-public": 0.65,
    "modeled": 0.55,
    "manual-placeholder": 0.25
  },
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
    scoredFactorCount: 21,
    method: "Bhadial Conditions Score-compatible 21-factor, 7-module 5Y historical percentile composite; Funding uses EMA(5).",
    summary: "偏紧: 等待 data/dashboard.json 后显示实时 21 因子模块评分。",
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
  signalValidation: {
    available: false,
    reason: "HTTP模式读取 data/dashboard.json 后显示走出样本信号验证。",
    factors: [],
    composites: [],
    clusters: [],
    effectiveWeights: []
  },
  portfolioOverview: {
    available: false,
    summary: "HTTP模式读取 data/dashboard.json 后显示组合总览。",
    layers: [],
    conflicts: [],
    suggestedEquityExposureBand: null
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
    backtest: { available: false, sampleSize: 0, threshold: 65, horizonTests: [] },
    perIndexHistory: {},
    perIndexBacktests: {}
  },
  regionalMonitor: {
    available: false,
    summary: "HTTP模式读取 data/dashboard.json 后显示地区监控。",
    regions: [],
    regionOrder: [],
    alertingRegions: []
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
const EQUITY_FRESHNESS_BACKOFF_MAX_MS = 10 * 60 * 1000;
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
let selectedRegionKey = null;
let equityFreshnessFailureCount = 0;
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
let selectedGlobalLpplSymbol = "";
const CORE_PERCENTILE_TRENDS = ["银行准备金", "净流动性", "13周净流动性动量", "TGA偏离度"];
const DEFAULT_PERCENTILE_TREND_LIMIT = 4;
const PREFERRED_HISTORY_SERIES = ["10Y收益率", "2Y收益率", "30Y收益率", "2s10s斜率", "净流动性", "13周净流动性动量", "TGA偏离度", "商票-TBill利差", "金融条件指数(NFCI)", "SOFR-EFFR利差", "VIX", "HY信用利差", "拍卖投标倍数"];
const SOURCE_STATUS_FILTERS = [
  { id: "all", label: "全部" },
  { id: "ok", label: "真实" },
  { id: "modeled", label: "模型" },
  { id: "problem", label: "问题" },
];
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
    equityFreshnessFailureCount = 0;
    equityFreshnessStatus = payload.equityRiskFreshness || null;
    renderEquityFreshnessStatus(equityFreshnessStatus);
    scheduleEquityFreshnessRefresh(equityFreshnessStatus);
  } catch (error) {
    console.warn("Failed to load equity risk freshness", error);
    equityFreshnessFailureCount += 1;
    equityFreshnessStatus = { stale: true, error: error.message };
    renderEquityFreshnessStatus(equityFreshnessStatus);
    scheduleEquityFreshnessRefresh(equityFreshnessStatus);
  }
}

function equityFreshnessBackoffDelay() {
  const exponent = Math.max(0, equityFreshnessFailureCount - 1);
  return Math.min(EQUITY_FRESHNESS_BACKOFF_MAX_MS, EQUITY_FRESHNESS_FAST_REFRESH_MS * (2 ** exponent));
}

function equityFreshnessRefreshDelay(freshness) {
  if (!freshness) return RUNTIME_AUTO_REFRESH_MS;
  if (freshness.error) return equityFreshnessBackoffDelay();
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
  const qualityMap = state.conclusionSourceQuality || DEFAULT_DATA.conclusionSourceQuality || {};
  return qualityMap[String(mode || "real-public")] ?? 1;
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
  renderRegionalMonitor();
  renderSignalValidation();
  renderPortfolioOverview();
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
    else if (status === "warning" || status === "warn" || status === "stale") counts.warning += 1;
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
  if (normalized === "stale") return "过期";
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
  if (filter === "problem") return status === "error" || status === "warning" || status === "warn" || status === "stale";
  return true;
}

function sourceStatusSearchText(source) {
  return [source.name, source.status, source.latest, source.note, source.ageDays, source.expectedMaxAgeDays]
    .map((value) => String(value || "").toLowerCase())
    .join(" ");
}

function sourceStatusAgeText(source) {
  const ageDays = Number(source.ageDays);
  if (!Number.isFinite(ageDays)) return "--";
  if (ageDays <= 0) return "今天";
  return `${Math.round(ageDays)}天`;
}

function sourceStatusCadenceText(source) {
  const expectedMaxAgeDays = Number(source.expectedMaxAgeDays);
  if (!Number.isFinite(expectedMaxAgeDays)) return "--";
  return `<=${Math.round(expectedMaxAgeDays)}天`;
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
  const statusOrder = { error: 0, stale: 1, warning: 2, warn: 2, modeled: 3, static: 4, unknown: 5, ok: 6 };
  const sorted = [...visibleRows].sort((a, b) => {
    const aStatus = normalizedSourceStatus(a);
    const bStatus = normalizedSourceStatus(b);
    return (statusOrder[aStatus] ?? 4) - (statusOrder[bStatus] ?? 4) || String(a.name || "").localeCompare(String(b.name || ""));
  });
  table.innerHTML = `
    <thead>
      <tr><th>状态</th><th>数据源</th><th>最新日期 / 说明</th><th>数据年龄</th><th>预期节奏</th></tr>
    </thead>
    <tbody>
      ${sorted.length ? sorted.map((source) => `
        <tr>
          <td><span class="status-badge ${sourceStatusClass(source.status)}">${sourceStatusLabel(source.status)}</span></td>
          <td>${escapeHtml(source.name || "--")}</td>
          <td>${escapeHtml(source.latest || source.note || "--")}</td>
          <td>${escapeHtml(sourceStatusAgeText(source))}</td>
          <td>${escapeHtml(sourceStatusCadenceText(source))}</td>
        </tr>
      `).join("") : `<tr><td colspan="5" class="empty-table-cell">没有匹配数据源</td></tr>`}
    </tbody>
  `;
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function exportSourceStatusCsv() {
  const rows = filterSourceStatusRows();
  const csv = [
    ["status", "label", "name", "latest_or_note", "age_days", "expected_max_age_days"].map(csvCell).join(","),
    ...rows.map((source) => [
      source.status || "unknown",
      sourceStatusLabel(source.status),
      source.name || "",
      source.latest || source.note || "",
      source.ageDays ?? "",
      source.expectedMaxAgeDays ?? "",
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
  const equityBandNode = $("#equityBandStance");
  if (equityBandNode) {
    const po = state.portfolioOverview || DEFAULT_DATA.portfolioOverview || {};
    const band = Array.isArray(po.suggestedEquityExposureBand) ? po.suggestedEquityExposureBand : null;
    equityBandNode.textContent = band ? `${Math.round(band[0])}-${Math.round(band[1])}%` : "--";
    equityBandNode.parentElement.dataset.code = band && Number(band[1]) < 90 ? "RESTRICT" : "NEUTRAL";
    const basis = $("#equityBandBasis");
    if (basis) basis.textContent = po.bindingLayer ? `约束层 ${po.bindingLayer}` : "三层调和 · OOS";
  }
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
    <details class="conclusion-audit-fold">
      <summary class="conclusion-audit-head">
        <span>结论审计 · Conclusion Audit</span>
        <strong>${escapeHtml(audit.duration.label)} / ${escapeHtml(audit.curve.label)}</strong>
        <span class="conclusion-audit-cred">可信度 ${escapeHtml(audit.confidence.label)} · 证据质量 ${Math.round(audit.confidence.evidenceQuality * 100)}%</span>
      </summary>
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
    </details>
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
  if (method) {
    method.textContent = "21因子 · 7模块 · 5年历史百分位";
    method.title = panel.method || "5Y rolling percentile composite";
  }
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
  // The panel title now stands for the forward-signals group; the 5Y-study method text
  // lives with that study (its conclusion paragraph) inside the collapsed details, so we
  // keep the static "SPY 预警 / 股票短期风险 / LPPL 泡沫" kicker rather than overwriting it.
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

function portfolioOverviewEvidenceText(evidence) {
  if (!evidence || typeof evidence !== "object" || !evidence.available) {
    return (evidence && evidence.note) || "证据不足";
  }
  const hit = Number(evidence.oosHitRate);
  const base = Number(evidence.baseRate);
  const lift = Number(evidence.lift);
  const lead = Number(evidence.leadTimeDays);
  const sample = Number(evidence.sampleSize);
  const parts = [];
  if (Number.isFinite(hit) && Number.isFinite(base)) parts.push(`OOS命中 ${(hit * 100).toFixed(0)}% vs 基准 ${(base * 100).toFixed(0)}%`);
  if (Number.isFinite(lift)) parts.push(`lift ${lift.toFixed(2)}x`);
  if (Number.isFinite(lead)) parts.push(`提前≈${lead.toFixed(0)}天`);
  if (Number.isFinite(sample)) parts.push(`n=${sample}`);
  return parts.length ? parts.join(" · ") : "证据不足";
}

function portfolioLayerTier(layer) {
  const tier = layer && layer.confidenceTier;
  if (tier === "validated") {
    return { cls: "tier-validated", badge: `<span class="pol-tier validated" title="样本外稳健: 90%自助CI排除0,可作前瞻依据 · OOS-robust">✓稳健</span>` };
  }
  if (tier === "context") {
    return { cls: "tier-context", badge: `<span class="pol-tier context" title="样本外未达稳健: CI跨0,仅作背景上下文,不作前瞻信号 · context only">上下文</span>` };
  }
  return { cls: "tier-unverified", badge: `<span class="pol-tier unverified" title="未经样本外稳健性(CI)检验,谨慎参考 · unverified">未验证</span>` };
}

function portfolioBindingBasisSuffix(panel) {
  const basis = panel && panel.bindingBasis;
  if (!basis || basis === "validated") return "";
  const label = basis === "context" ? "上下文层" : "未验证层";
  return ` <small class="pol-binding-note" title="当前权益仓位带由${label}约束(其样本外稳健性未确立)——谨慎采用 · binding layer is not OOS-robust">⚠ 约束层:${label}</small>`;
}

function renderPortfolioOverview() {
  const panel = state.portfolioOverview || DEFAULT_DATA.portfolioOverview || {};
  const root = $("#portfolioOverviewPanel");
  if (!root) return;
  const summaryNode = $("#portfolioOverviewSummary");
  const bandNode = $("#portfolioOverviewBand");
  const layersNode = $("#portfolioOverviewLayers");
  const tiltNode = $("#portfolioOverviewRegionalTilt");
  const conflictsNode = $("#portfolioOverviewConflicts");
  if (summaryNode) summaryNode.textContent = panel.summary || "--";
  if (bandNode) {
    const band = Array.isArray(panel.suggestedEquityExposureBand) ? panel.suggestedEquityExposureBand : null;
    bandNode.innerHTML = band
      ? `权益仓位 ${Number(band[0]).toFixed(0)}-${Number(band[1]).toFixed(0)}%${portfolioBindingBasisSuffix(panel)}`
      : "仓位区间 --";
    bandNode.dataset.tone = band && Number(band[1]) < 90 ? "restrictive" : "neutral";
  }
  if (!panel.available) {
    if (layersNode) layersNode.innerHTML = "";
    if (tiltNode) tiltNode.innerHTML = "";
    if (conflictsNode) conflictsNode.innerHTML = "";
    return;
  }
  if (tiltNode) {
    const tilt = panel.regionalTilt && typeof panel.regionalTilt === "object" ? panel.regionalTilt : {};
    const breaches = Array.isArray(tilt.breachedRegions) ? tilt.breachedRegions : [];
    const usTilt = panel.usInternalTilt && typeof panel.usInternalTilt === "object" ? panel.usInternalTilt : {};
    const usTiltRow = usTilt.available
      ? `<div class="pot-us-internal"><span class="pol-horizon">美股内部</span>${escapeHtml(usTilt.tiltCn || "")}</div>`
      : "";
    tiltNode.innerHTML = tilt.available ? `
      <div class="portfolio-overview-tilt-card${breaches.length ? " has-breach" : ""}">
        <div class="pot-head"><span class="pol-horizon">${escapeHtml(tilt.horizonCn || "地区轮动")}</span><strong>全球地区倾斜</strong></div>
        <span class="pot-summary">${escapeHtml(tilt.summary || "")}</span>
        ${usTiltRow}
      </div>
    ` : usTilt.available ? `
      <div class="portfolio-overview-tilt-card">
        <div class="pot-head"><strong>全球地区倾斜</strong></div>
        ${usTiltRow}
      </div>
    ` : "";
  }
  const layers = Array.isArray(panel.layers) ? panel.layers : [];
  if (layersNode) {
    layersNode.innerHTML = layers.map((layer) => {
      const band = Array.isArray(layer.exposureBandPct) ? layer.exposureBandPct : null;
      const score = Number(layer.score);
      const tier = portfolioLayerTier(layer);
      const noteText = layer.confidenceTier && layer.confidenceTier !== "validated"
        ? (layer.contextNoteCn || layer.contextNote || "")
        : "";
      const noteHtml = noteText ? `<div class="pol-context-note">${escapeHtml(noteText)}</div>` : "";
      return `
        <div class="portfolio-overview-layer ${tier.cls}">
          <div class="pol-head">
            <span class="pol-horizon">${escapeHtml(layer.horizonCn || layer.horizon || "")}</span>
            <strong>${escapeHtml(layer.labelCn || layer.label || "")}</strong>
            ${tier.badge}
            <em>${Number.isFinite(score) ? score.toFixed(1) : "--"} · ${escapeHtml(layer.regimeCn || layer.regime || "--")}</em>
          </div>
          <div class="pol-body">
            <span>${band ? `仓位带 ${Number(band[0]).toFixed(0)}-${Number(band[1]).toFixed(0)}%` : "背景层(不直接给仓位)"}</span>
            <span class="pol-stance">${escapeHtml(layer.stance || "")}</span>
          </div>
          <div class="pol-evidence">${escapeHtml(portfolioOverviewEvidenceText(layer.evidence))}${layer.note ? ` · ${escapeHtml(layer.note)}` : ""}</div>
          ${noteHtml}
        </div>
      `;
    }).join("") || `<div class="empty-state compact">暂无可用信号层</div>`;
  }
  if (conflictsNode) {
    const conflicts = Array.isArray(panel.conflicts) ? panel.conflicts : [];
    conflictsNode.innerHTML = conflicts.length ? `
      <h4 class="sv-heading">跨层冲突与调和 · Conflicts</h4>
      ${conflicts.map((conflict) => `
        <div class="portfolio-overview-conflict">
          <strong>${escapeHtml(conflict.description || "")}</strong>
          <span>${escapeHtml(conflict.resolution || "")}</span>
        </div>
      `).join("")}
    ` : "";
  }
}

function signalValidationBadge(classification) {
  const map = {
    leading: ["领先", "leading"],
    coincident: ["同步", "coincident"],
    lagging: ["滞后", "lagging"],
    none: ["无信号", "none"],
  };
  const [label, cls] = map[classification] || ["--", "none"];
  return `<span class="sv-badge ${cls}">${label}</span>`;
}

function formatSignalIc(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(2) : "--";
}

function formatSignalRate(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(0)}%` : "--";
}

function formatSignalLift(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(2)}x` : "--";
}

function formatSignalDays(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(0)}d` : "--";
}

function formatOosCi(ci, robust) {
  if (!Array.isArray(ci) || ci.length < 2 || ci[0] == null || ci[1] == null) return "";
  const lo = Number(ci[0]).toFixed(2);
  const hi = Number(ci[1]).toFixed(2);
  const mark = robust ? "✓" : "≈0";
  const cls = robust ? "sv-ci robust" : "sv-ci weak";
  const title = robust
    ? "样本外90%自助CI排除0,该IC统计显著"
    : "样本外90%自助CI跨越0,未达统计显著——勿当作真实预测力";
  return `<div class="${cls}" title="${title}">[${lo}, ${hi}] ${mark}</div>`;
}

function formatRegimeFlag(rs) {
  if (!rs || typeof rs !== "object") return "";
  const up = rs.upMarket || {};
  const down = rs.downMarket || {};
  const fmtIc = (v) => (v == null ? "—" : Number(v).toFixed(2));
  const detail = `涨市 IC ${fmtIc(up.ic)}(n=${up.n ?? 0}) · 跌市 IC ${fmtIc(down.ic)}(n=${down.n ?? 0}) — 子样本小,探索性`;
  if (rs.signConsistent === false) {
    return ` <span class="sv-regime flip" title="预测方向在涨/跌市之间反转(稳健性红旗): ${detail}">⇅✗</span>`;
  }
  if (rs.signConsistent === true) {
    return ` <span class="sv-regime ok" title="预测方向跨涨/跌市一致: ${detail}">⇅✓</span>`;
  }
  return ` <span class="sv-regime muted" title="某一regime样本不足以判定: ${detail}">⇅?</span>`;
}

function signalValidationRowHtml(row, { showModule = false, showCluster = false } = {}) {
  const name = `${escapeHtml(row.labelCn || row.label || row.id || "--")}`;
  const moduleCell = showModule ? `<td>${escapeHtml(row.module || "--")}</td>` : "";
  const clusterCell = showCluster ? `<td>${row.clusterId ? escapeHtml(row.clusterId) : "--"}</td>` : "";
  const hitText = `${formatSignalRate(row.hitRateOos)} / ${formatSignalRate(row.baseRate)}`;
  const oosCell = `${formatSignalIc(row.oosIc3m)}${formatOosCi(row.oosCi3m, row.robust)}`;
  return `
    <tr class="${row.robust === false ? "sv-row-weak" : ""}">
      <td class="sv-name" title="${escapeHtml(row.label || "")}">${name}</td>
      ${moduleCell}
      <td>${formatSignalIc(row.ic3m)}</td>
      <td>${formatSignalIc(row.oosIc1m)}</td>
      <td class="sv-oos-cell">${oosCell}</td>
      <td>${hitText}</td>
      <td>${formatSignalLift(row.lift)}</td>
      <td>${formatSignalDays(row.leadTimeDays)}</td>
      <td>${signalValidationBadge(row.classification)}${formatRegimeFlag(row.regimeSplit)}</td>
      ${clusterCell}
    </tr>
  `;
}

function renderSignalValidation() {
  const panel = state.signalValidation || DEFAULT_DATA.signalValidation || {};
  const root = $("#signalValidationPanel");
  if (!root) return;
  const method = $("#signalValidationMethod");
  if (method) method.textContent = panel.available ? `weekly replay · OOS ${panel.oosSplitPct || 65}/${100 - (panel.oosSplitPct || 65)} split · ${panel.drawdownRule || ""}` : "weekly point-in-time replay · out-of-sample split";
  const coverage = $("#signalValidationCoverage");
  if (coverage) coverage.textContent = panel.available ? `${Number(panel.weeklyObservationCount) || 0} weekly obs · asOf ${panel.asOf || "--"}` : "waiting for public history";
  const read = $("#signalValidationRead");
  const compositesNode = $("#signalValidationComposites");
  const factorsNode = $("#signalValidationFactors");
  const clustersNode = $("#signalValidationClusters");
  if (!panel.available) {
    if (read) read.textContent = panel.reason || "暂无走出样本验证。";
    if (compositesNode) compositesNode.innerHTML = "";
    if (factorsNode) factorsNode.innerHTML = "";
    if (clustersNode) clustersNode.innerHTML = "";
    return;
  }
  const composites = Array.isArray(panel.composites) ? panel.composites : [];
  const factors = Array.isArray(panel.factors) ? panel.factors : [];
  const leadingCount = factors.filter((row) => row.classification === "leading").length;
  const coincidentCount = factors.filter((row) => row.classification === "coincident").length;
  const robustCount = factors.filter((row) => row.robust === true).length;
  const robustLeadingCount = factors.filter((row) => row.robust === true && row.classification === "leading").length;
  const regimeFlipCount = factors.filter((row) => row.regimeSplit && row.regimeSplit.signConsistent === false).length;
  if (read) {
    const summaryLead = panel.summary ? `${panel.summary} ` : "";
    read.textContent = `${summaryLead}IC为信号与SPX远期收益的秩相关(已按方向校正,正值=有预测力); 命中率与基准率均在走出样本段计算。[]内为样本外90%自助置信区间——跨0(标记≈0)表示该IC未达统计显著,不应当作真实预测力。⇅标记为跨涨/跌市方向一致性(子样本小,探索性),${regimeFlipCount}个因子方向在两种市态间反转(慎用)。当前${factors.length}个因子中${leadingCount}个领先、${coincidentCount}个同步; 仅${robustCount}个样本外CI排除0(其中${robustLeadingCount}个稳健领先)。`;
  }
  if (compositesNode) {
    const lens = panel.predictiveLens && typeof panel.predictiveLens === "object" ? panel.predictiveLens : {};
    const lensFactors = Array.isArray(lens.selectedFactors) ? lens.selectedFactors : [];
    // 诚实门控: 预测镜头若样本外 IC 非正(bhadialPredictive 复合行),标注"未验证·仅供诊断",不展示为可用信号
    const lensComposite = composites.find((row) => row && row.id === "bhadialPredictive");
    const lensOos = lensComposite ? Number(lensComposite.oosIc3m) : NaN;
    const lensValidated = Number.isFinite(lensOos) && lensOos > 0;
    const lensFactorsHtml = lensFactors.map((item) => `${escapeHtml(item.id || "")}(校准IC ${escapeHtml(String(item.calibrationIc ?? "--"))})`).join(" · ");
    const lensHtml = lens.available
      ? `<div class="sv-lens${lensValidated ? "" : " muted"}">预测镜头(领先因子) 最新 <strong>${escapeHtml(String(lens.latestScore ?? "--"))}</strong> · 成分: ${lensFactorsHtml}${lensValidated ? "" : ` · ⚠ 样本外未验证(OOS IC ${Number.isFinite(lensOos) ? lensOos.toFixed(2) : "--"})·仅供诊断,不作为信号`}</div>`
      : (lens.reason ? `<div class="sv-lens muted">${escapeHtml(lens.reason)}</div>` : "");
    compositesNode.innerHTML = composites.length ? `
      <h4 class="sv-heading">复合信号 · Composites</h4>
      <div class="sv-table-wrap">
        <table class="sv-table">
          <thead><tr><th>信号</th><th>IC 3M</th><th>OOS IC 1M</th><th>OOS IC 3M</th><th>命中/基准</th><th>Lift</th><th>提前量</th><th>分类</th></tr></thead>
          <tbody>${composites.map((row) => signalValidationRowHtml(row)).join("")}</tbody>
        </table>
      </div>
      ${lensHtml}
    ` : `<div class="empty-state compact">暂无复合信号验证</div>`;
  }
  if (factorsNode) {
    const sorted = factors.slice().sort((first, second) => Math.abs(Number(second.oosIc3m) || 0) - Math.abs(Number(first.oosIc3m) || 0));
    factorsNode.innerHTML = sorted.length ? `
      <h4 class="sv-heading">单因子 · Factors (按|OOS IC 3M|排序)</h4>
      <div class="sv-table-wrap">
        <table class="sv-table">
          <thead><tr><th>因子</th><th>模块</th><th>IC 3M</th><th>OOS IC 1M</th><th>OOS IC 3M</th><th>命中/基准</th><th>Lift</th><th>提前量</th><th>分类</th><th>簇</th></tr></thead>
          <tbody>${sorted.map((row) => signalValidationRowHtml(row, { showModule: true, showCluster: true })).join("")}</tbody>
        </table>
      </div>
    ` : `<div class="empty-state compact">暂无因子验证</div>`;
  }
  if (clustersNode) {
    const clusters = Array.isArray(panel.clusters) ? panel.clusters : [];
    clustersNode.innerHTML = clusters.length ? `
      <h4 class="sv-heading">冗余簇 · Redundancy Clusters (|corr|≥0.8, 簇内权重均摊)</h4>
      <div class="sv-clusters">${clusters.map((cluster) => `
        <div class="sv-cluster"><strong>${escapeHtml(cluster.id || "")}</strong><span>${(cluster.factorIds || []).map((id) => escapeHtml(id)).join(" · ")}</span></div>
      `).join("")}</div>
    ` : `<div class="empty-state compact">未检测到高相关因子簇</div>`;
  }
}

function spyWarningRobustNote(item) {
  if (!item || item.aggregateRobust == null) return "";
  const ci = Array.isArray(item.aggregateOosCi3m) && item.aggregateOosCi3m.length >= 2
    ? `[${Number(item.aggregateOosCi3m[0]).toFixed(2)}, ${Number(item.aggregateOosCi3m[1]).toFixed(2)}]`
    : "";
  if (item.aggregateRobust === false) {
    const sleeves = Array.isArray(item.robustSleeves) ? item.robustSleeves : [];
    const sleeveText = sleeves.length
      ? `; 但其稳健领先 sleeve: <strong>${sleeves.map((s) => escapeHtml(spyWarningSleeveLabel(s))).join(" · ")}</strong>(样本外CI排除0,可作前瞻依据)`
      : "";
    return `<p class="spy-warning-robust weak" title="聚合预警样本外90%自助CI跨0,未达统计显著——勿当作真实预测力 · aggregate not OOS-robust">⚠ 聚合预警样本外未达稳健${ci ? `(CI ${ci}跨0)` : "(CI跨0)"}${sleeveText}</p>`;
  }
  return `<p class="spy-warning-robust ok" title="聚合预警样本外CI排除0 · OOS-robust">✓ 聚合预警样本外稳健${ci ? `(CI ${ci})` : ""}</p>`;
}

function spyWarningSleeveLabel(key) {
  const map = {
    fundingStress: "融资压力",
    ratesCurveStress: "利率曲线压力",
    liquidityStress: "流动性压力",
    creditVolStress: "信用/波动压力",
    externalShock: "外部冲击",
  };
  return map[key] || key;
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
    ${spyWarningRobustNote(item)}
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
  const lpplHistoryButton = event.target.closest("[data-global-lppl-symbol], .expandGlobalLpplRiskHistory, #expandGlobalLpplRiskHistory");
  if (lpplHistoryButton) openGlobalLpplRiskHistoryModal(lpplHistoryButton.dataset.globalLpplSymbol || "");
});
$("#regionalMonitorTabs")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-region-key]");
  if (!button) return;
  selectedRegionKey = button.dataset.regionKey || null;
  renderRegionalMonitor();
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
