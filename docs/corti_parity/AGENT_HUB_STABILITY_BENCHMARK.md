# Agent Hub 多轮稳定性基准

## 目标与边界

`backend/scripts/corti_parity/run_agent_hub_stability_benchmark.py` 对全部 Hub
可见 Agent 的快乐路径和对抗路径进行重复调用，报告完成率、错误率、P50/P95、
Provider 完成率、输出契约通过率、安全检查通过率，以及按币种分组的成本覆盖率、
总额、均值和 P50/P95。

该报告只证明传输、运行时、输出契约和既有安全断言的重复稳定性，不是临床准确率、
编码准确率或与 Corti 私有模型质量等价的证据。临床质量仍必须使用双方统一的去标识
病例、编码目录版本和独立专家金标准评价。

## 安全设计

- 串行执行并逐响应落盘，可从中断位置恢复；
- 每个新 HTTP Run 同步保存 tenant-scoped、display-safe 的 RunTrace 工件，并在汇总中
  记录响应/Trace SHA-256、Pack 摘要、契约版本、Provider/模型标识和 run/resume/seed 来源；
- 后台分别对公开结果和完整 safe RunTrace 事件列表签发 tenant/run-bound HMAC proof；
  bundle 必须使用同一临时 `ICODER_SECRET_KEY` 验证两类签名，复用真实结果 token 后
  改写 Provider/模型 Trace 也会失败关闭；
- 每次调用前检查进程没有加载 Torch/PyArrow；
- 不在报告中记录 LLM 密钥或 Authorization header；
- 不从源码读取演示密码；只接受 `ICODER_E2E_BEARER`、成对的
  `ICODER_E2E_USERNAME`/`ICODER_E2E_PASSWORD`，或 loopback 隔离数据库上的显式
  `--allow-self-register`；
- 仅在响应明确包含数值 `cost.amount` 和非空 `cost.currency` 时计入成本；显式零成本
  保留为零，缺失或畸形成本标记为 unknown，绝不以零代替；
- 复用现有快乐路径与对抗路径评价器，任何契约、安全或语义断言失败都会计入失败；
- 只有每个 Agent 的两类案例均完成全部重复轮次并全部通过，才标记为 repeatable；
- 默认任何失败都会使命令返回非零状态；
- 报告明确标记 `contract_safety_reliability_not_clinical_accuracy`，防止把工程稳定性
  误写为临床质量。
- `resume` 结果只能用于开发回归，不能进入 live semantic 统计；稳定性第一轮允许使用
  本次新鲜快乐/对抗报告的 byte-identical seed，但 bundle 校验器会逐 Agent 复核来源报告
  哈希、响应哈希及第二轮真实 HTTP Run，任一不一致即失败关闭。

## 本地/人工运行

只能使用未在聊天、日志或版本库暴露的新临时凭证。在启动后端的独立 PowerShell 中
设置 tenant-bound bearer 后运行：

```powershell
$env:ICODER_E2E_BEARER="<temporary-tenant-bearer>"
python backend/scripts/corti_parity/run_agent_hub_stability_benchmark.py `
  --out-dir reports/agent_hub/stability_benchmark `
  --repetitions 3 `
  --delay 1 `
  --timeout 150
```

在没有既有用户的全新本地隔离数据库中，可省略 bearer 并增加
`--allow-self-register`。该开关只接受 loopback URL，禁止对远程或共享环境自动注册。
账号密码方式必须同时设置 `ICODER_E2E_USERNAME` 与 `ICODER_E2E_PASSWORD`；缺一时
runner 会在发出请求前失败关闭。

可用 `--agent-ids` 做小范围复验；正式证据必须覆盖全部 26 个可见 Agent，且不得用
子集结果宣称全量通过。`--max-p95-seconds` 大于零时启用延迟门限；没有双方统一基础
设施与预算前不预设 Corti 等价门限。

## CI 运行

`.github/workflows/ci-integration.yml` 在配置 `ICODER_CREDENTIAL_LLM` 时先执行 26 个
快乐案例和 26 个对抗案例，再把这 52 个已验证的新鲜响应作为稳定性基准第一轮种子，
仅新增一轮真实调用，形成 26 × 2 × 2 = 104 条观测。bundle 校验器会把 seed 逐条绑定
到同一工件中的新鲜来源报告，不能使用历史缓存替代。随后 CI 完成参考语义回放、生成
语义证据 bundle，并用该 bundle 重新生成运行矩阵；任一步失败都会阻断作业。CI 后端
固定在 loopback 隔离 PostgreSQL，报告随 `agent-hub-live-e2e` 工件上传。

未配置凭证时 CI 只运行离线 Pack/矩阵/基准器单元测试，并生成明确的 live-E2E 跳过
工件，不允许以 mock 或缓存结果冒充新的真实模型基准。

## 新临时 DeepSeek 凭证的受控全量复测

此前在聊天或日志中出现过的密钥不得再次使用。先在 DeepSeek 控制台撤销旧密钥，
再创建一个有明确余额/预算、只用于本次合成测试的新临时密钥。密钥只在用户可见的
独立 PowerShell 中输入，不粘贴到 Codex、项目文件、命令历史、日志或报告。

后端 PowerShell 使用临时 SQLite 和非 8000 loopback 端口：

