# iCoDer 多码表管理 — Figma 设计规范（参照 Corti 风格）

## 设计参考
参照 Corti Console (console.corti.app)，使用其已验证的交互模式和视觉语言。

---

## 一、全局样式（与 Corti 对齐）

### 颜色系统
| Token | HEX | 用途 |
|-------|-----|------|
| 主色调 | #3C61DD | 按钮、选中态、链接、边框高亮 |
| 主色浅 | #EEF1FA | 选中背景、hover 态 |
| 成功绿 | #2D6A4F | 有效标记 (valid=true)、✓ 图标 |
| 警告黄 | #E6A817 | 部分匹配标记 |
| 错误红 | #C41E3A | 无效标记 (valid=false)、✗ 图标 |
| 背景白 | #FFFFFF | 卡片、页面背景 |
| 背景灰 | #F8F9FA | 次级区域、sidebar 背景 |
| 边框灰 | #E5E7EB | 卡片边框、分割线 |
| 文字主 | #111827 | 标题、正文 |
| 文字次 | #6B7280 | 描述、辅助信息 |
| 文字弱 | #9CA3AF | placeholder、禁用态 |

### 字体
| 级别 | 字号 | 字重 | 用途 |
|------|------|------|------|
| 页面标题 | 24px | 600 | "码表管理" |
| 区块标题 | 18px | 600 | 卡片标题、modal 标题 |
| 表格标题 | 14px | 500 | 列表表头、Tab 标签 |
| 正文 | 13px | 400 | 描述文本、表格内容 |
| 辅助文本 | 11px | 400 | 标签、徽章、提示文字 |
| 代码文本 | 12px | 500 | 编码显示 (font-mono) |
| 数字/数据 | 13px | 500 | 编码计数、版本号 (font-mono) |

### 圆角与间距
- 卡片: rounded-xl (12px)
- 按钮: rounded-lg (8px)
- 输入框: rounded-lg (8px)  
- 标签/徽章: rounded-full
- 页内间距: px-6 (24px)
- 卡片内间距: p-5 (20px)
- 元素间距: gap-3 (12px)

---

## 二、页面布局

```
┌─────────────────────────────────────────────────────────┐
│ ← Sidebar 256px → │         Main Content               │
│                    │                                    │
│ [iCoDer Logo]      │ 码表管理                            │
│                    │ 管理和配置不同医疗机构的编码字典      │
│ 首页               │                                    │
│ 开发者快速入门     │ ┌─────────────────────────────────┐│
│                    │ │ 🔍 跨表代码查询                  ││
│ AI STUDIO          │ │                                 ││
│  总览              │ │ [编码: N18.500   ] [查询映射]   ││
│  智能体            │ │                                 ││
│  语音转文字        │ │ ┌──────┐ ┌──────┐ ┌──────┐    ││
│  文书生成          │ │ │ 国标 │ │ 医保 │ │ 医院 │    ││
│  嵌入式助手        │ │ │N18.5 │ │N18.5 │ │N18.5 │    ││
│  事实提取          │ │ │  ✓   │ │  ✗   │ │  ✗   │    ││
│  医学编码          │ │ └──────┘ └──────┘ └──────┘    ││
│                    │ └─────────────────────────────────┘│
│ 管理               │                                    │
│  API 客户端        │    码表列表                         │
│  团队              │ ┌─────────────────────────────────┐│
│  计费              │ │ ICD-10-CN 国标版(2025) [默认]   ││
│  用量              │ │ 33,304 条 · 国家卫健委 · v2025  ││
│  设置              │ │ ...                             ││
│                    │ └─────────────────────────────────┘│
│ 数据管理           │ ┌─────────────────────────────────┐│
│  码表管理 ●        │ │ ICD-10-CN 医保版(2025)          ││
│  编码字典          │ │ 33,304 条 · 国家医保局 · v2025  ││
│  规则库            │ └─────────────────────────────────┘│
│  金标准病例        │ ┌─────────────────────────────────┐│
│  智能体评估        │ │ ICD-10-CN 医院本地版            ││
│  专家库            │ │ 0 条 · 本地医院 · v1.0          ││
│                    │ └─────────────────────────────────┘│
│ 支持               │                                    │
│  获取帮助          │ [+ 新增码表]                       │
│  工单中心          │                                    │
└─────────────────────────────────────────────────────────┘
```

---

## 三、页面分区详细设计

### Section 1: 跨表代码查询 (Cross-Table Lookup)

**布局**: 顶部卡片，浅灰背景，内含搜索栏和结果网格

