# The Dial v3：47因子真实数据抓取与评分实现方案（后端优先）

## 1. 目标与范围

### 目标
在 `the-dial-v3` 中完成 47 因子（30 scored + 17 display-only）的真实数据抓取、计算、入库、评分与 API 输出，替换当前 mock/随机逻辑。

### 范围
- ✅ 后端数据与评分管线（本轮重点）
- ✅ `/api/v1` 对齐与旧接口兼容
- ✅ Dashboard 最小去 mock（仅最小改造）
- ❌ 不做注册/报价/付费功能恢复
- ❌ 不做全前端页面重构（模块页深度联动留后续）

---

## 2. 已确认决策（锁定）

1. 目标目录：`the-dial-v3`
2. 因子口径：对齐 bhadial 线上 47 因子结构
3. 数据源策略：多源免 Key（FRED + CBOE CSV + Stooq）
4. 范围边界：后端优先，前端最小必要适配

---

## 3. 现状问题基线（实施前）

1. 指标配置数量不足：`FRED_SERIES` 只有 19 条
2. 更新流程仍是 mock：`update_all_data()` 调用 `generate_mock_data()`
3. 模块因子接口返回随机值：`get_module_indicators()`
4. Dashboard 强制 mock：`fetchDashboard()` 不拉真实后端

---

## 4. 实施架构总览

构建“四层架构”：

1. **因子定义层（Factor Catalog）**  
   47 因子的唯一配置真源
2. **原始数据层（Raw Sources）**  
   FRED/CBOE/Stooq 拉取并标准化
3. **因子计算层（Factor Engine）**  
   公式计算、百分位、分数、状态
4. **服务输出层（API）**  
   `/api/v1` 统一输出 + 旧路由兼容

---

## 5. 代码改造方案（按顺序）

## Phase A：统一因子目录（47条）

### 新增
- `backend/factor_catalog.py`

### 内容
- `FactorDef` 数据结构：
  - `id/module/name/name_cn/display_only/weight/direction/frequency/formula_id/deps/format_hint`
- 47条因子定义
- 断言：
  - 总数 = 47
  - scored = 30
  - display-only = 17
  - 模块数固定：8/12/8/5/4/5/5

---

## Phase B：多源采集层

### 新增
- `backend/data_sources.py`

### 函数
- `fetch_fred_csv(series_id)`
- `fetch_cboe_history(symbol)`（VIX/VXV/OVX）
- `fetch_stooq_daily(symbol)`（SPY/TLT/IWM/KRE/LQD/IEF/HYG/IEI）

### 采集要求
- 超时、重试、空值处理
- 日期标准化（YYYY-MM-DD）
- 统一返回结构：`[{date, value, source, symbol}]`

---

## Phase C：数据库扩展（不破坏旧表）

### 修改
- `backend/data_service.py` -> `init_database()`

### 新表
- `raw_series(source, symbol, date, value, frequency, fetched_at, status, PK(source,symbol,date))`
- `factor_series(factor_id, module_id, date, raw_value, percentile_5y, score, color, data_status, display_only, PK(factor_id,date))`
- `factor_latest(factor_id PK, module_id, date, raw_value, percentile_5y, score, color, data_status, updated_at)`
- `pipeline_runs(run_id, started_at, finished_at, status, message)`

---

## Phase D：47因子计算与评分引擎

### 修改
- `backend/data_service.py`

### 新增能力
- 原始序列读取与对齐
- 因子公式计算（直接值、利差、滚动变化、波动率、相对收益、偏离度）
- 5年滚动百分位（默认 1825天）
- 方向映射：
  - `higher_better => score = pctl`
  - `lower_better => score = 100 - pctl`
  - `neutral => score = 100 - 2*abs(pctl-50)`
- `data_status`：
  - `current/stale/missing`
- 模块分：
  - 仅 scored 因子按权重加权
- 总分：
  - 按模块权重聚合

---

## Phase E：更新流程切换到真实管线

