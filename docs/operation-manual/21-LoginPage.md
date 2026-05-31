# LoginPage

**路由**: `/login` | **定位**: 登录

## 元素
| 元素 | 操作 | 预期 |
|------|------|------|
| iCoDer Console 标题 | 查看 | 品牌展示 |
| 用户名 input | 输入 | placeholder: "用户名" |
| 密码 input | 输入 | placeholder: "密码" |
| 登录按钮 | 点击 | POST /api/auth/login |
| 加载中 | 查看 | 按钮文字变 "登录中..." |
| 错误提示 | 查看 | 红色文字显示错误详情 |
| 演示账号提示 | 查看 | "演示账号：admin / admin123" |
| 隐私政策/服务条款 | 点击 | 跳转 |
