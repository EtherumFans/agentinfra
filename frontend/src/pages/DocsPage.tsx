// iCoDer Documentation Hub
import { BookOpen, Code, Key, Mic, FileText, Sparkles, Terminal, Puzzle, Stethoscope, ExternalLink } from 'lucide-react';
import { useT } from '../i18n';
import { BACKEND_BASE_URL } from '../config';

const SDK_CARDS = [
  { icon: Code, title: 'JavaScript SDK', desc: 'Node.js + 浏览器。全 REST + WebSocket 支持。', cmd: 'npm install @icoder/sdk', href: '#js-sdk' },
  { icon: Terminal, title: 'Python SDK', desc: 'Python 3.9+。httpx 异步 HTTP 客户端。', cmd: 'pip install icoder-sdk', href: '#python-sdk' },
  { icon: Code, title: 'C# .NET SDK', desc: '.NET 8+。async/await + WebSocket。', cmd: 'dotnet add package iCoDer.Sdk', href: '#dotnet-sdk' },
  { icon: Puzzle, title: 'Web Components', desc: '零依赖。任意 HTML 页面一行标签嵌入。', cmd: 'npm install @icoder/web', href: '#web-components' },
];

const API_SECTIONS = [
  { icon: Mic, title: 'Speech To Text', path: '/api/speech-to-text', desc: '实时语音识别，中英混合，语音指令', method: 'POST / WS' },
  { icon: FileText, title: 'Fact Extraction', path: '/api/facts/extract', desc: '临床文本→结构化事实', method: 'POST' },
  { icon: FileText, title: 'Text Generation', path: '/api/text-gen/generate', desc: '13 模板 LLM 文书生成', method: 'POST' },
  { icon: Stethoscope, title: 'Medical Coding', path: '/api/reviews', desc: 'ICD-10-CN / ICD-9-CM-3 编码', method: 'POST' },
  { icon: Sparkles, title: 'Agentic Framework', path: '/api/agents', desc: '智能体创建/管理/流式对话', method: 'POST / GET / SSE' },
  { icon: Key, title: 'Authentication', path: '/api/auth/login', desc: 'JWT + OAuth 2.0 + PKCE', method: 'POST' },
  { icon: Puzzle, title: 'Embedded Assistant', path: '/api/embedded', desc: 'Web Component 嵌入', method: 'GET' },
];

export default function DocsPage() {
  const t = useT();

  return (
    <div className="flex h-full bg-muted/20">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-8">
          {/* Header */}
          <div className="mb-10">
            <h1 className="text-2xl font-bold text-foreground mb-2">iCoDer 开发者文档</h1>
            <p className="text-sm text-muted-foreground max-w-2xl">
              iCoDer — 可审计的临床AI。预置编码审核、语音转录、文书生成、事实提取和AI智能体。通过SDK、Web Components或REST API嵌入您的HIS/EMR系统。
            </p>
            <div className="flex items-center gap-3 mt-4">
              <a href={`${BACKEND_BASE_URL}/docs`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors">
                <BookOpen size={14} /> OpenAPI 规范 (Swagger)
              </a>
              <a href={`${BACKEND_BASE_URL}/redoc`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-accent transition-colors">
                <ExternalLink size={14} /> ReDoc
              </a>
              <a href="/developer-quickstart?tab=api-playground"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-accent transition-colors">
                <ExternalLink size={14} /> Postman Collection
              </a>
              <a href="/release-notes"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-accent transition-colors">
                <ExternalLink size={14} /> Release Notes
              </a>
            </div>
          </div>

          {/* SDK Section */}
          <div className="mb-10">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1 h-5 rounded-full bg-primary/40" />
              <h2 className="text-lg font-semibold text-foreground">SDK & 工具</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {SDK_CARDS.map(card => (
                <div key={card.title} className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <card.icon size={18} className="text-primary" />
                    <h3 className="text-sm font-semibold text-foreground">{card.title}</h3>
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">{card.desc}</p>
                  <code className="block text-xs font-mono bg-muted px-3 py-2 rounded-lg text-foreground select-all">{card.cmd}</code>
                </div>
              ))}
            </div>
          </div>

          {/* API Reference */}
          <div className="mb-10">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1 h-5 rounded-full bg-primary/40" />
              <h2 className="text-lg font-semibold text-foreground">API 参考</h2>
            </div>
            <div className="space-y-2">
              {API_SECTIONS.map(api => (
                <div key={api.path} className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4 flex items-center gap-4">
                  <api.icon size={18} className="text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-foreground">{api.title}</h3>
                    <p className="text-xs text-muted-foreground">{api.desc}</p>
                  </div>
                  <span className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-1 rounded shrink-0">{api.method}</span>
                  <code className="text-xs font-mono text-foreground/70 shrink-0">{api.path}</code>
                </div>
              ))}
            </div>
          </div>

          {/* Quickstart */}
          <div className="mb-10">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1 h-5 rounded-full bg-primary/40" />
              <h2 className="text-lg font-semibold text-foreground">5 分钟快速开始</h2>
            </div>
            <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-6">
              <div className="space-y-6">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-[11px] font-bold text-primary-foreground">1</div>
                    <h3 className="text-sm font-semibold text-foreground">获取 API 凭据</h3>
                  </div>
                  <p className="text-xs text-muted-foreground ml-8">在 iCoDer Console 注册，进入 API 客户端页面创建 OAuth 客户端，保存 Client ID 和 Client Secret。</p>
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-[11px] font-bold text-primary-foreground">2</div>
                    <h3 className="text-sm font-semibold text-foreground">安装 SDK</h3>
                  </div>
                  <div className="ml-8 space-y-1">
                    <code className="block text-xs font-mono bg-muted px-3 py-2 rounded-lg">npm install @icoder/sdk</code>
                    <span className="text-[11px] text-muted-foreground">或 pip install icoder-sdk</span>
                  </div>
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-[11px] font-bold text-primary-foreground">3</div>
                    <h3 className="text-sm font-semibold text-foreground">发起第一个 API 调用</h3>
                  </div>
                  <pre className="ml-8 text-xs font-mono bg-muted p-4 rounded-lg overflow-x-auto text-foreground whitespace-pre-wrap">{`import iCoDer from '@icoder/sdk';

const icoder = new iCoDer({
  baseURL: '${BACKEND_BASE_URL}',
  auth: { accessToken: '<token>', refreshToken: '<refresh>' },
});

// 提取临床事实
const facts = await icoder.facts.extract(
  '患者因腰痛伴左下肢放射痛3月就诊。MRI示L4/5椎间盘突出。',
  'zh-CN'
);
console.log(facts.facts.diagnosis_facts);`}</pre>
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="border-t border-border pt-6 text-xs text-muted-foreground">
            <p>需要帮助？ <a href="/support" className="text-primary hover:underline">联系支持</a> 或 <a href="/developer-quickstart" className="text-primary hover:underline">开发者快速入门</a></p>
          </div>
        </div>
      </div>
    </div>
  );
}
