# Windows 原生 AI/数据依赖运行安全门禁

> 状态：开发环境安全说明，2026-08-10（Asia/Shanghai）  
> 适用范围：Windows 上的本地 MedCodER BGE-M3/FAISS 检索进程，以及可能加载 PyArrow 的数据工具

## 已证实故障

当前开发机曾在测试启动应用 lifespan 时发生 Python 原生崩溃。Windows Error Reporting 的可用证据为：

- 故障进程：`python.exe`
- 故障模块：`torch_cpu.dll`
- 异常代码：`0xc0000005`（内存访问冲突）
- 已安装组合：`torch 2.11.0`、`sentence-transformers 3.2.1`、`faiss-cpu 1.9.0`、`numpy 1.26.4`

Minidump 的 ExceptionStream 已确认：该 `torch_cpu.dll` 故障是读访问冲突，目标地址为 `0x2DC79A60`。2026-08-13 的另一组崩溃来自 `pyarrow 24.0.0` 的 `arrow.dll`：同一 Python 进程先发生写访问冲突（目标 `0x66F`），随后发生读空地址冲突（目标 `0x0`）。Python 无法捕获进程内的这类原生访问冲突，重复运行可能同时终止测试进程和 Codex 桌面宿主。

崩溃后还发现 7 个父进程已经消失的 `multiprocessing.spawn` 子进程，占用约 1.34 GB 工作集。它们已按精确 PID 清理，未终止其他用户进程。

## 当前保护

`icoder_runtime.providers.medical_coding.runtime_safety.assess_bge_runtime_safety()` 使用包元数据判断风险，不导入 PyTorch。对于上述 Windows 组合，应用将失败关闭：

- 不启动 BGE/FAISS worker；
- `/api/health` 暴露 `medcoder_index_ready=false` 与明确错误原因；
- MedCodER 默认检索器不导入不安全的原生栈；
- 正常 shutdown 主动关闭 worker；
- worker 监听父进程管道，父进程异常退出后自行结束，避免孤儿进程。

`MEDCODER_SUBPROCESS=1` 只表示隔离运行，不等于接受已知不安全依赖，因此不会绕过门禁。

`assess_pyarrow_runtime_safety()` 同样只读取包元数据、不导入 PyArrow。当前开发机上的 `pyarrow 24.0.0` 在 Windows 默认失败关闭；项目常规后端并不要求 PyArrow，因此不应为了普通测试加载它。只有与 Codex 分离、可丢弃的隔离进程可以在明确接受风险后设置 `ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW=1`。

## 操作要求

推荐的生产等价路径是使用经过锁定和验证的 Linux 检索服务，将 BGE/FAISS 与 API 进程隔离，并对模型、索引、依赖镜像和健康探针做版本化。该路径现已形成开发部署候选：

- 主 API 镜像只安装 `requirements-api.txt`，不安装或导入 Torch、FAISS、SentenceTransformers、PyArrow；
- `medcoder-retriever` 使用独立 `Dockerfile.ml`、单 Uvicorn worker、非 root 用户和内部端口，不暴露宿主端口；
- API 与 worker 之间使用 Bearer 服务凭证、严格版本化 JSON 契约、超时和失败关闭；
- worker 启动时先核对 `asset_manifest.json`，逐项验证四个索引/元数据文件的大小与 SHA-256，再允许导入原生 ML；
- BGE-M3 固定到 revision `5617a9f61b028005a4858fdac845db406aefb181`，容器默认 `local_files_only`、Hugging Face/Transformers 离线；
- `/readyz` 只有两个编码系统都完成索引加载和推理预热后才返回 200，否则返回 503；
- 当前开发机没有 Docker CLI，因此以上已有静态配置、契约、资产完整性和无原生导入回归证据，但尚无本机镜像构建/启动证据。

具备 Docker 的 Linux 开发机可按以下方式启动；必须先通过密钥管理生成独立 worker token，不得复用 LLM 密钥：

```bash
export MEDCODER_RETRIEVER_TOKEN='<32-512 字符随机服务凭证>'
docker compose \
  -f docker-compose.local-dev.yml \
  -f docker-compose.medcoder.yml \
  up -d --build medcoder-retriever backend
curl -fsS http://localhost:8000/api/health
```

不要只运行旧的 `--profile ml` 命令：它会启动 Worker，但不会自动把 Backend 的 `MEDCODER_RETRIEVER_URL` 指向该服务。overlay 同时提供 URL、仅限 Compose 内网的 HTTP 许可、原生栈禁用和健康依赖，并在缺少独立 Worker token 时失败关闭。

也可以先在独立 Windows 测试机验证兼容的 PyTorch/sentence-transformers 构建，再更新允许矩阵，但不得在 Codex 宿主进程内试载。

仅在一次性、可丢弃、与 Codex 分离的测试环境中，且操作者明确接受原生崩溃风险时，才可设置对应覆盖项：

```powershell
$env:MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE='1'
$env:ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW='1'
```

不得在常规开发、CI 或生产配置中设置该变量，也不得用它证明 MedCodER 语义检索已达到上线标准。

## 低风险验证

常规回归应按目录或能力拆批运行，并在每批之后确认没有残留 worker。不要为了复现异常而导入当前不安全的 `torch_cpu.dll` 组合。

可通过以下只读命令检查疑似 worker；只有在确认父进程已经不存在且 PID 精确匹配后，才允许单独终止：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'multiprocessing\.spawn' } |
  Select-Object ProcessId, ParentProcessId, CommandLine
```

发布证据必须区分：安全门禁测试通过、静态部署候选通过、检索服务真实启动、索引质量评测、医院临床验证。前两者不能替代后三者。