```powershell
Set-Location E:\Corti4C
$env:ICODER_SECRET_KEY = [Convert]::ToBase64String(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
)
# 先打开 runner 窗口；它只继承测试 attestation key，此时尚未设置 LLM key。
Start-Process powershell.exe -ArgumentList '-NoExit','-Command','Set-Location E:\Corti4C'
$secureKey = Read-Host "DeepSeek temporary API key" -AsSecureString
$keyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
  $env:ICODER_CREDENTIAL_LLM = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPtr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPtr)
}
$tempDb = Join-Path $env:TEMP ("icoder-agent-quality-" + [guid]::NewGuid().ToString("N") + ".db")
$env:DATABASE_URL = "sqlite+aiosqlite:///" + $tempDb.Replace("\", "/")
$env:SEED_ON_STARTUP = "0"
.\backend\scripts\start_visible_deepseek_e2e_backend.ps1 -Port 18022
```

保持后端窗口可见，在刚才打开、已继承同一 `ICODER_SECRET_KEY` 的第二个 PowerShell
中串行执行；目录名必须是新的时间戳，禁止覆盖历史证据。若 runner 与后台没有共享
该临时 attestation key，bundle 会因 HMAC 签名不可验证而失败关闭：

```powershell
Set-Location E:\Corti4C
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$happy = "reports/agent_hub/live_quality_$stamp/happy"
$adversarial = "reports/agent_hub/live_quality_$stamp/adversarial"
$stability = "reports/agent_hub/live_quality_$stamp/stability"
$reference = "reports/agent_hub/live_quality_$stamp/reference"
$bundle = "reports/agent_hub/live_quality_$stamp/semantic-evidence"
$runtime = "reports/agent_hub/live_quality_$stamp/runtime"

python backend/scripts/corti_parity/run_agent_hub_examples_e2e.py `
  --base-url http://127.0.0.1:18022 --out-dir $happy `
  --allow-self-register --delay 1 --timeout 150
if ($LASTEXITCODE -ne 0) { throw "happy E2E failed" }

python backend/scripts/corti_parity/run_agent_hub_adversarial_e2e.py `
  --base-url http://127.0.0.1:18022 --out-dir $adversarial `
  --allow-self-register --delay 1 --timeout 150
if ($LASTEXITCODE -ne 0) { throw "adversarial E2E failed" }

python backend/scripts/corti_parity/run_agent_hub_stability_benchmark.py `
  --base-url http://127.0.0.1:18022 --out-dir $stability `
  --happy-seed-dir $happy --adversarial-seed-dir $adversarial `
  --allow-self-register --repetitions 2 --delay 1 --timeout 150
if ($LASTEXITCODE -ne 0) { throw "stability benchmark failed" }

python backend/scripts/corti_parity/run_agent_hub_reference_quality_replay.py `
  --responses-dir "$happy/responses" `
  --source-report "$happy/agent_hub_examples_e2e.json" `
  --out-dir $reference
if ($LASTEXITCODE -ne 0) { throw "reference quality replay failed" }

python backend/scripts/corti_parity/build_agent_hub_semantic_evidence_bundle.py `
  --examples "$happy/agent_hub_examples_e2e.json" `
  --adversarial "$adversarial/agent_hub_adversarial_e2e.json" `
  --reference "$reference/agent_hub_reference_quality_replay.json" `
  --stability "$stability/agent_hub_stability_benchmark.json" `
  --out-dir $bundle
if ($LASTEXITCODE -ne 0) { throw "semantic evidence bundle failed" }

python backend/scripts/corti_parity/build_agent_hub_runtime_matrix.py `
  --output-dir $runtime `
  --semantic-evidence "$bundle/agent_hub_semantic_evidence_bundle.json" `
  --assert-visible-ready
if ($LASTEXITCODE -ne 0) { throw "semantic runtime matrix failed" }
```

完成后在后端窗口按一次 `Ctrl+C` 并等待 Uvicorn 退出；不要直接关闭窗口或用任务管理器
结束父 PowerShell。随后在该后端窗口清除环境变量并删除仅由本次命令创建的临时库：

```powershell
Get-NetTCPConnection -LocalPort 18022 -State Listen -ErrorAction SilentlyContinue
Remove-Item Env:ICODER_CREDENTIAL_LLM -ErrorAction SilentlyContinue
Remove-Item Env:ICODER_SECRET_KEY -ErrorAction SilentlyContinue
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:SEED_ON_STARTUP -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $tempDb -ErrorAction SilentlyContinue
Remove-Item -LiteralPath ($tempDb + "-wal") -ErrorAction SilentlyContinue
Remove-Item -LiteralPath ($tempDb + "-shm") -ErrorAction SilentlyContinue
```

runner 窗口也应执行 `Remove-Item Env:ICODER_SECRET_KEY -ErrorAction SilentlyContinue`。

最后在 DeepSeek 控制台撤销该临时密钥。只有快乐、对抗、稳定性和参考语义四类报告
都完整覆盖 26 个 Agent，且 bundle 与带语义证据的运行矩阵均成功，才可作为当前
Provider 合成回归证据。旧 v1/v2、mock、safe-fail-only、resume、过期、部分覆盖、
Pack 摘要不一致、缺少非 mock 模型遥测或被改写的工件都保持 0/26；即使全绿，也仍
不是独立临床金标准或 Corti 临床质量等价证明。