### 修改
- `backend/data_service.py`

### 目标流程
- `update_all_data()` 改为：
  1. 拉取三源数据 -> `raw_series`
  2. 计算全部因子 -> `factor_series/factor_latest`
  3. 计算模块与总体评分 -> `module_scores/overall_scores`
  4. 记录 `pipeline_runs`

### 禁止
- 更新主链路中继续使用 `generate_mock_data()`

---

## Phase F：API 对齐 `/api/v1` 并兼容旧接口

### 修改
- `backend/main.py`
- `backend/data_service.py`

### 新/改接口
- `GET /api/v1/dashboard`
- `GET /api/v1/modules`
- `GET /api/v1/modules/{module_id}`
- `GET /api/v1/modules/{module_id}/history`
- `GET /api/v1/modules/{module_id}/factors/{factor_id}/history`
- `GET /api/v1/modules/{module_id}/factors/{factor_id}/distribution`
- `GET /api/v1/dashboard/drivers?period=7d|30d|90d`
- `POST /api/v1/update`

### 兼容
- 保留 `/api/*` 旧路由，内部复用 v1 服务层

### 关键修复
- `get_module_indicators()` 不再随机，改读 `factor_latest`

---

## Phase G：前端最小去 mock（仅 Dashboard）

### 修改
- `frontend/dashboard.html`

### 处理
- `fetchDashboard()` 改为优先请求 `${API_BASE}/dashboard`
- 请求失败才 fallback mock
- 删除“Always use mock data”强制路径
- 保留 mock 仅作兜底

---

## 6. 公开接口/类型变更

## 模块对象新增/稳定字段
- `factors_count`
- `scored_factors_count`
- `last_updated`

## 因子对象稳定字段
- `id,name,name_cn,display_only,weight,direction,frequency`
- `latest:{date,value,percentile,color,data_status}`

## dashboard 新鲜度
- `data_freshness:{overall_status,last_fred_sync,last_alt_sync,stale_factors}`

---

## 7. 测试与验收

## 新增测试
- `backend/tests/test_factor_catalog.py`
- `backend/tests/test_formulas.py`
- `backend/tests/test_scoring.py`
- `backend/tests/test_api_contract.py`

## 必过项
1. 47因子全部可返回 latest（允许 stale/missing，但不能消失）
2. scored=30，display-only=17
3. `/api/v1/dashboard` 与 `/api/v1/modules/{id}` 字段完整、类型稳定
4. 更新任务执行后，`module_scores/overall_scores` 均有当日记录
5. Dashboard 实际走 API 数据（网络断开时才 fallback）

## 对标检查
- 与线上 API 对比结构与统计：
  - 模块数量
  - 每模块 factors_count / scored_factors_count
  - data_freshness 结构
- 数值允许偏差，但口径/字段不漂移

---

## 8. 风险与回退

## 风险
- 非FRED源偶发限流/不可用
- 部分序列频率差异造成对齐复杂
- 代理口径（如 DXY）与原站存在轻微偏移

## 回退策略
- source 级 fallback（单源失败不阻断全量）
- 记录 stale/missing，不造假
- 保留 mock 仅前端兜底，不进入评分主链路

---

## 9. 里程碑与交付物

## M1（基础）
- 因子目录 + 三源采集 + DB扩展

## M2（核心）
- 因子计算 + 百分位 + 模块/总分 + 更新管线

## M3（服务）
- `/api/v1` 完整输出 + 旧路由兼容

## M4（验证）
- 测试通过 + dashboard 最小去mock + 对标报告

## 文档交付
- `docs/REAL_DATA_SOURCE_MAP.md`
- `docs/REPLICATION_GAP_REPORT.md`

---

## 10. 默认参数与假设

- 时区：`America/New_York`
- 统计窗口：5年（1825天）
- 更新频率：每日（默认 06:00）
- DXY 默认采用免Key可稳定口径（可后续切换）
- 本轮不处理登录/定价相关功能
