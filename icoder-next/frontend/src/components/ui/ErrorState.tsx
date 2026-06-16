import { ApiError } from "../../services/api";
import { Card, CardBody } from "./Card";
import { Button } from "./Button";

// Turns a thrown error into an actionable panel. Network/credential/permission failures
// each get a plain-language hint; everything else falls back to the raw message. When a
// retry handler is supplied we show a button rather than leaving the user stuck.
function describe(err: unknown): { title: string; hint?: string } {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 0:
        return { title: "无法连接后端", hint: "请确认 iCoDer 服务正在运行（开发环境：uvicorn 监听 :8000）。" };
      case 401:
        return { title: "未授权", hint: "登录令牌无效或缺失，请检查右上角登录身份。" };
      case 403:
        return { title: "权限不足", hint: "该操作需要 coder 或 admin 角色。" };
      case 404:
        return { title: "未找到", hint: "请求的智能体或运行记录不存在。" };
      case 409:
        return { title: "配置缺失", hint: err.message || "规则集或 Expert 未注册，运行时已拒绝执行。" };
      case 503:
        return {
          title: "服务未就绪",
          hint:
            err.code === "llm_credential_missing"
              ? "LLM 凭据缺失（llm_credential_missing）。请配置 ICODER_CREDENTIAL_LLM 后重试。"
              : err.message || "后端依赖暂不可用。",
        };
      default:
        return { title: `加载失败（${err.status}）`, hint: err.message };
    }
  }
  return { title: "加载失败", hint: err instanceof Error ? err.message : String(err) };
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const { title, hint } = describe(error);
  return (
    <Card className={className}>
      <CardBody className="flex flex-col items-start gap-3">
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-300"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </span>
          <div role="alert">
            <p className="text-sm font-semibold text-ink">{title}</p>
            {hint && <p className="mt-1 text-sm leading-relaxed text-muted">{hint}</p>}
          </div>
        </div>
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            重试
          </Button>
        )}
      </CardBody>
    </Card>
  );
}
