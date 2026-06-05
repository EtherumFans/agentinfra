/** Map backend error codes to user-readable Chinese messages. */

const ERROR_MAP: Record<string, string> = {
  LLM_PROVIDER_NOT_CONFIGURED: 'LLM 模型服务未配置，请联系管理员',
  AGENT_NOT_FOUND: 'Agent 未安装到 Runtime，请先点击「Install to Runtime」',
  VALIDATION_ERROR: 'Agent 包校验失败',
  INSTALL_ERROR: '安装失败，请检查 Agent 包格式',
  RUNTIME_CONFIGURATION_ERROR: 'Runtime 配置错误，请联系管理员',
  PROVIDER_ERROR: '模型服务调用失败，请稍后重试',
  MARKETPLACE_ERROR: 'Marketplace 服务异常',
  DataPolicyViolation: '数据安全策略阻止了外部模型调用',
  external_llm_blocked: '外部 LLM 调用已被数据安全策略阻止',
  agent_disabled: 'Agent 已被禁用，请先启用后再运行',
  tier3_approval_required: 'Agent 安全等级为 Tier 3，需管理员审批后才能启用',
  tier4_blocked: 'Agent 安全等级为 Tier 4，默认禁止运行',
  network_error: '网络连接失败，请检查服务是否启动',
  unauthorized: '未登录或登录已过期，请重新登录',
};

/** Convert a backend error detail to a user-friendly Chinese message. */
export function toUserMessage(err: unknown): string {
  if (!err) return '未知错误';

  // Axios error with response data
  if (typeof err === 'object' && err !== null) {
    const e = err as Record<string, unknown>;

    // Check response data
    const resp = e.response as Record<string, unknown> | undefined;
    if (resp) {
      const data = resp.data as Record<string, unknown> | undefined;
      if (data) {
        // Structured error: { code: "...", detail: "..." }
        const code = (data.code || data.error || '') as string;
        const detail = (data.detail || data.message || '') as string;

        if (code && ERROR_MAP[code]) return ERROR_MAP[code];

        // Detail might be an object with errors array
        if (typeof detail === 'object' && detail !== null) {
          const d = detail as Record<string, unknown>;
          if (Array.isArray(d.errors)) return (d.errors as string[]).join('; ');
        }
        if (typeof detail === 'string' && detail) {
          // Try to match known patterns
          for (const [key, msg] of Object.entries(ERROR_MAP)) {
            if (detail.includes(key)) return msg;
          }
          return detail;
        }
      }

      // HTTP status
      const status = resp.status as number;
      if (status === 401 || status === 403) return ERROR_MAP.unauthorized;
      if (status === 503) return '服务暂不可用，请稍后重试';
    }

    // Error message matching
    const msg = (e.message || '') as string;
    for (const [key, val] of Object.entries(ERROR_MAP)) {
      if (msg.includes(key)) return val;
    }
    if (msg && msg !== 'Request failed') return msg;
  }

  // String error
  if (typeof err === 'string') {
    for (const [key, val] of Object.entries(ERROR_MAP)) {
      if (err.includes(key)) return val;
    }
    return err;
  }

  return '操作失败，请稍后重试';
}
