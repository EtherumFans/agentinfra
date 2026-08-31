# iCoDer 数据库日志隐私阶段总结（2026-08-22）

## 阶段结论

本阶段关闭了一个医疗隐私 P0：本地 Compose 的 `DEBUG=true` 会经 `database.py` 直接开启 SQLAlchemy `echo`，从而把绑定参数中的完整病历、提示词和标识符写入后台日志。

当前 SQL statement echo 已与应用 `DEBUG` 完全解耦，默认关闭；应用数据库引擎在任何模式下均强制 `hide_parameters=true`；Cloud 模式若尝试开启 `ICODER_DATABASE_SQL_ECHO=true` 会在绑定端口前拒绝启动。本地操作者只有显式开启该独立开关才能查看 SQL 结构，而且仍看不到绑定值。

## 实现

- 新增 `ICODER_DATABASE_SQL_ECHO=false`，不再用 `DEBUG` 控制数据库 statement logging。
- `create_async_engine` 永久设置 `hide_parameters=true`，即使其他 logger 把 `sqlalchemy.engine` 提升到 INFO，也不会记录绑定值。
- 本地 Compose 将 `DEBUG` 和 SQL echo 均改为默认 false、可显式覆盖；Cloud 模板显式声明 SQL echo false。
- Cloud fail-closed 策略拒绝 SQL echo，防止容器或集中日志采集器接收 SQL 结构及潜在运维噪声。
- 增加默认、显式本地诊断、绑定参数哨兵及 Cloud 反例测试。
- 静态部署预检新增 `database_sql_logging_is_opt_in_and_parameter_safe`，当前 56/56。
- 新增 [`DATABASE_LOGGING_PRIVACY.md`](../cloud/DATABASE_LOGGING_PRIVACY.md) 运维规范，并更正 2026-08-15 Run SSE 阶段中过早声称该缺口已关闭的历史表述。

## 真实 TCP 验证

两次验证均使用临时隔离 SQLite、空 LLM 凭据、mock provider、禁用外部 LLM 与本机原生 MedCoder；只运行 `medical-coding-agent` 的合成示例，结束后按精确 PID 停服。

| 模式 | DEBUG | SQL echo | SQL engine 日志 | 参数隐藏标记 | 病历标记泄漏 | 手机哨兵泄漏 | Agent 安全结果 |
|---|---:|---:|---:|---:|---:|---:|---|
| 默认安全模式，`127.0.0.1:18023` | true | false | 0 | 0 | 0 | 0 | safe fail-closed 1/1 |
| 显式本地 statement 诊断，`127.0.0.1:18024` | true | true | 3,680 | 1,796 | 0 | 0 | safe fail-closed 1/1 |

第二组证明系统不是简单“没有执行 SQL”：日志中存在大量语句与参数隐藏标记，但 `T12 椎体压缩性骨折` 和 `13800138000` 均未出现。两个 runner 因真实能力未完成按预期返回退出码 1；安全轴均为 `safe_fail_closed=1`、`unsafe_or_invalid=0`，未把 mock 失败冒充能力成功。

## 回归结果

- 后端联合回归：179/179 passed。
- 配置、数据库日志与部署预检专项：55/55 passed。
- 静态部署候选预检：56/56 passed，模式仍为 `static_without_docker_cli`。
- 两套真实 TCP 服务均已停止；18023/18024 无监听残留。
- 本阶段没有变更 API 数据结构，因此无需更新 OpenAPI。

## 边界与后续门禁

- 本阶段证明应用数据库引擎的绑定参数保护，不证明第三方驱动、代理、APM agent 或云采集器已通过生产 DLP 审计。
- 原始 SQL 文本中仍禁止通过字符串拼接嵌入临床值；生产代码审查和 SAST 仍应检查该规则。
- 日志保留期、SIEM、访问控制、跨境路径、第三方处理者和医院制度仍需云/法务/医院验证。
- 当前开发数据库仍未迁移或重启；本阶段只使用隔离临时数据库。
- Docker、PostgreSQL 多副本、Linux 原生 MedCoder、.NET 和生产日志基础设施仍未在本机执行。

机器证据位于 [`database_log_privacy_phase_20260822/phase_evidence.json`](../../reports/agent_hub/database_log_privacy_phase_20260822/phase_evidence.json)。
