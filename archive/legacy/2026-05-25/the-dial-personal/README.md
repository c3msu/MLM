# The Dial - 个人宏观经济仪表盘

个人使用的宏观经济监测工具，基于FRED数据，本地SQLite存储。

## 功能特点

- 📊 **7大分析模块**：流动性、融资、国债、利率、信用、风险、外部
- 📈 **47个宏观因子**：全面覆盖关键经济指标
- 💯 **经济环境评分**：0-100分综合评分系统
- 🏠 **本地数据存储**：SQLite数据库，数据完全掌控
- 📥 **CSV数据导入**：直接从FRED下载，无需API密钥

## 快速开始

### 1. 安装依赖
```bash
pip install pandas numpy
```

### 2. 下载数据
```bash
bash scripts/download_data.sh
```

### 3. 导入数据
```bash
python scripts/import_data.py
```

### 4. 查看仪表盘
在浏览器中打开 `index.html` 或 `dashboard.html`

## 数据更新

```bash
# 重新下载并导入
bash scripts/download_data.sh
python scripts/import_data.py
```

## 项目结构

```
the-dial-personal/
├── index.html              # 首页
├── dashboard.html          # 仪表盘
├── module-*.html           # 模块详情页（7个）
├── scripts/
│   ├── download_data.sh    # 数据下载脚本
│   └── import_data.py      # 数据导入脚本
├── data/                   # CSV数据文件
└── macro_data.db           # SQLite数据库
```

## 核心指标

| 模块 | 指标代码 | 说明 |
|------|----------|------|
| 流动性 | WALCL | 美联储资产负债表 |
| 流动性 | RESBALNS | 银行准备金 |
| 融资 | SOFR | SOFR利率 |
| 融资 | TEDRATE | TED利差 |
| 国债 | DGS10 | 10年国债收益率 |
| 国债 | T10Y2Y | 期限利差 |
| 利率 | FEDFUNDS | 联邦基金利率 |
| 信用 | BAMLC0A0CM | 投资级利差 |
| 风险 | VIXCLS | VIX指数 |
| 外部 | DXY | 美元指数 |

## 评分算法

- **百分位评分**：每个指标按5年滚动历史归一化为0-100
- **模块评分**：模块内所有指标的平均百分位
- **总体评分**：所有模块评分的加权平均

## 评分标准

- **≥55分**：支持性环境（绿色）
- **45-55分**：中性环境（黄色）
- **≤45分**：限制性环境（红色）

## 数据来源

- **FRED**: https://fred.stlouisfed.org/
- **Federal Reserve Bank of St. Louis**

## 许可证

个人使用，仅用于教育和研究目的。
