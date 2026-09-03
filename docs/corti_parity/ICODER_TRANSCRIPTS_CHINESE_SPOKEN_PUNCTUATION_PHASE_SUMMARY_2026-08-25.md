# iCoDer Transcripts 中文口述标点阶段总结（2026-08-25）

## 阶段结论

本阶段关闭了开发环境内可完成的预录音中文口述标点合同切片。`POST /api/v2/tools/transcripts` 现在按 Corti 当前公开合同解析 `spokenPunctuation`、`automaticPunctuation` 与已弃用的 `isDictation`：

- `spokenPunctuation=true` 启用显式口述标点转换，并优先于自动标点；因此它与 `automaticPunctuation=false` 同时出现时请求仍被接受。
- 只要任一当前字段被提供，`isDictation` 就被忽略；只有两个当前字段都未提供时，`isDictation=true` 才作为 `spokenPunctuation=true` 的兼容回退。
- 未显式启用时不改写 ASR 文本；当前本地转换只对 `zh-*` 生效。
- 同步完成、异步 Job 和进程恢复三条路径复用同一个确定性后处理器，并在用户声明的 replacements 之前执行。

实现覆盖常用中文口述符号：逗号、句号、问号、感叹号、冒号、分号、顿号、省略号、左右括号和左右单双引号。它是可审计的 ASR 后处理，不冒充模型原生命令识别能力。

## 同期稳定性修复

最终全量回归前发现登录限流与一般 API 请求共享同一桶，容易让先前正常流量耗尽登录额度。Redis 与内存实现现统一使用 `login`/`general` 独立桶；Redis 成员增加纳秒唯一量，避免同毫秒请求相互覆盖。新增回归证明一般请求不会消耗登录额度，登录额度仍独立失败关闭。

## 端到端与回归证据

- 真实 Uvicorn、真实注册/鉴权、真实录音上传和真实同步/异步生命周期 loopback：通过。
- 音频和 ASR 边界：仅使用固定合成 WAV/固定合成文本；`patient_audio_used=false`、`real_stt_used=false`、`real_llm_used=false`、`native_models_loaded=false`。
- 同步现行字段：`spokenPunctuation=true` 得到 `患者主诉胸痛，持续三天。（房颤）`。
- 默认行为：未开启时保留原始口述词。
- 异步兼容字段：`isDictation=true` 经 Job 轮询得到相同格式化结果。
- 最终后端全量：**5,574 passed、20 skipped、11 deselected、0 failed**，28:48；JUnit 已保存。
- JavaScript SDK：**95/95**；Python SDK：**101/101**；.NET net8.0/net10.0：各 **82/82**。
- 部署预检：**97/97**；校验器 **6/6**；OpenAPI 运行时/快照合同 **7/7**。
- OpenAPI：877,077 bytes、271 paths、299 schemas。

全量诊断中两次人为覆盖 `APP_ENV` 的非权威运行分别触发 4 项账单模拟失败和一组环境策略失败；移除全局覆盖后上述最终全量全部通过。这些运行没有出现 Windows 内存不可读/写、Python 崩溃或 Uvicorn `-1` 异常。

## SDK 与候选工件

JavaScript/.NET 版本为 `1.0.0-beta.39`，Python 为 `1.0.0b39`。三套 SDK 均公开当前字段和兼容字段，客户端也允许 `spokenPunctuation=true` 覆盖 `automaticPunctuation=false`。5 个安装包与 1 个内层 manifest 已重新构建、校验和哈希，未发布到外部仓库。

## 尚未关闭的 Corti 能力差距

本阶段没有证明 Corti 私有实现等价、临床准确率或生产就绪。以下仍开放：

1. 预录音 `keyterms` 尚失败关闭；Corti 当前公开支持该字段。这是下一项可在开发环境继续关闭的合同差距。
2. 预录音多声道、diarization、多语言，以及 `automaticPunctuation=false` 的真实 ASR 行为仍未实现。
3. 口述标点目前是中文确定性后处理，不是声学/语言模型原生命令识别；真实口音、噪声、长音频和医疗术语质量未验证。
4. 未用同一批临床合规音频对 Corti 与 iCoDer 做盲测；WER/CER、标点 F1、术语召回、延迟、成本和并发容量均无 head-to-head 证据。
5. Docker/Linux/PostgreSQL 多副本、区域数据驻留、监控告警和医院验收仍是外部上线门禁。

## 安全与数据边界

本阶段显式清空 DeepSeek/OpenAI/项目 LLM 凭证，关闭外部 LLM、本地 STT 和原生 MedCoder，使用临时 SQLite；受保护开发数据库未迁移、未写入。用户曾在对话中暴露的 DeepSeek Key 未被本阶段使用，仍必须在 DeepSeek 控制台撤销并轮换。

机器证据见 `reports/transcripts_dictation_phase_20260825/phase_evidence.json`，发布物清单见 `reports/transcripts_dictation_phase_20260825/release_candidate_validation.json`。
