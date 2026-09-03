# iCoDer .NET Standard 2.0 兼容阶段总结（2026-08-27）

## 阶段结论

iCoDer .NET SDK 的开发态源码、NuGet 资产和最低消费者编译差距已关闭。Corti 官方 [SDK Overview](https://docs.corti.ai/sdk/overview) 声明其 .NET SDK 支持 `.NET Framework 4.6.2+` 与 `.NET Standard 2.0`；iCoDer `1.0.0-beta.43` 现在提供 `netstandard2.0`、`net8.0`、`net10.0` 三个资产，并以直接 `netstandard2.0` 消费者和 `.NET Framework 4.6.2` 消费者作为阻断编译门禁。

这只证明工程兼容，不证明 NuGet 已公开发布、真实旧 Framework 进程运行、Corti 托管 API 互操作、临床质量或生产上线。

## 本轮完成

1. SDK 多目标从 `net8.0;net10.0` 扩展为 `netstandard2.0;net8.0;net10.0`。
2. 增加仅在 `netstandard2.0` 使用的 `System.Net.Http.Json` 与 `System.Text.Json` 依赖，以及 required/init 编译属性 polyfill。
3. 集中封装旧目标缺失的 PATCH、参数守卫、随机抖动、Clamp、ASCII token、HttpContent/StreamReader cancellation、WebSocket ArraySegment 与敏感缓冲清零差异；公开 SDK API 未改变。
4. SSE/下载在旧目标通过取消注册主动释放 reader/content，避免把“不带 CancellationToken 的旧 API”误当作不可取消。
5. 新增直接 `netstandard2.0` 与 `net462` compile-only consumer；后者使用官方 Reference Assemblies 包跨平台验证最低 Framework 编译选择。
6. PR CI 与发布候选工作流现在要求：net8/net10 原生测试、两个最低消费者编译、NuGet 三资产精确存在和工件缺失失败关闭。
7. 静态部署预检同步检查 SDK 目标、兼容层、消费者、PR/发布工作流和三资产包门禁。
8. 三种公开 SDK 版本按仓库发布合同同步提升到 `beta.43/b43`；JavaScript/Python 本轮没有 API 行为变化。

## 新鲜验证

权威聚合证据：[`dotnet_sdk_compatibility_20260827`](../../reports/deployment/dotnet_sdk_compatibility_20260827/)

| 门禁 | 结果 |
|---|---:|
| .NET 8 合同测试 | 82/82 passed |
| .NET 10 合同测试 | 82/82 passed |
| `netstandard2.0` consumer | build passed；0 warnings / 0 errors |
| `.NET Framework 4.6.2` consumer | build passed；0 warnings / 0 errors |
| NuGet framework assets | 精确为 netstandard2.0、net8.0、net10.0 |
| 全局静态部署预检 | 110/110 passed |
| SDK 版本合同 | `1.0.0-beta.43` 一致，passed |
| JavaScript 发布元数据 | `npm pack --dry-run` = `1.0.0-beta.43`，58 files |
| Python 发布元数据 | `icoder_sdk-1.0.0b43-py3-none-any.whl` build passed |

候选包未发布：

- `iCoDer.Sdk.1.0.0-beta.43.nupkg`：SHA-256 `1ab84550c5b5bdba313b7cd8171ff429fa65f132ca23afe925c0d3731ad1cc6b`
- `iCoDer.Sdk.1.0.0-beta.43.snupkg`：SHA-256 `327a77a977edbd0c5d4e37a8195de852c54bfad231c0a733a80c1c13af99cf0e`

## 诚实边界与剩余门禁

- `net462` 是编译兼容证据，没有在真实 .NET Framework 4.6.2 进程中跑网络集成测试；当前 Windows 更高 Framework 版本也不能替代最低版本运行证明。
- `netstandard2.0` 的敏感音频数组使用该目标可用的 `Array.Clear`；现代目标继续使用 `CryptographicOperations.ZeroMemory`。两者都不扩大缓存或日志内容，但旧运行时无法提供现代 API 的同级实现保证。
- 本机验证使用 Microsoft 官方非管理员安装方式放置的临时 .NET 8/10 SDK，没有修改系统 PATH 或注册表。
- 验证结束后两个临时 MSBuild node-reuse 进程已精确终止；当前命令安全策略拒绝递归删除，因此 `C:\Temp\icoder-dotnet-sdk-10-20260827` 及本轮几个同名前缀临时文件仍留在磁盘但没有运行进程，不属于项目或发布工件。
- 仍需真实 GitHub Linux CI 成功记录、NuGet 组织/签名/供应链发布权限、托管 API 外网 consumer、旧 Framework 真实宿主集成，以及生产安全和医院验收。
- 本阶段没有读取或外发 CCL 病例内容，没有使用 LLM/API Key，没有调用 Corti credits，也没有改变受保护开发数据库。
