# 本地开发快速开始

当前版本用于开发和受控验证。

当前本地产品审核服务已统一到 PostgreSQL，启动与恢复记录见 [PostgreSQL 环境统一验收](reports/POSTGRESQL_UNIFICATION_2026-09-09.md)。下文 SQLite 步骤用于新建轻量开发环境，不用于重启现有产品审核库。PostgreSQL 必须先执行 Alembic 至当前版本，配置 PHI 密钥，并以受限应用账号启动；后端不会自动创建 PostgreSQL 表。

### 2.2 本地开发准备

依赖基线来自仓库：Python 3.11+；Node版本须满足锁定Vite版本的engines要求，不能将任意Node 20版本视为兼容。以锁文件及API requirements为准。本次实际运行是Windows 11、Python 3.12.14、Node 24.19.0，复用已有依赖，**未重新执行干净依赖安装**。

如已有Python环境和前端依赖，直接进入下一步。若需自行准备，在仓库根目录用独立venv，按以下源码清单安装；这部分是依据manifest的安装说明，不是本次新执行的安装证明：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-api.txt
Set-Location frontend
npm ci --legacy-peer-deps
```

API依赖默认不包含全部ASR/FAISS/模型工作器；安装API不意味着语音、深度检索和所有模型都已就绪。网络代理仅在任务进程按需要设置；不要套用本机旧Git全局代理。

### 2.3 两个终端启动

终端A，从仓库根目录进入backend。先准备一个只用于开发的新数据库目录：

```powershell
Set-Location backend
New-Item -ItemType Directory -Force ../artifacts/local-demo | Out-Null
$demoDir = (Resolve-Path ../artifacts/local-demo).Path.Replace('\','/')
$env:DATABASE_URL = "sqlite+aiosqlite:///$demoDir/demo.db"
$env:ICODER_DATABASE_URL = $env:DATABASE_URL
$env:APP_ENV = 'development'
$env:ICODER_DEPLOYMENT_MODE = 'local'
$env:ICODER_ALLOW_DEGRADED_NO_KEY = '0'
$env:ICODER_CREDENTIAL_LLM = ''
$env:LLM_API_KEY = ''
$env:ICODER_ALLOW_EXTERNAL_LLM = 'false'
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`APP_ENV=development` 会触发开发seed；默认 `APP_ENV=local` 且 `SEED_ON_STARTUP=false` 时不能假设演示账户已创建。配置类默认读取当前工作目录 `.env`；单纯复制根目录 `.env.cloud.example` 为 `.env.cloud` 并不会让这里自动读取它。[配置](https://github.com/EtherumFans/agentinfra/blob/b8357ba22b1035a3bbb7bcafb2d9cf4871b746c8/backend/app/config.py#L752)、[seed条件](https://github.com/EtherumFans/agentinfra/blob/b8357ba22b1035a3bbb7bcafb2d9cf4871b746c8/backend/app/main.py#L143)。

终端B，从仓库根目录进入frontend：

```powershell
Set-Location frontend
$env:VITE_API_TARGET = 'http://127.0.0.1:8000'
npm run dev -- --host 127.0.0.1 --port 3000 --strictPort
```

浏览器访问 [本地Console](http://localhost:3000)，API文档为 [Swagger](http://127.0.0.1:8000/docs)，健康检查为 [health](http://127.0.0.1:8000/api/health)。当前Vite默认端口是3000，不是旧QUICKSTART中的5173；80只对应特定容器前端。

如使用其他浏览器来源，例如本次审查的 `http://127.0.0.1:13000`，在后端启动前将 `CORS_ORIGINS` 精确设为该来源的JSON数组。`localhost` 与 `127.0.0.1` 不是相同Origin。仅更换Vite端口可能使登录成功、Agent运行却403；本次已复现并通过正确CORS配置解决。[Partner CORS](https://github.com/EtherumFans/agentinfra/blob/b8357ba22b1035a3bbb7bcafb2d9cf4871b746c8/backend/app/middleware/partner_cors.py#L1)

本次审查实例实际使用18000/13000和全新的审查数据库，因沙箱限制采用审查副本及授权后的前端进程；普通环境无需照抄该工作区的依赖路径。Docker在本机未能验证，因此不把Docker启动列为已亲测路径。

### 2.4 怎样知道服务真的可用

`/api/health`返回200只表示服务可响应。还要检查 `medcoder_index_ready`、解码器、Connector状态和Hub的租户readiness。启动日志显示“real wiring”也不代表模型key/FAISS/ASR已经就绪。

本次状态：API和本地完整性规则可用；LLM无凭据；FAISS index缺失；语音页显示引擎未配置、加密存储未启用。没有尝试付费模型或下载大模型。


登录后选择“AI智能体 → iCoDer预置 → 病历完整性 → 使用”，克隆到当前组织后运行合成文本，再查看运行记录与RunTrace。本地规则不需要外部模型，规则通过仍需人工复核。当前不需要Install to Runtime，也没有Marketplace发布流程。

单轮任务入口只提交本轮输入与附件；智能体详情页支持多轮Context。顶部名称与客户端选择仅是显示偏好，不创建独立项目授权或预算。
