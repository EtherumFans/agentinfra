# iCoDer Transcripts Keyterms 阶段总结（2026-08-25）

## 阶段结论

本阶段关闭了开发环境内可完成的预录音 `/transcripts` keyterms 合同差距。根据 Corti 当前公开文档，keyterms 适用于预录音转写和实时流，用于提高专有名词、医疗术语及同音词的识别偏置；词项有序且大小写敏感，最多 1,000 项、每项最多 50 字符。iCoDer 现已在同一边界实现这些约束：

- `POST /api/v2/tools/transcripts` 接受 `keyterms.terms[].term`，保持调用方顺序、大小写和书写形式，不执行去重、排序或替换。
- 同步完成、异步 Job 和进程恢复路径均把同一有序词项传入 STT 推理边界；FunASR 适配器将其映射为 `hotword`。
- keyterms 只随加密的转写请求数据持久化，不写入应用日志、错误文本或 STT 遥测。
- 空词项、超过 50 字符、超过 1,000 项在模型调用前失败关闭。
- JavaScript、Python、.NET SDK 均公开相同结构和客户端边界校验。

Keyterms 与 replacements 保持不同语义：前者只影响识别偏置，后者才进行转写后的文本替换。本阶段没有把 keyterms 实现成确定性字符串替换，也没有宣称仅凭请求透传即可证明识别质量提升。

参考合同：[Corti Keyterms](https://docs.corti.ai/stt/keyterms)、[Corti Transcripts](https://docs.corti.ai/stt/transcripts)。本地模型边界依据 FunASR `AutoModel.generate(..., hotword=...)` 的公开接口。

## 同期一致性修复

异步和恢复路径此前会把旧 `isDictation=true` 与当前显式 `spokenPunctuation=false` 做逻辑或运算，违反“当前字段优先、旧字段只在当前字段缺失时回退”的合同。任务执行器现优先信任已解析并持久化的 `spokenPunctuation`；只有旧数据完全没有该字段时才读取 `isDictation`。新增回归覆盖当前字段显式关闭和旧记录恢复两类场景。

## 端到端与回归证据

- 真实 Uvicorn、真实注册/租户鉴权、真实录音上传及同步/异步生命周期 loopback：通过。
- 专用 keyterms 请求把 `("房颤", "Corti Health")` 精确、有序、大小写敏感地传到合成 ASR 边界；机器证据为 `prerecorded_keyterms_forwarded_in_order=true`。
- 音频和 ASR 边界：固定合成 WAV/固定合成文本；`patient_audio_used=false`、`real_stt_used=false`、`real_llm_used=false`、`native_models_loaded=false`。
- STT/环境处理/OpenAPI 扩展回归：**130/130**。
- 最终后端全量：**5,575 passed、20 skipped、11 deselected、0 failed**，28:23；JUnit 已保存。
- JavaScript SDK：**95/95**；Python SDK：**101/101**；.NET net8.0/net10.0：各 **82/82**。
- 部署预检：**98/98**；最终发布验证器/OpenAPI 回归：**13/13**。
- OpenAPI：877,158 bytes、271 paths、299 schemas。

本阶段和最终回归没有再现 Windows “内存不可读/写”、Python 崩溃或 Uvicorn `-1` 异常退出。

## SDK 与候选工件

JavaScript/.NET 版本为 `1.0.0-beta.40`，Python 为 `1.0.0b40`。5 个安装包与 1 个内层 manifest 已重新构建、校验并记录 SHA-256，未发布到任何外部仓库。候选目录为 `C:\codex-artifacts\release-b40-transcripts-keyterms`。

## 尚未关闭的 Corti 能力差距

本阶段没有证明 Corti 私有实现等价、临床准确率或生产就绪。以下仍开放：

1. 尚未用真实 FunASR 和合规中国医疗音频量化 keyterms 对术语召回、CER/WER 的增益，也未与 Corti 使用同一批音频做盲测。
2. 预录音多声道、diarization、多参与者映射、多语言，以及 `automaticPunctuation=false` 的真实 ASR 行为仍未实现。
3. 噪声、方言、长音频、同音医学术语、并发容量、延迟和成本没有 head-to-head 证据。
4. Docker/Linux/PostgreSQL 多副本、区域数据驻留、监控告警、渗透测试及医院验收仍是外部上线门禁。
5. Agent Hub 的严格真实 Provider 语义和临床生产批准仍是 0/26；本阶段只关闭 STT 合同切片，不能改变该结论。

## 安全与数据边界

本阶段显式清空 DeepSeek/OpenAI/项目 LLM 凭证，关闭外部 LLM、本地 STT 和原生 MedCoder，使用临时 SQLite；受保护开发数据库未迁移、未写入。用户曾在对话中暴露的 DeepSeek Key 未被本阶段使用，仍必须在 DeepSeek 控制台撤销并轮换。

机器证据见 `reports/transcripts_keyterms_phase_20260825/phase_evidence.json`，发布物清单见 `reports/transcripts_keyterms_phase_20260825/release_candidate_validation.json`。
