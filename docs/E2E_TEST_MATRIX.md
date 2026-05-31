# E2E Test Matrix — iCoDer Medical Coding Agent

> 17条业务流程 × 页面/API/角色 的完整可追溯矩阵。
> 状态: ✅ 可自动化 | ⚠️ 部分可自动化 (需 mock/seed data) | ❌ 不可自动化

---

## 1. 总览矩阵

| # | 业务流程 | 目标页面 | API 依赖 | Auth | 可自动化 | 优先级 |
|---|---------|---------|---------|------|---------|--------|
| 01 | 列表加载 | CodingWorkbenchPage | GET /encounters | Bearer | ✅ | P0 |
| 02 | 过滤/搜索 | CodingWorkbenchPage | GET /encounters?status= | Bearer | ✅ | P0 |
| 03 | 分页 | GoldCasesPage | GET /gold-cases?page=&page_size= | Bearer | ⚠️ 需数据 | P0 |
| 04 | 新建对象 | GoldCasesPage | POST /gold-cases | Bearer | ✅ | P0 |
| 05 | 新建校验 | GoldCasesPage | POST /gold-cases (422) | Bearer | ⚠️ 无前端校验 | P1 |
| 06 | 删除对象 | GoldCasesPage | DELETE /gold-cases/{id} | Bearer | ⚠️ 需数据 | P1 |
| 07 | 详情查看 | CodingWorkbenchPage | GET /encounters/{id} | Bearer | ⚠️ 需数据 | P0 |
| 08 | 编辑对象 | GoldCasesPage | (create = overwrite) | Bearer | ⚠️ 无编辑 API | P2 |
| 09 | 提交审核 | CodingWorkbenchPage | POST /reviews (LLM) | Bearer | ⚠️ 耗时/费用 | P1 |
| 10 | 状态变更 | SettingsPage | (前端 state toggle) | Bearer | ✅ | P1 |
| 11 | 权限-按钮不可见 | (所有受保护页面) | — | 无 | ❌ 无角色 UI | P2 |
| 12 | 权限-URL 被拒绝 | /billing, /team, /settings | — | 无 | ✅ | P0 |
| 13 | API 失败提示 | SettingsPage | GET /api/health (500 mock) | Bearer | ✅ | P0 |
| 14 | 表单校验 | LoginPage | — | 无 | ✅ | P0 |
| 15 | 导出/下载 | GoldCasesPage | — | Bearer | ⚠️ 仅模板复制 | P2 |
| 16 | 刷新后保持 | (全局) | (localStorage) | 持久化 | ✅ | P0 |
| 17 | 退出登录 | Layout → /login | (localStorage clear) | — | ✅ | P0 |

---

## 2. 逐测试详细矩阵

### 2.1 测试 01: 核心业务对象列表加载

```
目标页面:   /workbench
业务对象:   Encounter
API 调用:   encountersApi.list() (当搜索输入 >= 2 字符时)
           reviewsApi 无显式列表调用
前置条件:   已认证
成功标准:   页面渲染 h2 "编码工作台"
           搜索输入框可见
           无 error banner
失败场景:   API 返回 500 → 页面仍可渲染 (搜索功能不可用)
可自动化:   ✅ 是
测试输入:   无需 (仅验证页面加载)
数据需求:   无需 seed data
```

### 2.2 测试 02: 核心业务对象过滤/搜索

```
目标页面:   /workbench
交互元素:   input[placeholder="搜索病历 ID 或科室..."]
触发条件:   输入 >= 2 字符
API 调用:   encountersApi.list(0, 10, query)
UI 响应:    下拉列表 (匹配结果) 或 "无匹配病历"
成功标准:   输入 "ab" → 搜索触发 → 下拉或 "无匹配" 显示
            输入保留在 input 中 (toHaveValue)
失败场景:   API 超时 → .catch(() => {}) 静默吞没 → 无 UI 变化
可自动化:   ✅ 是 (但需接受可能无匹配结果)
```

### 2.3 测试 03: 核心业务对象分页

```
目标页面:   /gold-cases
业务对象:   GoldCase
API 调用:   goldCasesApi.list(page, 20)
UI 元素:    上一页 / 页码 / 下一页 按钮; "共 N 条" 文本
成功标准:   有数据时 → 分页控件可见 + 功能正常
            无数据时 → 分页控件隐藏 (total > 0 判断)
失败场景:   API 返回异常 total → 分页计算错误
可自动化:   ⚠️ 需要预先 seed 至少 10 条 GoldCase
数据需求:   10+ GoldCase records
```

### 2.4 测试 04: 新建核心业务对象

```
目标页面:   /gold-cases
触发:       点击 "添加金标准病例" 按钮 → 表单展开
表单字段:   input[placeholder="科室"] (text)
           input[placeholder="诊断分组"] (text)
           input[placeholder="编码"] × 4 (code fields)
           select (难度: easy/medium/hard)
提交:       点击 "保存" 按钮
API 调用:   POST /api/gold-cases
成功标准:   表单关闭；无 .badge-error 出现
失败场景:   必填字段为空 → API 返回 422 → 无 UI 反馈 (已知缺陷)
可自动化:   ✅ 是
数据需求:   无需 (创建新数据)
```

