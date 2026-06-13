---
name: icoder-coding-review
description: >
  集成 iCoDer 病案首页编码审核嵌入组件 <icoder-embedded> 的开发者技能。覆盖生命周期、
  embedded-event 事件总线、以及在院内私有化部署下必须遵守的硬规则。当你需要把 iCoDer 的
  编码审核能力嵌入医院 HIS/EMR 门户或第三方工作台时使用本技能。
---

# 集成 iCoDer 编码审核组件

`<icoder-embedded>` 是一个无依赖的自定义元素，把「病案首页编码审核 Agent」的结果
（codes / candidates / 合规门禁 / 证据回链 / DRG 路由）渲染进宿主页面。它是 Corti
`<corti-embedded>` 范式在私有化部署下的对应物：**宿主持有鉴权，组件只渲染结果**。

## 安装与挂载

```html
<script src="https://<医院内网>/icoder-embedded.js"></script>
<icoder-embedded id="w" base-url="https://<医院内网>"></icoder-embedded>
```

## 生命周期（宿主驱动）

`ready → auth → configure → show`

```js
const w = document.getElementById('w');
w.configureSession({ token: HOST_ISSUED_TOKEN });                         // auth
w.configure({ agentId: 'icoder/homepage-coding-review-agent', codingSystem: 'ICD-10-CN' });
w.run(clinicalText);                                                      // -> 渲染
```

## 事件总线

组件派发单一的、冒泡且穿透 shadow DOM 的 `embedded-event`，detail 为 `{ type, payload }`：

| type | 何时触发 | payload |
|------|----------|---------|
| `ready` | 组件挂载完成 | `{ baseURL }` |
| `auth` | configureSession 后 | `{ authenticated }` |
| `configured` | configure 后 | `{ agentId, codingSystem }` |
| `run.started` / `run.completed` | 运行开始/完成 | `{ run_id, codes, candidates }` |
| `rule-gate-triggered` | 门禁要求人工复核 | `{ run_id, passed, hits }` |
| `evidence-clicked` | 点击证据高亮 | `{ code, start, end, text }` |
| `code-overridden` / `human-review-submitted` | 采纳候选码 / 复核回写 | 复核结果 |
| `error.triggered` | 任意失败 | `{ message, detail }` |

## 硬规则（HARD RULES）

集成时必须遵守。前 6 条是通用嵌入规则（与 Corti 同源），后 5 条是 iCoDer 私有化 + 中国编码体系特有。

**通用嵌入规则**
1. 宿主持有并注入令牌；组件**绝不**存储凭据、绝不把令牌写入 DOM 属性（用 `configureSession`，不要用 attribute）。
2. 令牌是短时、无状态的；过期由宿主负责刷新后重新 `configureSession`。
3. 始终监听 `error.triggered` 并向用户展示降级 UI，不要静默吞错。
4. 不要解析或依赖组件内部 DOM 结构；只通过公开方法与 `embedded-event` 交互。
5. 一个组件实例对应一次会话；多病历并发请用多个实例或串行 `run`。
6. 跨源加载组件脚本时，确保 iCoDer 服务端 CORS 允许你的宿主源。

**iCoDer 私有化 + 中国编码体系特有规则**
7. **数据不出院**：`base-url` 必须指向医院内网的 iCoDer 服务；不得将病历文本转发到院外或公有云。
8. **证据为字符级 span**：证据高亮按 `text[start:end]`（start 含 / end 不含）渲染，**不得**用文本检索去重新定位证据——偏移基于服务端返回的去标识化文本。
9. **codes 与 candidates 可视分离**：必须分区展示，**不可合并**、codes **不可重排**（临床顺序有意义）；candidates 一律标注「需人工复核」。
10. **门禁与 severity 可见**：命中规则按 Critical/Moderate/Informational 展示；`human_review_required=true` 时必须暴露人工复核入口（角色受限：coder|admin）。
11. **编码体系固定**：只使用 ICD-10-CN / ICD-9-CM-3（及 DRG/DIP 路由）；**不得**在宿主侧改写、映射到或臆造 ICD-10-CM / 境外体系。

> 注：`production_writeback_blocked` **不是**集成方需要执行的规则——它是服务端恒定的不变量
> （样板阶段永远为 true，禁止写回 EMR 生产库）。集成方无需也无法关闭它，因此它不列入上面的
> 集成硬规则；这与把它误当作「前端开关」的做法不同。
