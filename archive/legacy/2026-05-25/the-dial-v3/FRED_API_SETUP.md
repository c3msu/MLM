# FRED API 设置指南

## 什么是FRED?

FRED (Federal Reserve Economic Data) 是美联储圣路易斯分行提供的免费经济数据平台，包含超过80万个美国经济时间序列数据。

- **官网**: https://fred.stlouisfed.org/
- **API文档**: https://fred.stlouisfed.org/docs/api/fred/

---

## 获取FRED API Key的步骤

### 步骤1: 注册FRED账户

1. 访问 https://fred.stlouisfed.org/
2. 点击右上角的 **"Sign In"** 或 **"Register"**
3. 填写注册信息：
   - Email地址
   - 密码
   - 姓名
   - 组织（可选，可填"Personal"）
4. 点击 **"Create Account"**
5. 查收验证邮件并点击链接激活账户

### 步骤2: 申请API Key

1. 登录FRED账户
2. 访问 https://fred.stlouisfis.org/docs/api/api_key.html
3. 或直接访问: https://fredaccount.stlouisfed.org/apikey
4. 点击 **"Request API Key"**
5. 填写申请理由（例如）：
   ```
   I am building a personal macroeconomic monitoring dashboard 
   for educational purposes. I need access to FRED data to 
   analyze economic indicators like Fed balance sheet, 
   interest rates, and market volatility indices.
   ```
6. 点击 **"Submit"**
7. API Key会立即显示，请**立即复制保存**

### 步骤3: 保存API Key

#### 方法1: 使用环境变量（推荐）

**Linux/Mac:**
```bash
export FRED_API_KEY="your_api_key_here"
```

**Windows (PowerShell):**
```powershell
$env:FRED_API_KEY="your_api_key_here"
```

**Windows (CMD):**
```cmd
set FRED_API_KEY=your_api_key_here
```

#### 方法2: 使用配置文件

```bash
cd /mnt/okcomputer/output/the-dial-v3/backend
python config.py --save-key "your_api_key_here"
```

这会在 `backend/.fred_api_key` 文件中保存API Key。

---

## 验证API Key

### 方法1: 使用curl测试

```bash
curl "https://api.stlouisfed.org/fred/series/observations?series_id=GDPC1&api_key=YOUR_API_KEY&file_type=json&limit=1"
```

### 方法2: 使用Python测试

```python
import requests

api_key = "YOUR_API_KEY"
url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "GDPC1",
    "api_key": api_key,
    "file_type": "json",
    "limit": 1
}

response = requests.get(url, params=params)
data = response.json()
print(data)
```

### 方法3: 使用本项目的验证脚本

```bash
cd /mnt/okcomputer/output/the-dial-v3/backend
python config.py
```

---

## 常用FRED Series ID

| 指标 | Series ID | 说明 |
|------|-----------|------|
| 美联储资产负债表 | WALCL | 周数据，百万美元 |
| 银行准备金 | RESBALNS | 周数据，百万美元 |
| TGA账户 | WTREGEN | 日数据，十亿美元 |
| ON RRP | RRPONTSYD | 日数据，十亿美元 |
| M2货币供应 | M2SL | 月数据，十亿美元 |
| SOFR利率 | SOFR | 日数据，百分比 |
| 有效联邦基金利率 | EFFR | 日数据，百分比 |
| TED利差 | TEDRATE | 日数据，百分比 |
| 2年国债收益率 | DGS2 | 日数据，百分比 |
| 10年国债收益率 | DGS10 | 日数据，百分比 |
| 30年国债收益率 | DGS30 | 日数据，百分比 |
| 期限利差 | T10Y2Y | 日数据，百分比 |
| 联邦基金利率 | FEDFUNDS | 月数据，百分比 |
| VIX指数 | VIXCLS | 日数据，指数 |
| 美元指数 | DTWEXBGS | 日数据，指数 |

---

## API使用限制

- **免费账户**: 每分钟120次请求
- **每日限制**: 无明确限制
- **数据更新**: 实时或延迟（取决于数据源）

---

## 不注册API的替代方案

如果不想注册API，可以使用CSV下载方式：

```
https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}
```

例如：
- https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL
- https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10

---

## 下一步

获取API Key后，运行以下命令开始下载真实数据：

```bash
cd /mnt/okcomputer/output/the-dial-v3/backend
export FRED_API_KEY="your_api_key"
python data_service.py --update-fred
```
