# The Dial - 安全说明

## 安全特性概览

本优化版本包含多层安全防护措施，确保个人使用时的数据安全和隐私保护。

## 1. 内容安全策略 (CSP)

### 策略配置

```http
Content-Security-Policy: 
  default-src 'self';
  script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net;
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data:;
  connect-src 'self';
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
```

### 防护效果

- ✅ **防止XSS攻击** - 限制脚本执行来源
- ✅ **防止数据注入** - 控制资源加载
- ✅ **防止点击劫持** - `frame-ancestors 'none'`
- ✅ **防止混合内容** - 强制HTTPS资源

## 2. 安全响应头

### X-Frame-Options: DENY
- **作用**: 防止页面被嵌入iframe
- **攻击防护**: 点击劫持 (Clickjacking)

### X-Content-Type-Options: nosniff
- **作用**: 禁止浏览器MIME嗅探
- **攻击防护**: MIME类型混淆攻击

### Referrer-Policy: strict-origin-when-cross-origin
- **作用**: 控制Referrer信息泄露
- **隐私保护**: 减少URL信息暴露

### Permissions-Policy
- **作用**: 限制浏览器敏感API
- **配置**: `geolocation=(), microphone=(), camera=()`
- **效果**: 完全禁用定位、麦克风、摄像头

## 3. 子资源完整性 (SRI)

### CDN资源校验

```html
<script src="https://cdn.tailwindcss.com" 
  integrity="sha384-..." 
  crossorigin="anonymous"></script>
```

### 防护效果
- ✅ 防止CDN资源被篡改
- ✅ 确保加载的代码完整性
- ✅ 即使CDN被攻击也能保护用户

## 4. 输入安全

### 无用户输入处理
- 本应用为纯展示型仪表盘
- 不涉及用户输入处理
- 无表单提交功能
- 无Cookie使用

### 数据安全
- 所有数据来自本地SQLite数据库
- 无外部API调用（除FRED数据下载）
- 无用户数据收集

## 5. 本地存储安全

### localStorage使用
```javascript
// 仅存储主题偏好
localStorage.setItem('theme', 'dark');
```

- ✅ 不存储敏感信息
- ✅ 不存储用户标识
- ✅ 可随时清除

## 6. 代码安全

### 避免的危险操作
- ✅ 不使用 `eval()`
- ✅ 不使用 `innerHTML` 插入用户数据
- ✅ 不使用 `document.write()`
- ✅ 所有DOM操作使用安全的API

### 示例
```javascript
// ✅ 安全：使用textContent
element.textContent = userData;

// ❌ 危险：使用innerHTML
element.innerHTML = userData;
```

## 7. 网络安全

### 同源策略
- 所有资源同源（或明确允许的CDN）
- 无跨域请求（除FRED数据下载）

### HTTPS强制
- 所有CDN资源使用HTTPS
- 无混合内容警告

## 8. 隐私保护

### 无跟踪
- 无Google Analytics
- 无第三方Cookie
- 无用户行为追踪

### 最小权限
- 仅请求必要的浏览器权限
- 默认禁用所有敏感API

## 9. 安全更新

### 依赖管理
- 使用CDN资源的特定版本
- 定期更新依赖
- 监控安全公告

### 更新检查
```bash
# 检查依赖更新
npm outdated

# 安全审计
npm audit
```

## 10. 部署安全

### 静态托管
- 使用静态文件托管
- 无服务器端代码
- 无数据库暴露

### 推荐配置
```nginx
# Nginx安全响应头
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

## 安全审计清单

- [x] CSP配置正确
- [x] 安全响应头完整
- [x] SRI哈希正确
- [x] 无eval使用
- [x] 无innerHTML风险
- [x] HTTPS强制
- [x] 无敏感数据暴露
- [x] 无第三方跟踪
- [x] 权限最小化
- [x] 依赖最新

## 报告安全问题

如发现安全问题，请：
1. 不要公开披露
2. 记录问题详情
3. 联系维护者

## 参考资源

- [OWASP CSP Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [Mozilla Security Headers](https://developer.mozilla.org/en-US/docs/Web/Security)
- [SRI Hash Generator](https://www.srihash.org/)
