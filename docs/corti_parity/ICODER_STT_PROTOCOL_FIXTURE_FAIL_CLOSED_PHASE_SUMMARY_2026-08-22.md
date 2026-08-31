# iCoDer STT 协议样例失败关闭阶段总结（2026-08-22）

> 声明：本报告证明合成 STT 协议样例不会被普通开发或部署进程发布，不代表真实 ASR 的临床准确率、方言覆盖、多人分离、延迟或 Corti 托管语音能力等价。

## 结论

预录音 STT 主链已经具备租户隔离的录音上传/读取/删除、加密持久化、同步与持久异步转写、重启恢复、状态查询、请求能力失败关闭和引擎不可用 503。遗留风险位于 OpenAPI 协议一致性样例：旧逻辑在 `development/test` 中只需设置 `ICODER_ENABLE_PROTOCOL_FIXTURES=1`，普通 Uvicorn 进程即可为不存在的 interaction 生成固定英文病历文本、`-stub` 录音 ID 和完成状态。

本阶段将该路径收窄为三重条件：开发/测试环境、显式 fixture 开关、当前进程实际加载 pytest。环境变量本身不再足以发布合成录音或转写；普通 Python 进程的直接反证为 `NON_PYTEST_FIXTURES_ENABLED=False`。真实上传和转写路径没有改为测试替身，也没有降低现有能力。

## 实现与安全边界

- `v2_tools_stt._protocol_fixtures_enabled()` 增加 pytest 运行时门禁。
- Cloud 模板继续固定 `ICODER_ENABLE_PROTOCOL_FIXTURES=0`，Cloud 环境在 pytest 下也不能打开 fixture。
- 未物化的录音或转写在普通运行时继续返回空列表或 404；创建转写必须引用租户内真实上传的录音。
- 固定样例仍保留给 Corti/OpenAPI 协议形状测试，但不能由开发者启动的 Python/Uvicorn 进程通过环境变量启用。
- 部署预检新增 `stt_protocol_fixtures_are_pytest_only_and_cloud_disabled`，同时校验代码门禁、反例测试和 Cloud 模板。

## 验证结果

- STT 真实生命周期、10 组协议一致性与部署预检聚焦回归：**82/82**。
- 完整 STT API、录音/转写仓储、异步 Job、WebSocket 安全、Cloud 配置和部署预检扩大回归：**145/145**，13 条均为测试客户端弃用或测试 JWT 长度警告。
- 普通非 pytest Python 进程在 `APP_ENV=development` 且 `ICODER_ENABLE_PROTOCOL_FIXTURES=1` 时返回 `False`。
- 静态部署候选预检：**68/68**。
- OpenAPI `--check` 通过，仍为 269 paths、288 schemas、842,015 bytes。
- 未启动独立后端，未使用真实 ASR/LLM，未允许外部 LLM，未加载 Windows 原生 MedCodER。
- 开发主库 `backend/data/icoder.db` SHA-256 保持 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。

## 对 Corti 的差距判断

本阶段关闭的是“测试样例冒充真实语音资源”的产品真实性缺口，不提升识别质量。iCoDer 当前仅诚实支持已验证的中文单声道能力，并明确拒绝尚未实现的 diarization、多声道、keyterms、关闭自动标点和多参与者映射。与 Corti 实时医疗语音能力的差距仍包括真实 Provider 的普通话/方言/中英混说、多人、噪声、长音频、流式纠错、词级时间戳、临床术语准确率、P50/P95 首字与终稿延迟、成本及现场稳定性。

## 仍开放的门禁

1. 使用合法、去标识且有金标准的中国医疗音频数据做离线准确率、方言、噪声和长音频评测。
2. 在明确预算和隔离凭据下验证真实 ASR Provider，并与 Corti 对同一批授权音频做双边对照。
3. 医院现场麦克风、网络、多人会诊、患者授权、录音留存与删除政策验收。
4. 生产对象存储/KMS、队列、多副本、容量、故障注入、云、法务、认证和独立临床 reviewer。

机器证据目录：`reports/agent_hub/stt_protocol_fixture_fail_closed_phase_20260822/`。

