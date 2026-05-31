# BillingPage

**路由**: `/billing` | **定位**: 计费管理

## 元素
| 元素 | 操作 | 预期 |
|------|------|------|
| 可用积分 | 查看 | ¥xxx.xx |
| 已消耗积分 | 查看 | ¥xxx.xx |
| 添加积分 | 点击 | 调用 POST /api/billing/credits |
| 套餐计划/账单历史/企业信息 | 点击标签 | 切换面板 |
| 低余额提醒 | 开关+阈值+更新 | localStorage 持久化，"已保存"提示 |
| 自动充值 | 开关+金额+更新 | localStorage 持久化 |
| 交易记录 | 查看 | GET /api/billing/transactions |
