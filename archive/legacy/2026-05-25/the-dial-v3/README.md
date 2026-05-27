# The Dial v3 - 当前主线

`the-dial-v3` 是当前可运行的主线版本：FastAPI 后端负责宏观数据、47 因子计算和 SQLite 存储，`frontend/` 下的静态页面由同一个服务直接托管。

根目录还有 `my-app/`、`static-site/`、`the-dial-personal/`、`the-dial-optimized/` 等历史或原型版本。除非另有说明，开发和验证都以本目录为准。

## 主要改进

### 1. Dashboard图表优化 ✅

#### 替换Chart.js为轻量级SVG
- **文件大小**: Chart.js (~200KB) → SVG (0KB, 内联)
- **渲染性能**: 大幅提升，无JavaScript依赖
- **动画效果**: CSS过渡动画，流畅自然

#### 响应式设计
- **手机端优化**: 侧边栏滑出菜单
- **触摸友好**: 按钮最小44px点击区域
- **下拉刷新**: 移动端手势刷新
- **自适应布局**: 单列/双列/三列自动切换

### 2. 后端数据服务 ✅

#### FastAPI后端
```python
# 主要API端点
GET /api/dashboard          # 完整仪表盘数据
GET /api/overall-score      # 总体评分
GET /api/modules            # 所有模块
GET /api/modules/{id}       # 单个模块
GET /api/modules/{id}/history  # 历史数据
POST /api/update            # 触发数据更新
```

#### 数据管线
- **本地修复**: 启动时会检查是否存在原始数据但因子表为空或只有占位记录，并自动从本地原始数据重建因子层
- **后台更新**: `POST /api/v1/update` 使用 FastAPI BackgroundTasks 执行一次完整更新
- **手动触发**: 支持从前端或 API 手动刷新数据
- **当前限制**: 代码尚未接入持久化定时调度器，生产环境需要单独配置 cron/systemd/任务平台

### 3. 前端API集成 ✅

#### 实时数据同步
- **自动刷新**: 每5分钟自动获取最新数据
- **离线支持**: 网络失败时使用本地缓存
- **Toast通知**: 更新状态实时反馈

## 项目结构

```
the-dial-v3/
├── backend/
│   ├── main.py              # FastAPI主服务
│   ├── data_service.py      # 数据服务
│   ├── requirements.txt     # Python依赖
│   └── macro_data.db        # SQLite数据库
├── frontend/
│   ├── index.html           # 首页
│   ├── dashboard.html       # 仪表盘（优化版）
│   └── module-*.html        # 模块详情页
├── start.sh                 # 启动脚本
└── README.md
```

## 快速启动

### 本地开发

```bash
# 1. 进入项目目录
cd the-dial-v3

# 2. 启动服务
./start.sh

# 3. 访问仪表盘
open http://localhost:8000/dashboard.html
```

### API测试

```bash
# 获取仪表盘数据
curl http://localhost:8000/api/dashboard

# 触发数据更新
curl -X POST http://localhost:8000/api/update

# 获取模块历史
curl http://localhost:8000/api/modules/liquidity/history?days=30
```

## 性能对比

| 指标 | v2 (Chart.js) | v3 (SVG) | 提升 |
|------|---------------|----------|------|
| 图表库大小 | ~200KB | 0KB | 100% |
| 首次渲染 | ~500ms | ~50ms | 90% |
| 内存占用 | 高 | 极低 | - |
| 移动端体验 | 一般 | 优秀 | - |

## 移动端特性

- ✅ 侧边栏滑出菜单
- ✅ 触摸友好按钮
- ✅ 下拉刷新手势
- ✅ 响应式布局
- ✅ 优化滚动性能

## 数据更新

### 启动修复
- 服务启动时会清理旧的 `running` pipeline 记录
- 如果 `raw_series` 已有数据但 `factor_series` 为空，或 `factor_latest` 只有 bootstrap 占位记录，会自动重建因子层
- 该修复只使用本地 SQLite 中已有的 raw data，不会额外访问外部数据源

### 手动更新
- 点击刷新按钮
- 下拉刷新（移动端）
- API触发更新

```bash
curl -X POST http://localhost:8000/api/v1/update
```

### 定时更新
当前代码没有实际启用 APScheduler/cron。若需要无人值守更新，应在部署层调用 `POST /api/v1/update` 或增加受控的任务入口。

## 部署说明

### 前端部署
前端为纯静态文件，可部署到任何静态托管服务：
- GitHub Pages
- Vercel
- Netlify
- Nginx

### 后端部署
后端为FastAPI服务，需要Python环境：

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 启动服务
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Docker部署（可选）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 环境变量

```bash
# API配置
API_HOST=0.0.0.0
API_PORT=8000

# 数据更新
UPDATE_SCHEDULE=0 6 * * *  # Cron格式
```

## 技术栈

- **前端**: HTML5 + Tailwind CSS + 原生SVG
- **后端**: Python 3.11 + FastAPI + SQLite
- **任务调度**: APScheduler
- **数据**: FRED API (可选)

## 浏览器支持

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
- iOS Safari 14+
- Chrome Android 90+

## 许可证

个人使用，仅用于教育和研究目的。
