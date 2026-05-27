# The Dial - 修改说明

## 主要修改内容

### 1. 去掉定价和注册功能 ✅

**已删除的页面：**
- `login.html` - 登录页面
- `signup.html` - 注册页面
- `pricing.html` - 定价页面
- `profile.html` - 用户资料页面

**已删除的功能：**
- 用户认证系统
- 登录/注册按钮
- 定价方案展示
- Pro/Free版本区分
- 支付相关功能

### 2. FRED数据获取方案 ✅

**实现方式：**
- **CSV直接下载**：从FRED官网直接下载CSV文件，无需API密钥
- **自动下载脚本**：`scripts/download_data.sh` 使用curl批量下载
- **数据导入脚本**：`scripts/import_data.py` 自动导入CSV到SQLite

**使用方法：**
```bash
# 1. 自动下载数据
bash scripts/download_data.sh

# 2. 导入到SQLite
python scripts/import_data.py
```

**支持的指标（20个核心指标）：**

| 模块 | 指标代码 | 说明 |
|------|----------|------|
| 流动性 | WALCL | 美联储资产负债表 |
| 流动性 | RESBALNS | 银行准备金 |
| 流动性 | WTREGEN | TGA账户 |
| 流动性 | RRPONTSYD | ON RRP |
| 流动性 | M2SL | M2货币供应 |
| 融资 | SOFR | SOFR利率 |
| 融资 | EFFR | 有效联邦基金利率 |
| 融资 | TEDRATE | TED利差 |
| 国债 | DGS2 | 2年国债收益率 |
| 国债 | DGS10 | 10年国债收益率 |
| 国债 | DGS30 | 30年国债收益率 |
| 国债 | T10Y2Y | 期限利差 |
| 利率 | FEDFUNDS | 联邦基金利率 |
| 利率 | MPRIME | Prime利率 |
| 信用 | BAMLC0A0CM | 投资级利差 |
| 信用 | BAMLH0A0HYM2 | 高收益利差 |
| 风险 | VIXCLS | VIX指数 |
| 风险 | DXY | 美元指数 |
| 外部 | DEXUSEU | 欧元汇率 |
| 外部 | GACDISA | 全球PMI |

### 3. SQLite数据库存储 ✅

**数据库结构：**

```sql
-- 指标数据表
CREATE TABLE indicators (
    series_id TEXT,      -- 指标代码
    date TEXT,           -- 日期
    value REAL,          -- 数值
    module TEXT,         -- 所属模块
    name TEXT,           -- 指标名称
    PRIMARY KEY (series_id, date)
);

-- 模块评分表
CREATE TABLE module_scores (
    module TEXT,         -- 模块名称
    date TEXT,           -- 日期
    score REAL,          -- 评分(0-100)
    PRIMARY KEY (module, date)
);

-- 总体评分表
CREATE TABLE overall_scores (
    date TEXT PRIMARY KEY,
    score REAL           -- 总体评分(0-100)
);
```

**数据库文件：** `macro_data.db`（自动生成）

### 4. 补齐过去两年历史数据 ✅

**数据获取方式：**
- 从FRED下载完整历史数据（通常包含5-10年）
- 自动导入所有历史数据到SQLite
- 支持增量更新（只导入新数据）

**历史数据图表：**
- 每个模块页面显示24个月历史趋势
- 仪表盘显示30天总体评分趋势

### 5. 更新后的网站结构 ✅

```
the-dial-personal/
├── index.html                 # 首页（简化版）
├── dashboard.html             # 仪表盘
├── module-liquidity.html      # 流动性模块
├── module-funding.html        # 融资模块
├── module-treasury.html       # 国债模块
├── module-rates.html          # 利率模块
├── module-credit.html         # 信用模块
├── module-risk.html           # 风险模块
├── module-external.html       # 外部模块
├── scripts/
│   ├── download_data.sh       # 数据下载脚本
│   ├── import_data.py         # 数据导入脚本
│   └── README.md              # 脚本说明
├── data/                      # CSV数据目录
│   ├── DGS10.csv
│   ├── VIXCLS.csv
│   └── ...
├── macro_data.db              # SQLite数据库
└── README.md                  # 项目说明
```

## 数据获取流程

### 方式一：自动下载（推荐）

```bash
# 1. 进入项目目录
cd the-dial-personal

# 2. 运行下载脚本
bash scripts/download_data.sh

# 3. 导入数据到SQLite
python scripts/import_data.py

# 4. 打开仪表盘查看
open dashboard.html
```

### 方式二：手动下载

1. 访问 https://fred.stlouisfed.org/
2. 搜索指标代码（如：DGS10, VIXCLS）
3. 点击 "Download" → "CSV"
4. 保存到 `data/` 目录
5. 运行 `python scripts/import_data.py`

## 评分算法说明

### 1. 百分位评分

每个指标按其5年滚动历史归一化为0-100百分位：

```python
def calculate_percentile(current_value, historical_values):
    """计算当前值在历史数据中的百分位"""
    percentile = (historical_values < current_value).mean() * 100
    return round(percentile, 1)
```

### 2. 模块评分

模块内所有指标百分位的平均值：

```python
def calculate_module_score(indicators):
    """计算模块评分"""
    percentiles = [ind.percentile for ind in indicators]
    return round(mean(percentiles), 1)
```

### 3. 总体评分

所有模块评分的加权平均：

```python
def calculate_overall_score(module_scores):
    """计算总体评分"""
    return round(mean(module_scores), 1)
```

### 4. 评分标准

- **≥55分**：支持性环境（绿色）- 有利于经济增长
- **45-55分**：中性环境（黄色）- 正常波动范围
- **≤45分**：限制性环境（红色）- 可能抑制经济

## 界面截图

### 首页
- Hero区域：经济环境评分仪表盘
- 统计卡片：47因子/7模块/5年窗口/每日更新
- 功能特性：6大功能介绍
- 模块预览：7大模块卡片
- 数据管理：CSV下载和SQLite存储说明

### 仪表盘
- 总体评分仪表盘（SVG动画）
- 关键指标卡片（健康模块/临界模块/百分位/数据覆盖）
- 历史趋势图表（Chart.js）
- 模块网格（带进度条）

### 模块详情页
- 模块评分和关键指标
- 24个月历史趋势图
- 因子详情表格（当前值/变化/百分位/状态）

## 技术栈

- **前端**：HTML5 + Tailwind CSS + Chart.js + Lucide Icons
- **数据**：Python 3 + Pandas + SQLite3
- **数据源**：FRED (Federal Reserve Economic Data)
- **部署**：静态网站托管

## 后续优化建议

### 1. 后端服务（可选）
如果需要实时数据更新，可以添加轻量级后端：

```python
# Flask后端示例
from flask import Flask, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/api/scores')
def get_scores():
    conn = sqlite3.connect('macro_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM overall_scores ORDER BY date DESC LIMIT 1')
    data = cursor.fetchone()
    conn.close()
    return jsonify(data)
```

### 2. 定时更新
使用cron定时任务自动更新数据：

```bash
# 每天凌晨3点更新数据
0 3 * * * cd /path/to/the-dial && bash scripts/download_data.sh && python scripts/import_data.py
```

### 3. 数据备份
定期备份SQLite数据库：

```bash
# 备份数据库
cp macro_data.db backup/macro_data_$(date +%Y%m%d).db
```

## 许可证

个人使用，仅用于教育和研究目的。

## 免责声明

本工具仅用于宏观经济研究，不构成任何投资建议。