### 2.5 测试 05: 新建表单校验

```
目标页面:   /gold-cases
校验层:     HTML5 required? → 否 (无 required 属性)
           前端 JS 校验? → 否
           后端 Pydantic 校验? → GoldCaseCreate 无 min_length 约束
实际行为:   空表单可提交 → API 创建 gold case 含空字段
风险:       脏数据入库
成功标准:   提交空表单 → 表单保持打开 或 错误提示出现
可自动化:   ⚠️ 当前无前端校验 → 测试验证"不崩溃"而非"拦截"
改进建议:   GoldCaseCreate schema 添加 min_length 约束
```

### 2.6 测试 06: 核心业务对象删除

```
目标页面:   /gold-cases
触发:       table 中行尾红色删除按钮 (svg.lucide-trash2)
确认:       window.confirm("Delete this gold case?")
API 调用:   DELETE /api/gold-cases/{id}
成功标准:   确认后行消失；页面仍显示表格标题
失败场景:   无数据时无可删除项 → 测试 vacuously pass
可自动化:   ⚠️ 需要至少 1 条 GoldCase
数据需求:   1+ GoldCase record
特殊处理:   page.on('dialog') 监听 confirm
```

### 2.7 测试 07: 核心业务对象详情查看

```
目标页面:   /workbench → 搜索 → 点击 encounter → /workbench/:id
交互路径:   输入搜索 → 点击下拉中的 encounter → URL 变化
API 调用:   GET /api/encounters/{id}
UI 响应:   显示 Patient 信息；文档列表；"运行编码审核" 按钮
成功标准:   URL 变为 /workbench/{id}；Patient 文本可见
失败场景:   无 encounter 数据 → 搜索无结果 → 测试 vacuously pass
可自动化:   ⚠️ 需要至少 1 条 Encounter
数据需求:   1+ Encounter (可通过 POST /api/encounters/text 创建)
```

### 2.8 测试 08: 核心业务对象编辑

```
目标页面:   /gold-cases
现状:       无 PATCH/PUT 端点 → GoldCasesPage 无编辑模式
            "编辑" = 打开新建表单 + 覆盖性创建
操作:       打开 "添加金标准病例" → 填写新值 → "保存"
API 调用:   POST /api/gold-cases
成功标准:   表单关闭；无 error
可自动化:   ✅ 是 (实际是测试 "新建")
改进建议:   添加 PUT /api/gold-cases/{id} + 前端 Edit 按钮
```

### 2.9 测试 09: 核心业务对象提交

```
目标页面:   /workbench/:id
触发:       点击 "运行编码审核" 按钮
API 调用:   POST /api/reviews (触发完整 9 步编码管线)
管线步骤:   证据提取 → ICD诊断 → 手术编码 → 首页 → 规则验证 →
           证据校验 → DRG分析 → 文书缺口 → 报告生成 → 人工审核
LLM 调用:   每步调用 DeepSeek API (多次 LLM 往返)
耗时:       30-120 秒
成功标准:   "运行编码审核" 按钮消失；"人工审核" 按钮出现；
           显示完成时间 (processing_time_ms)
失败场景:   LLM API 超时/错误 → error state → red banner
可自动化:   ⚠️ 是，但需特殊处理：
           - 延长 timeout (120s+)
           - 或 mock agent_runner
           - 每次运行产生 LLM 费用
费用:       ~¥0.50-2.00 / 次 (取决于管线复杂度)
建议:      CI 中默认 skip；手动触发时运行
```

### 2.10 测试 10: 核心业务状态变更

```
目标页面:   /settings
业务对象:   安全护栏 (Guardrails) — 前端 state，无后端持久化
操作:       点击 6 个 toggle switch 中的任意一个
UI 响应:    toggle 视觉状态切换 (inner dot 位置变化)
成功标准:   点击后 dot 移动 (left-0.5 ↔ left-3.5)
注意:       状态不持久化 (页面刷新后重置)
可自动化:   ✅ 是
数据需求:   无需
```

### 2.11 测试 11: 权限不足时按钮不可见

```
现状:       iCoDer 前端无角色级 UI 门控
            所有已认证用户看到相同的 UI
            无法测试"admin 可见但 coder 不可见"
可自动化:   ❌ 否 — 前端未实现
改进建议:   基于 user.role 的条件渲染
```

### 2.12 测试 12: 直接访问无权限 URL 被拒绝

```
目标路由:   /billing, /team, /settings, /gold-cases (所有受保护路由)
机制:       ProtectedRoute 组件检查 useAuthStore().isAuthenticated
            未认证 → <Navigate to="/login" replace />
操作:       清空 localStorage → 直接 goto 受保护 URL
成功标准:   URL 最终变为 /login
已知问题:   /api-clients 被 Vite proxy 拦截 → 无法测试
可自动化:   ✅ 是
测试方法:   browser.newContext({ storageState: undefined }) 创建干净会话
```