**输入区**:
- 标签: "跨表代码查询" (18px, 600)
- 副文本: "输入编码查看在不同医疗机构码表中的表达" (13px, 400, 文字次)
- 输入框: 320px 宽，placeholder "输入 ICD 编码，如 N18.500"
- 按钮: "查询映射" (bg #3C61DD, 白字, 圆角-lg, 高 36px)
- 输入框和按钮之间 gap-3

**结果区** (点击查询后出现):
- 3-4 列卡片网格 (grid-cols-2 或 grid-cols-3, gap-3)
- 每张卡片:
  - 顶部: 码表名称 (14px, 500) + 来源类型标签 (11px, bg #EEF1FA, rounded-full)
  - 中部: 编码展示 (14px, font-mono, 500)，有效时绿色 ✓，无效时红色 ✗
  - 底部: 编码名称 (13px, 400, 文字次，一行截断)
  - 默认码表: 卡片右下角 "默认" 标签 (11px, bg #3C61DD, 白字, rounded-full)
  - 卡片: bg #FFFFFF, border #E5E7EB, rounded-xl, p-4
  - hover: border #3C61DD, shadow-sm

### Section 2: 码表列表 (Code Table List)

**布局**: 卡片列表，每个码表一行卡片

**列表头部**:
- 标题: "码表列表" (18px, 600)，右侧 "新增码表" 按钮 (bg #3C61DD，白字)

**每张码表卡片**:
```
┌──────────────────────────────────────────────────────────┐
│  ● ICD-10-CN 国标版(2025)                    [默认]  [删除] │
│  33,304 条编码 · 国家卫健委 · v2025                        │
│  标准编码 · ICD10_CN                                      │
│  ───────────────────────────────────────────────          │
│  描述: 国家卫生健康委员会发布的 ICD-10 临床版编码标准        │
└──────────────────────────────────────────────────────────┘
```

- 左侧圆点: 绿色=激活，灰色=未激活
- 卡片名 (16px, 600) + 默认标签 (11px, bg #3C61DD, 白字, rounded-full)
- 第二行: 编码数量 · 机构 · 版本 (13px, 400, 文字次)
- 第三行: 来源类型 · 编码系统 (13px, 400, 文字次)
- 描述行: 分割线上方 (13px, 400, 文字弱)
- 操作按钮在右上角: "默认"/"删除" (13px, 500, 文字次, hover 文字主)

### Section 3: 新增码表 Modal

**触发**: 点击"新增码表"按钮

**Modal 设计**:
- 居中弹窗，max-width 480px
- 标题: "新增码表" (18px, 600)
- 副标题: "配置新的编码字典数据源" (13px, 400, 文字次)
- 关闭按钮: 右上角 ×

**表单字段** (每字段 label 在上，input 在下):
1. 码表名称*: text input, placeholder "如：XX医院 HIS 编码库"
2. 描述: textarea, placeholder "描述该码表的用途和来源"
3. 编码系统*: select dropdown
   - ICD10_CN (ICD-10 临床版)
   - ICD9_CM3 (ICD-9-CM-3 手术操作)
   - LOCAL (医院本地扩展)
   - INSURANCE_DIAG (医保诊断)
   - INSURANCE_PROC (医保手术)
4. 版本号: text input, placeholder "1.0"
5. 来源类型*: select dropdown
   - standard (国家标准)
   - insurance (医保标准)
   - hospital (医院本地)
6. 所属机构: text input, placeholder "国家卫健委 / XX医院"

**底部按钮**: "取消" (outline) + "创建" (bg #3C61DD 白字)
- 两按钮 gap-3，右对齐

---

## 四、交互状态

### 按钮状态
| 状态 | 主按钮 (创建/查询) | 次级按钮 (取消/删除) |
|------|-------------------|---------------------|
| 默认 | bg #3C61DD, 白字 | bg 透明, border #E5E7EB, 文字次 |
| hover | bg #2F52C4 | bg #F3F4F6, border #D1D5DB |
| active | bg #243D93 | bg #E5E7EB |
| disabled | bg #9FB4E8, cursor not-allowed | 文字弱, cursor not-allowed |

### 输入框状态
| 状态 | 样式 |
|------|------|
| 默认 | border #E5E7EB, bg #FFFFFF |
| focus | border #3C61DD, ring 3px rgba(60,97,221,0.15) |
| error | border #C41E3A, 下方红色提示文字 (11px) |
| disabled | bg #F3F4F6, 文字弱 |

### Loading 状态
- 查询中: 按钮显示 spinner + "查询中..."
- 创建中: 按钮显示 spinner + "创建中..."
- spinner: 16px, 旋转动画

### Toast 通知
- 创建成功: 右上角绿色 toast "码表创建成功"，3s 自动消失
- 删除确认: Modal 确认 "确定删除该码表？相关映射数据也将被删除"
- 查询无结果: 卡片区显示空状态 "该编码在所有码表中均未找到"

---

## 五、设计 Token 速查表 (直接复制到 Figma)

```
// 颜色
Primary: #3C61DD
Primary Light: #EEF1FA
Primary Hover: #2F52C4
Success: #2D6A4F
Success Light: #ECFDF5
Warning: #E6A817
Warning Light: #FFFBEB
Error: #C41E3A
Error Light: #FEF2F2
Background: #FFFFFF
Background Secondary: #F8F9FA
Border: #E5E7EB
Text Primary: #111827
Text Secondary: #6B7280
Text Muted: #9CA3AF

// 字体
Font Family: "Noto Sans SC", -apple-system, "Segoe UI", sans-serif
Font Mono: "JetBrains Mono", monospace

// 字号
Heading 1: 24px / 600
Heading 2: 18px / 600
Heading 3: 16px / 600
Body Large: 14px / 500
Body: 13px / 400
Caption: 11px / 400
Code: 12px / 500 (font-mono)

// 圆角
Card: 12px
Button: 8px
Input: 8px
Badge: 999px (rounded-full)
Modal: 16px

// 阴影
Card Hover: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)
Modal Overlay: rgba(0,0,0,0.4) backdrop

// 间距 (Tailwind scale)
Page padding: 24px (p-6)
Card padding: 20px (p-5)
Element gap: 12px (gap-3)
Section gap: 24px
