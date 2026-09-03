# iCoDer Streams keyterms 与当前字段合同阶段总结（2026-08-25）

## 阶段结论

Corti 2026-08-25 可访问的当前 Streams 文档显示：`diarize` 是现行字段，旧 `isDiarization` 仍兼容；`keyterms.terms` 是正式公开配置，按顺序且大小写敏感，最多 1,000 项，每项最多 50 字符。仓库在上一阶段仍序列化旧字段并对所有非空 keyterms 返回 `session_keyterms_not_available`，属于明确的合同漂移。

本阶段已经关闭该开发环境缺口：服务端与三 SDK 接受当前 `diarize`，仍兼容旧输入别名；Streams keyterms 经过一致的数量/长度门禁后，以原始顺序和大小写传入 FunASR `hotword` 运行参数。日志和 STT 遥测不保存词项内容，配置审计只保存 `keyterm_count`。Diarization 仍失败关闭，避免把未经资格验证的本机启发式或 native 模型冒充 Corti 临床能力。

该结论只证明合同、参数转发、边界、安全性、三 SDK 与 loopback E2E；测试关闭了真实 ASR，因此不证明 keyterms 实际提高识别率，也不证明与 Corti 的同音频质量等价。

## 官方依据

- Corti Streams 当前配置以 `diarize` 启用单声道说话人分离，并注明 legacy `isDiarization` 仍接受。
- `keyterms.terms` 是有序、大小写敏感的识别词项；单项最长 50 字符，列表最多 1,000 项。
- diarization 打开时 transcript 可在同一消息中包含不同 speaker 的 segments，并需按 `time.start` 排序。

来源：<https://docs.corti.ai/api-reference/streams>（2026-08-25 读取）。

## 实现范围

1. Pydantic 继续接受 `diarize`/`isDiarization` 两种输入，但 CONFIG_ACCEPTED 使用当前 `diarize` 输出。
2. 非空 keyterms 不再被配置阶段拒绝；服务端模型仍强制 1–1,000 项、每项 1–50 字符。
3. Streams mono 与每个 multichannel 声道都收到相同的不可变 keyterms tuple。
4. FunASR batch inference 仅在确有 keyterms 时加入 `hotword=[...]`；无 keyterms 的预录音和 Streams 路径保持原签名与行为。
5. 如果 FunASR 不可用且批准的 Whisper 回退开启，词项进入 `initial_prompt`；没有批准本地 STT 时仍返回真实 `STT_UNAVAILABLE`。
6. 三 SDK 在开 WebSocket 前拒绝超过 1,000 项、空词项或超过 50 字符的词项；顺序和大小写不改写。
7. 真实 loopback 的双声道 fast_init 配置加入 `房颤` 与 `Corti Health`，验证 CONFIG_ACCEPTED 精确保留当前字段和 keyterms，之后因 STT 被安全关闭而返回 `STT_UNAVAILABLE`。
8. 发布候选升至 JavaScript/.NET `1.0.0-beta.38`、Python `1.0.0b38`；本机生成哈希，未发布。

## 回归与整改

第一次后端全量为 5,563 passed、4 failed。四个失败均来自同一个兼容性错误：预录音遥测包装器在空 keyterms 时仍向旧测试替身传入新关键字。修复为“只有非空时才传参”后，相关范围 67/67，最终后端全量为 **5,568 passed、20 skipped、11 deselected、0 failed**，耗时 1,590.14 秒。

其余权威结果：

- Streams API/边界：40/40。
- JavaScript SDK：95/95。
- Python SDK：101/101。
- .NET SDK：net8.0 82/82，net10.0 82/82。
- 部署候选预检：95/95。
- 真实 loopback WebSocket：三 SDK、malformed media、单声道 audio events、多声道/fast_init/keyterms 全部通过。
- 发布验证器：版本一致，六个工件进入带 SHA-256 的非发布清单。
- 两次本阶段后端全量均没有进程崩溃；最终权威轮全绿。此前 `uvicorn -1` 仍不能仅凭不同时间的 PyArrow 事件归因。

证据：

- `reports/streams_keyterms_phase_20260825/phase_evidence.json`
- `reports/streams_keyterms_phase_20260825/full_backend_remediated_junit.xml`
- `reports/streams_keyterms_phase_20260825/loopback_e2e.json`
- `reports/deployment/streams_keyterms_phase_20260825/deployment_preflight.json`
- `reports/streams_keyterms_phase_20260825/release_candidate_validation.json`

## 仍未关闭的 Corti 差距

1. Diarization 仍未实现上线候选。Corti 会自动分配 speakerId；iCoDer 当前在 diarize=false 时诚实返回 `speakerId=-1`，diarize=true 失败关闭。
2. 没有真实去标识中国医疗音频的 keyterm A/B 评测，无法声明召回率、误替换率或 Corti 等价。
3. iCoDer 当前只验证中文服务端 ASR 路径；Corti 的多语言、方言、噪声、多人重叠、长音频、延迟、并发、usage/billing 和 SLA 仍开放。
4. Corti 在声明 participant channels 与检测声道不一致时公开描述为 warning；iCoDer 当前为医疗安全选择配置阶段失败关闭，这是有意的更严格差异，不是线协议完全等价。
5. 登录态 Corti 控制台本阶段因浏览器运行组件缺失未能重新读取；本结论依据当天官方公开文档，不覆盖私有 UI 或租户特性。
6. Agent Hub 严格 live-provider 仍为 0/26，CDI/Medical Coding 多病例真实运行仍为 0/50，临床与生产验收仍为 0/26。

## 安全与凭证

测试期间清除了 `ICODER_CREDENTIAL_LLM`、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`，关闭 external LLM、本地 STT 和 native medcoder，所有后端/E2E 使用临时 SQLite。受保护开发数据库保持 8,536,064 bytes、2026-08-22 17:16:22、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。先前在对话中公开的 DeepSeek Key 仍必须撤销；本阶段未使用。
