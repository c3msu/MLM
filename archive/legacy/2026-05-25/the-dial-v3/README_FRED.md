# FRED API 配置与使用指南

## 📋 快速开始

### 方式一：CSV下载（推荐，无需API Key）

直接下载CSV文件，无需注册：
```bash
cd /mnt/okcomputer/output/the-dial-v3/backend
python3 -c "
from data_service import DataService
ds = DataService('macro_data.db', 'data')
ds.update_fred_data(use_api=False, days=1825)
"
```

### 方式二：FRED API（需要注册）

#### 1. 注册FRED账户
- 访问 https://fred.stlouisfed.org/
- 点击右上角 **"Register"** 注册
- 验证邮箱

#### 2. 申请API Key
- 访问 https://fredaccount.stlouisfed.org/apikey
- 点击 **"Request API Key"**
- 填写申请理由，提交

#### 3. 配置API Key
```bash
cd /mnt/okcomputer/output/the-dial-v3/backend

# 方式A: 使用交互式工具
python3 setup_fred.py

# 方式B: 直接保存
python3 config.py --save-key "your_api_key_here"

# 方式C: 环境变量
export FRED_API_KEY="your_api_key_here"
```

#### 4. 更新数据
```bash
python3 -c "
from data_service import DataService
ds = DataService('macro_data.db', 'data')
ds.update_fred_data(use_api=True, days=1825)
"
```

---

## 📁 配置文件

### 配置文件位置
```
/mnt/okcomputer/output/the-dial-v3/backend/
├── config.py              # 主配置文件
├── setup_fred.py          # 交互式配置工具
└── .fred_api_key          # API Key存储文件（自动创建）
```

### 配置项说明

**config.py** 包含：
- `FRED_API_KEY`: API密钥
- `FRED_SERIES`: 19个经济指标配置
- `UPDATE_SETTINGS`: 自动更新设置
- `MODULE_WEIGHTS`: 模块权重配置

---

## 📊 可用指标列表

| 模块 | 指标ID | 名称 | 频率 |
|------|--------|------|------|
| **流动性** | WALCL | 美联储资产负债表 | 周 |
| | RESBALNS | 银行准备金 | 周 |
| | WTREGEN | TGA账户 | 日 |
| | RRPONTSYD | ON RRP | 日 |
| | M2SL | M2货币供应 | 月 |
| **融资** | SOFR | SOFR利率 | 日 |
| | EFFR | 有效联邦基金利率 | 日 |
| | TEDRATE | TED利差 | 日 |
| **国债** | DGS2 | 2年国债收益率 | 日 |
| | DGS10 | 10年国债收益率 | 日 |
| | DGS30 | 30年国债收益率 | 日 |
| | T10Y2Y | 期限利差 | 日 |
| **利率** | FEDFUNDS | 联邦基金利率 | 月 |
| | MPRIME | Prime利率 | 月 |
| **信用** | BAMLC0A0CM | 投资级利差 | 日 |
| | BAMLH0A0HYM2 | 高收益利差 | 日 |
| **风险** | VIXCLS | VIX指数 | 日 |
| | DTWEXBGS | 美元指数 | 日 |
| **外部** | DEXUSEU | 欧元汇率 | 日 |

---

## 🔧 工具使用

### 交互式配置工具
```bash
python3 setup_fred.py
```

功能菜单：
1. **输入FRED API Key** - 保存API密钥
2. **查看当前API Key状态** - 检查配置状态
3. **查看FRED指标列表** - 显示所有可用指标
4. **测试API连接** - 验证API是否可用
5. **删除已保存的API Key** - 清除配置

### 验证配置
```bash
python3 config.py
```

---

## 📥 CSV下载链接

无需API Key，直接下载：

```
https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL
https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10
https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS
https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS
```

---

## ⚠️ 注意事项

1. **API限制**: 免费账户每分钟120次请求
2. **数据延迟**: 部分指标有1天延迟
3. **数据缺失**: 周末和节假日无数据
4. **单位注意**: 不同指标单位不同（B=十亿, %=百分比, bp=基点）

---

## 🔄 自动更新

启用自动更新（需要配置cron或systemd）：

```python
# 在config.py中设置
UPDATE_SETTINGS = {
    "auto_update": True,
    "update_time": "06:00",  # 每天早上6点
    "retention_days": 1825,  # 保留5年数据
}
```

---

## 📞 帮助

- FRED官网: https://fred.stlouisfed.org/
- API文档: https://fred.stlouisfed.org/docs/api/fred/
- 指标搜索: https://fred.stlouisfed.org/search
