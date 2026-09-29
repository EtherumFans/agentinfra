# API Client与浏览器集成（当前实现）

API客户端用于机器身份；Console用户JWT是另一种身份。当前OAuth token端点仅支持`client_credentials`，不支持ROPC或`grant_type=password`。

在Console“API客户端”创建客户端时，配置名称、说明、scope、允许的Agent与用途。凭据只交给受信任的服务端保管，不嵌入浏览器脚本。机器调用的组织、Client及费用归属由已验证的令牌与服务器授权确定，浏览器项目选择或请求体不能覆盖它。

Scope以当前创建表单、OpenAPI和服务端允许列表为准，Agent执行还要满足用途授权。不要复制旧设计稿中的未核实scope示例。Token有效期、issuer、audience和刷新政策以部署配置及实际响应为准。

浏览器嵌入使用现有受控短期会话/预览票据流程，患者上下文经受保护通道传递，不放入iframe URL。预览成功不代表医院SSO、患者主索引、签名归档或生产写回已经验收。

云租户域名、地区与SLA是交付配置及验收事项；模板地址不是已开通服务。完整授权API契约见运行服务的`/openapi.json`与`/docs`。