### 2.13 测试 13: API 返回失败时页面提示

```
目标页面:   /settings (请求 GET /api/health)
方法:       page.route('**/api/health') → 拦截 → fulfill 500
成功标准:   页面不崩溃 (h2 "设置" 仍可见)
            状态指示器显示错误 (红色 dot 或 "unknown")
注意:       SettingsPage 的 .catch(() => setConfig(null)) → 静默降级
            不展示 toast / banner
可自动化:   ✅ 是 (使用 Playwright route interception)
```

### 2.14 测试 14: 表单校验

```
目标页面:   /login
校验层:     HTML5 required 属性
            JS: if (!username.trim() || !password.trim()) setError(...)
            API: auth/login → 401 → error response
测试 1:     空提交 → 浏览器原生 required 提示 或 JS error
测试 2:     错误凭据 → red banner (.bg-red-50) 显示错误消息
成功标准:   required 属性存在于两个 input
            错误凭据 → error banner 可见
可自动化:   ✅ 是
```

### 2.15 测试 15: 导出或下载

```
目标页面:   /gold-cases
现有功能:   "模板" 按钮 — 复制 CSV 模板到剪贴板 + alert()
           "CSV导入" 标签 — 上传 CSV 文件
缺失功能:   无真正的 CSV 导出 (下载当前 gold cases 为 CSV)
操作:       点击 "模板" → 验证 alert 对话框内容和剪贴板
可自动化:   ⚠️ 仅模板复制可测 (csv 导出不存在)
改进建议:   添加 GET /api/gold-cases?format=csv 导出端点
```

### 2.16 测试 16: 页面刷新后数据保持

```
存储层:     localStorage: icoder-auth (Zustand persist)
            localStorage: access_token
            localStorage: refresh_token
操作:       登录 → 验证 localStorage → 刷新页面 → 验证未重定向
成功标准:   icoder-auth.state.isAuthenticated === true
            access_token 存在
            URL 不含 /login
可自动化:   ✅ 是
```

### 2.17 测试 17: 退出登录

```
触发:       Layout header 用户头像 → 下拉菜单 → "退出登录"
后端:       无 (纯前端清空 storage)
前端:       useAuthStore().logout() → 清空 localStorage (3 keys) →
            set isAuthenticated = false → Navigate to /login
成功标准:   URL 变为 /login
            localStorage access_token === null
            icoder-auth 中的 isAuthenticated === false
可自动化:   ✅ 是
挑战:       定位器 — user menu button 需动态查找 (header 最右侧按钮)
```

---

## 3. 自动化就绪状态汇总

| 状态 | 数量 | 测试编号 |
|------|------|---------|
| ✅ 可直接自动化 | 9 | 01, 02, 04, 10, 12, 13, 14, 16, 17 |
| ⚠️ 需要 seed data | 4 | 03, 06, 07, 08 |
| ⚠️ 耗时/费用高 | 1 | 09 |
| ⚠️ 功能受限 | 3 | 05, 08, 15 |
| ❌ 前端未实现 | 1 | 11 |
| **总计** | **17** | |

---

## 4. 改进建议 (按优先级)

| 优先级 | 改进 | 影响测试 |
|--------|------|---------|
| 🔴 P0 | GoldCaseCreate schema 添加 min_length 约束 | 测试 05 真正有意义 |
| 🔴 P0 | 添加 data-testid 属性到关键元素 | 所有测试稳定性 |
| 🟡 P1 | 修复 /api-clients 路由与 Vite proxy 冲突 | 测试 12 覆盖该路由 |
| 🟡 P1 | 添加 GET /api/gold-cases/export?format=csv | 测试 15 完整 |
| 🟡 P1 | 添加 PUT /api/gold-cases/{id} 编辑端点 | 测试 08 真正编辑 |
| 🟢 P2 | CaseReviewPage 审核失败添加用户提示 | 测试 09 错误路径 |
| 🟢 P2 | 前端角色级 UI 门控 | 测试 11 |
| 🟢 P2 | 全局 ErrorBoundary | 所有测试健壮性 |
| 🟢 P2 | 后端 seed 脚本 (创建测试 encounter + gold case) | 数据依赖测试 |

---

## 5. 覆盖缺口

| 缺口 | 说明 |
|------|------|
| WebSocket 流 | STT、Agent SSE 流未覆盖 → 需独立 WebSocket 测试工具 |
| 多角色权限矩阵 | 前端未实现 → 后端单独测试 get_admin_user |
| OAuth Client Credentials | M2M 认证流 → 独立 API 测试 |
| FunASR STT 质量 | 需要真实音频文件 → 独立质量测试 |
| DRG 分组器准确率 | 需要金标准 DRG 数据 → 已有 evaluation API |
| 性能基准 | LLM 管线耗时无 baseline → 后续阶段 |
