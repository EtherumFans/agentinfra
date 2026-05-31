# APIClientsPage

**路由**: `/api-clients` | **定位**: API 客户端管理

## 元素
| 元素 | 操作 | 预期 |
|------|------|------|
| OAuth客户端/API密钥 | 点击标签 | 切换列表 |
| 名称 input | 输入 | placeholder: "客户端名称（如：生产环境SDK）" |
| 描述 input | 输入 | — |
| 创建按钮 | 点击 | POST /api/oauth/clients |
| 客户端行 | 查看 | client_id + 创建时间 |
| 复制按钮 | 点击 | 复制客户端 ID/密钥 |
| 撤销按钮 | 点击 | 确认模态框 → DELETE |
