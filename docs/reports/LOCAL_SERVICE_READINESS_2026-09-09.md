# 本地启动与就绪检查

医学编码效果优化按用户要求暂停；本次只处理本地服务可用性，不运行模型或修改编码配置。

## 实现

- 保留 `/api/health` 存活接口，新增 `/api/health/ready`：实际查询数据库，成功返回 200，连接失败或超过 3 秒返回 503。响应不含连接地址、数据库名称或异常详情，禁止缓存。
- 新增可复用 Windows 启动脚本 `scripts/local/Start-IcoderReview.ps1`。校验依赖、设置前端 API 目标、以隐藏进程启动缺失服务，并依次验证后端数据库连接、前端 API 代理、登录页 HTML。
- 占用端口但未就绪时明确失败，不自动结束未知进程。重复启动复用现有服务，不安装软件、不执行数据库迁移。
- 当前本地审查包装脚本 `artifacts/product-review-2026-09-07/start_local_review.ps1` 已接入该流程。数据库需要事先启动；后端启动脚本继续使用既有受限 PostgreSQL 账号和密钥配置。
- 登录页面区分网络断开、超时、服务端故障和原有账号错误；服务端故障不会直接展示内部错误详情。

## 使用

在仓库根目录运行现有本地审查入口：

```powershell
./artifacts/product-review-2026-09-07/start_local_review.ps1
```

只检查当前服务，不启动进程：

```powershell
./scripts/local/Start-IcoderReview.ps1 -CheckOnly
```

通用脚本的启动模式需提供 BackendPython、BackendScript、FrontendDirectory；BackendScript 必须绑定指定回环端口并自行读取所需配置。进程日志默认位于 `.data/local-service-logs`，当前审查包装脚本将日志写入审查目录的 `backend.out.log` / `backend.err.log` 和 `frontend.out.log` / `frontend.err.log`。

## 验证

- 后端 2 项测试通过，覆盖真实查询、连接释放、失败响应与超时。
- 登录错误信息 3 项测试通过；前端类型检查通过。
- 实际启动后：后端数据库检查、前端代理检查及登录页 HTML 检查通过。
- 重复执行启动脚本：前后进程号相同。
- 指向不可用前端端口的负向测试：正确报告代理未就绪。

## 范围

该检查验证 HTTP 与数据库连通，不替代模型可用性、业务权限或工作队列验收。没有提交真实账号密码进行新的登录测试，也没有模拟关闭当前业务数据库。自动开机启动、进程监督与生产告警仍需后续部署工作。
