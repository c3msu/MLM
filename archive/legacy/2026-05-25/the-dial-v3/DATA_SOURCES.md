# The Dial - 数据来源与获取方法文档

**最后更新**: 2026-02-22

---

## 数据真实性状态

| 数据类型 | 状态 | 说明 |
|---------|------|------|
| **S&P 500指数** | ✅ 真实数据 | 从Yahoo Finance获取，1,256条日线数据 |
| **宏观经济评分** | ✅ 真实数据 | 基于FRED指标计算，19个指标 |
| **模块评分** | ✅ 真实数据 | 基于FRED指标计算，7个模块 |
| **因子指标** | ✅ 真实数据 | 从FRED下载，115,595条记录 |

---

## 一、S&P 500数据

### 1.1 数据来源
- **来源**: Yahoo Finance
- **代码**: ^GSPC (S&P 500 Index)
- **获取时间**: 2021-02-22 至 2026-02-20
- **数据条数**: 1,256条日线数据

### 1.2 数据字段
```
date: 日期 (YYYY-MM-DD)
open: 开盘价
high: 最高价
low: 最低价
close: 收盘价
volume: 成交量
normalized: 归一化值 (0-100)
```

### 1.3 数据范围
- **起始日期**: 2021-02-22 (收盘价: 3,876.50)
- **结束日期**: 2026-02-20 (收盘价: 6,909.51)
- **涨幅**: +78.2% (约5年)

---

## 二、FRED数据

### 2.1 数据来源
- **来源**: FRED (Federal Reserve Economic Data)
- **获取方式**: CSV下载 (无需API Key)
- **下载URL**: `https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}`

### 2.2 已下载指标 (19个)

| 模块 | 指标ID | 名称 | 频率 | 记录数 |
|------|--------|------|------|--------|
| **流动性** | WALCL | 美联储资产负债表 | 周 | 1,210 |
| | RESBALNS | 银行准备金 | 周 | 848 |
| | WTREGEN | TGA账户 | 日 | 1,210 |
| | RRPONTSYD | ON RRP | 日 | 3,184 |
| | M2SL | M2货币供应 | 月 | 804 |
| **融资** | SOFR | SOFR利率 | 日 | 1,968 |
| | EFFR | 有效联邦基金利率 | 日 | 6,434 |
| | TEDRATE | TED利差 | 日 | 8,853 |
| **国债** | DGS2 | 2年国债收益率 | 日 | 12,425 |
| | DGS10 | 10年国债收益率 | 日 | 16,017 |
| | DGS30 | 30年国债收益率 | 日 | 12,247 |
| | T10Y2Y | 期限利差 | 日 | 12,426 |
| **利率** | FEDFUNDS | 联邦基金利率 | 月 | 859 |
| | MPRIME | Prime利率 | 月 | 925 |
| **信用** | BAMLC0A0CM | 投资级利差 | 日 | 7,607 |
| | BAMLH0A0HYM2 | 高收益利差 | 日 | 7,608 |
| **风险** | VIXCLS | VIX指数 | 日 | 9,127 |
| | DTWEXBGS | 美元指数 | 日 | 5,043 |
| **外部** | DEXUSEU | 欧元汇率 | 日 | 6,800 |

**总计**: 115,595条记录

### 2.3 最新数据示例 (2026-02-19)

| 指标 | 最新值 |
|------|--------|
| 10年国债收益率 (DGS10) | 4.08% |
| VIX指数 (VIXCLS) | 20.23 |
| 联邦基金利率 (FEDFUNDS) | 3.64% |
| 投资级利差 (BAMLC0A0CM) | 0.79% |
| 高收益利差 (BAMLH0A0HYM2) | 2.88% |

---

## 三、评分计算方法

### 3.1 计算逻辑

```python
def calculate_module_score(indicators):
    scores = []
    for indicator in indicators:
        # 获取当前值和历史数据
        current = get_latest_value(indicator)
        history = get_historical_values(indicator, days=1825)
        
        # 计算百分位
        percentile = calculate_percentile(current, history)
        
        # 对于"越低越好"的指标，反转百分位
        if indicator in good_when_low:
            score = 100 - percentile
        else:
            score = percentile
        
        scores.append(score)
    
    # 模块评分为各指标平均分
    return average(scores)
```

### 3.2 "越低越好"指标
- SOFR, EFFR, TEDRATE (利率)
- DGS2, DGS10, DGS30 (国债收益率)
- FEDFUNDS, MPRIME (政策利率)
- BAMLC0A0CM, BAMLH0A0HYM2 (信用利差)
- VIXCLS (波动率)

### 3.3 当前评分 (2026-02-22)

| 模块 | 评分 | 状态 | 基于指标数 |
|------|------|------|-----------|
| **信用** | 93.3 | 🟢 支持性 | 2 |
| **外部** | 91.3 | 🟢 支持性 | 1 |
| **流动性** | 76.9 | 🟢 支持性 | 5 |
| **融资** | 61.5 | 🟢 支持性 | 3 |
| **利率** | 50.0 | 🟡 中性 | 2 |
| **国债** | 42.1 | 🔴 限制性 | 4 |
| **风险** | 39.5 | 🔴 限制性 | 2 |
| **整体** | **64.9** | **🟢 支持性** | **19** |

---

## 四、数据更新方法

### 4.1 更新FRED数据

```bash
cd /mnt/okcomputer/output/the-dial-v3/backend
python3 -c "
from data_service import DataService
ds = DataService('macro_data.db', 'data')
ds.update_fred_data(use_api=False, days=1825)
"
```

### 4.2 重新计算评分

```bash
cd /mnt/okcomputer/output/the-dial-v3/backend
python3 -c "
from data_service import DataService
ds = DataService('macro_data.db', 'data')
ds.update_real_scores()
"
```

### 4.3 一键更新

```bash
cd /mnt/okcomputer/output/the-dial-v3/backend
python3 -c "
from data_service import DataService
ds = DataService('macro_data.db', 'data')
ds.update_fred_data(use_api=False, days=1825)
ds.update_real_scores()
"
```

---

## 五、文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 数据库 | `backend/macro_data.db` | SQLite数据库 |
| 数据服务 | `backend/data_service.py` | 数据获取和评分计算 |
| 配置 | `backend/config.py` | FRED指标配置 |
| 前端 | `frontend/dashboard.html` | 仪表盘展示 |
| 前端 | `frontend/index.html` | 首页展示 |

---

## 六、网站地址

**Dashboard**: https://6s4i23zkrdhb4.ok.kimi.link/dashboard.html

---

## 七、数据质量保证

- ✅ 所有数据来自权威来源 (FRED/Yahoo Finance)
- ✅ 评分基于真实指标计算，非模拟
- ✅ 历史数据可追溯5年
- ✅ 每日可自动更新
