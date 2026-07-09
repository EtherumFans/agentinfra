// iCoDer Developer Quickstart - iCoDer-style with i18n
import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Key, BookOpen, Copy, Check, Terminal, ChevronRight, Loader2, Bot, Mic, FileEdit, Stethoscope, Play } from 'lucide-react';
import { oauthApi } from '../services/api';
import { useT } from '../i18n';

type AiTool = 'claude' | 'cursor' | 'codex' | 'lovable';
type UseCase = 'dictation' | 'scribe' | 'coding' | 'chat';
type MainTab = 'ai-tools' | 'js-sdk' | 'dotnet-sdk' | 'api-playground';

const AI_TOOLS: { key: AiTool; label: string }[] = [
  { key: 'claude', label: 'Claude Code' }, { key: 'cursor', label: 'Cursor' }, { key: 'codex', label: 'Codex' }, { key: 'lovable', label: 'Lovable' },
];

const API_ENDPOINTS: { key: string; method: string; path: string; label: string; sampleBody: string | null }[] = [
  { key: 'facts-extract', method: 'POST', path: '/api/v2/tools/extract-facts', label: 'POST /api/v2/tools/extract-facts', sampleBody: JSON.stringify({ context: { type: 'text', text: '患者因腰痛伴左下肢放射痛3月就诊。查体：腰椎活动受限，左下肢直腿抬高试验阳性。' }, outputLanguage: 'zh-CN' }, null, 2) },
  { key: 'agents-run', method: 'POST', path: '/api/icoder/agents/medcoder-coding-review/v1/message:send', label: 'POST /api/icoder/agents/{id}/v1/message:send (A2A)', sampleBody: JSON.stringify({ jsonrpc: '2.0', id: 'q-1', method: 'message/send', params: { message: { role: 'user', parts: [{ type: 'text', text: '请根据以下病例提供ICD-10-CN编码建议。' }] } } }, null, 2) },
  { key: 'coding', method: 'POST', path: '/api/v2/tools/coding/icoder/', label: 'POST /api/v2/tools/coding/icoder/', sampleBody: JSON.stringify({ input: { case_id: 'case-xxx', text: '主诉：腹痛...' } }, null, 2) },
  { key: 'usage', method: 'GET', path: '/api/usage/summary', label: 'GET /api/usage/summary', sampleBody: null },
];

export default function DeveloperQuickstartPage() {
  const t = useT();
  const [searchParams] = useSearchParams();
  const [mainTab, setMainTab] = useState<MainTab>((searchParams.get('tab') as MainTab) || 'ai-tools');

  // React to sidebar/tab query param changes without remount
  useEffect(() => {
    const tab = searchParams.get('tab') as MainTab | null;
    if (tab && ['ai-tools', 'js-sdk', 'dotnet-sdk', 'api-playground'].includes(tab)) {
      setMainTab(tab);
    }
  }, [searchParams]);
  const [useCase, setUseCase] = useState<UseCase>('dictation');
  const [activeTool, setActiveTool] = useState<AiTool>('claude');
  const [copied, setCopied] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientName, setClientName] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [showSecret, setShowSecret] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [envCopied, setEnvCopied] = useState(false);
  const [promptCopied, setPromptCopied] = useState(false);
const [oauthError, setOauthError] = useState<string | null>(null);
  const [selectedEndpoint, setSelectedEndpoint] = useState(API_ENDPOINTS[0].key);
  const [requestBody, setRequestBody] = useState(API_ENDPOINTS[0].sampleBody || '');
  const [playgroundResponse, setPlaygroundResponse] = useState<any>(null);
  const [playgroundLoading, setPlaygroundLoading] = useState(false);
  const [playgroundError, setPlaygroundError] = useState<string | null>(null);

  const USE_CASES = [
    { key: 'dictation' as UseCase, label: t.useCaseDictation, icon: Mic },
    { key: 'scribe' as UseCase, label: t.useCaseScribe, icon: FileEdit },
    { key: 'coding' as UseCase, label: t.useCaseCoding, icon: Stethoscope },
    { key: 'chat' as UseCase, label: t.useCaseChat, icon: Bot },
  ];

  const USE_CASE_PROMPTS: Record<UseCase, (origin: string) => string> = {
    dictation: (origin: string) => `使用 iCoDer SDK 构建医疗语音听写 Web 应用。\n\n1. 获取构建技能文件：\n   ${origin}/.well-known/agent-skills/icoder-dictation/SKILL.md\n2. 凭据在 iCoDer 控制台中获取：\n   ${origin}/developer-quickstart\n3. 使用 iCoDer Speech To Text API 流式传输实时音频并显示转录文本\n4. 添加自定义语音指令支持（如"下一部分"、"删除上一条"）\n5. 包含语言选择和标点符号设置面板`,
    scribe: (origin: string) => `使用 iCoDer SDK 构建环境抄录 Web 应用。\n\n1. 获取构建技能文件：\n   ${origin}/.well-known/agent-skills/icoder-scribe/SKILL.md\n2. 凭据在 iCoDer 控制台中获取：\n   ${origin}/developer-quickstart\n3. 使用 iCoDer Embedded Assistant API 捕获临床对话\n4. 实时显示结构化事实和临床文书\n5. 添加远程模式、AI 对话和文档反馈开关`,
    coding: (origin: string) => `使用 iCoDer SDK 构建医学编码 Web 应用。\n\n1. 获取构建技能文件：\n   ${origin}/.well-known/agent-skills/icoder-coding/SKILL.md\n2. 凭据在 iCoDer 控制台中获取：\n   ${origin}/developer-quickstart\n3. 使用 iCoDer Medical Coding API 将临床文本转换为结构化 ICD-10-CN 编码\n4. 显示证据摘要、候选编码和编码置信度\n5. 添加编码筛选和编码系统选择功能`,
    chat: (origin: string) => `使用 iCoDer SDK 构建临床对话助手 Web 应用。\n\n1. 获取构建技能文件：\n   ${origin}/.well-known/agent-skills/icoder-chat/SKILL.md\n2. 凭据在 iCoDer 控制台中获取：\n   ${origin}/developer-quickstart\n3. 使用 iCoDer Agentic Framework API 创建并调遣医学 AI 智能体\n4. 为智能体绑定专家（诊断、手术、用药信息等）\n5. 显示带证据引用的结构化编码结果`,
  };

  useEffect(() => { oauthApi.list().then(res => { const clients = res.data.clients || []; if (clients.length > 0) { const c = clients[0]; setClientId(c.client_id); setClientName(c.name || c.client_name || '默认客户端'); } }).catch(() => {}).finally(() => setLoading(false)); }, []);
  useEffect(() => {
    const ep = API_ENDPOINTS.find(e => e.key === selectedEndpoint)!;
    setRequestBody(ep.sampleBody || '');
    setPlaygroundResponse(null);
    setPlaygroundError(null);
  }, [selectedEndpoint]);
  const handleGenerate = async () => { setGenerating(true); try { const res = await oauthApi.create('快速入门客户端', '开发者快速入门自动生成', 'api:read api:write'); setClientId(res.data.client_id); setClientSecret(res.data.client_secret); } catch { setOauthError('创建 OAuth 客户端失败'); setTimeout(() => setOauthError(null), 3000); } finally { setGenerating(false); } };
  const handleCopy = (key: string, text: string) => { navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(''), 2000); };
  const handleSendRequest = async () => {
    const ep = API_ENDPOINTS.find(e => e.key === selectedEndpoint)!;
    setPlaygroundLoading(true);
    setPlaygroundError(null);
    setPlaygroundResponse(null);
    const startTime = performance.now();
    try {
      const token = localStorage.getItem('access_token');
      const headers: Record<string, string> = {
        Authorization: token ? `Bearer ${token}` : '',
        'Content-Type': 'application/json',
      };
      let parsedBody: any = {};
      if (ep.method === 'POST') {
        try { parsedBody = JSON.parse(requestBody); } catch { throw new Error('Invalid JSON in request body'); }
      }
      const options: RequestInit = { method: ep.method, headers };
      if (ep.method === 'POST') options.body = JSON.stringify(parsedBody);
      const res = await fetch(ep.path, options);
      const elapsed = Math.round(performance.now() - startTime);
      let responseBody: any = null;
      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        responseBody = await res.json();
      } else {
        responseBody = await res.text();
      }
      setPlaygroundResponse({ status: res.status, statusText: res.statusText, time: elapsed, body: responseBody });
    } catch (err) {
      const elapsed = Math.round(performance.now() - startTime);
      setPlaygroundError(err instanceof Error ? err.message : 'Unknown error');
    } finally { setPlaygroundLoading(false); }
  };

  const currentPrompt = USE_CASE_PROMPTS[useCase](window.location.origin);
  const origin = window.location.origin;
  const jsCode = `import { iCoDerClient } from "@icoder/sdk";\n\nconst client = new iCoDerClient({ baseURL: "${origin}" });\n\nconst token = await client.oauth.getToken("${clientId || 'icoder-xxx'}", "${clientSecret ? clientSecret.substring(0, 20) + '...' : 'ics_xxx'}");\n\n// 事实提取\nconst facts = await client.facts.extract({\n  context: { type: "text", text: "患者因腰痛伴左下肢放射痛3月就诊..." },\n  outputLanguage: "zh-CN",\n});\nconsole.log("诊断:", facts.diagnosis_facts);\nconsole.log("手术:", facts.procedure_facts);`;
  const dotNetCode = `using iCoDer.Sdk;\nusing iCoDer.Sdk.Models;\n\nvar credentials = new ClientCredentials { ClientId = "${clientId || 'icoder-xxx'}", ClientSecret = "${clientSecret ? clientSecret.substring(0, 20) + '...' : 'ics_xxx'}", BaseUrl = "${origin}" };\n\nvar client = new iCoDerClient(credentials);\n\n// 事实提取\nvar facts = await client.Facts.ExtractAsync(new FactExtractRequest\n{\n    Context = new FactContext { Type = "text", Text = "患者因腰痛伴左下肢放射痛3月就诊..." },\n    OutputLanguage = "zh-CN",\n});\nConsole.WriteLine($"诊断: {string.Join(", ", facts.DiagnosisFacts)}");\nConsole.WriteLine($"手术: {string.Join(", ", facts.ProcedureFacts)}");`;

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin h-8 w-8 text-muted-foreground" /></div>;

  return (
    <div className="p-6 bg-muted/20 min-h-full">
      {oauthError && (
        <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive flex items-center justify-between">
          <span>{oauthError}</span>
          <button onClick={() => setOauthError(null)} className="text-destructive/60 hover:text-destructive">&times;</button>
        </div>
      )}
      <div className="flex items-center gap-1.5 mb-4 text-xs text-muted-foreground"><Link to="/" className="hover:text-foreground">{t.home}</Link><ChevronRight size={12} /><span className="text-foreground font-medium">{t.devQsTitle}</span></div>
      <div className="flex items-center justify-between mb-6"><div><h2 className="text-2xl font-bold text-foreground mb-1">{t.devQsTitle}</h2><p className="text-sm text-muted-foreground max-w-xl">{t.devQsSubtitle}</p></div><a href="/docs" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-foreground hover:bg-accent transition-colors h-8"><BookOpen size={14} /> {t.devQsApiDocs}</a></div>

      <div className="inline-flex items-center rounded-lg border border-border/20 bg-background p-0.5 mb-6 shadow-sm" role="tablist">
        {([{ key: 'ai-tools' as MainTab, label: t.devQsAiToolsTab }, { key: 'js-sdk' as MainTab, label: t.devQsJsSdkTab }, { key: 'dotnet-sdk' as MainTab, label: t.devQsDotNetTab }, { key: 'api-playground' as MainTab, label: 'API Playground' }]).map(tab => (
          <button key={tab.key} role="tab" aria-selected={mainTab === tab.key} onClick={() => setMainTab(tab.key)} className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${mainTab === tab.key ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>{tab.label}</button>
        ))}
      </div>

      {mainTab === 'ai-tools' && (
        <div className="flex flex-col gap-6 w-full">
          <p className="text-base text-muted-foreground">{t.devQsAiToolsDesc}</p>
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">1</div><h3 className="text-sm font-semibold text-foreground">{t.devQsStep1Title}</h3></div>
            <div className="grid grid-cols-4 gap-3">{USE_CASES.map(uc => { const Icon = uc.icon; return <button key={uc.key} onClick={() => setUseCase(uc.key)} className={`flex flex-col items-center gap-2 p-4 rounded-lg transition-all text-left ${useCase === uc.key ? 'ring-2 ring-primary/50 bg-primary/5 shadow-sm' : 'shadow-sm bg-background hover:ring-primary/30 hover:bg-accent/50'}`}><Icon size={20} className={useCase === uc.key ? 'text-primary' : 'text-muted-foreground'} /><span className="text-sm font-medium text-foreground text-center leading-tight">{uc.label}</span></button>; })}</div>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">2</div><h3 className="text-sm font-semibold text-foreground">{t.devQsStep2Title}</h3></div>
            <p className="text-sm text-muted-foreground mb-3">{t.devQsStep2Hint}</p>
            <div className="border border-border rounded-xl bg-muted/20 p-4 mb-3 relative">
              <button onClick={() => { navigator.clipboard.writeText(currentPrompt); setPromptCopied(true); setTimeout(() => setPromptCopied(false), 2000); }} className="absolute top-3 right-3 p-1.5 rounded hover:bg-accent transition-colors text-muted-foreground">{promptCopied ? <Check size={14} className="text-secondary" /> : <Copy size={14} />}</button>
              <p className="text-sm text-muted-foreground font-semibold mb-2">{t.devQsPromptLabel}</p>
              <pre className="text-base text-foreground whitespace-pre-wrap font-sans leading-relaxed">{currentPrompt}</pre>
            </div>
            <div className="flex items-center gap-2"><span className="text-sm text-muted-foreground">{t.devQsOpenIn}</span>{AI_TOOLS.map(tool => <button key={tool.key} onClick={() => { setActiveTool(tool.key); navigator.clipboard.writeText(currentPrompt); setPromptCopied(true); setTimeout(() => setPromptCopied(false), 2000); }} className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${activeTool === tool.key ? 'border-primary/50 bg-primary/5 text-foreground' : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'}`}>{tool.label}</button>)}</div>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">3</div><h3 className="text-sm font-semibold text-foreground">{t.devQsStep3Title}</h3></div>
            <p className="text-sm text-muted-foreground mb-3">{t.devQsStep3Hint}</p>
            <div className="flex items-center gap-3">
              <Link to="/api-clients" className="px-3 py-1.5 rounded-md text-sm border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">{t.devQsManageClients}</Link>
              {clientId ? (
                <>
                  <button onClick={() => { const dotEnv = `CLIENT_ID=${clientId}\nCLIENT_SECRET=${clientSecret || 'ics_xxx'}\nENVIRONMENT=development\nTENANT=default`; navigator.clipboard.writeText(dotEnv); setEnvCopied(true); setTimeout(() => setEnvCopied(false), 2000); }} className="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5">{envCopied ? <Check size={14} /> : <Copy size={14} />}{envCopied ? t.copied : t.devQsCopyEnv}</button>
                  <span className="text-xs text-muted-foreground">{clientName}{showSecret && clientSecret && <span className="ml-2 font-mono text-[10px] text-muted-foreground/60">{clientSecret}</span>}</span>
                </>
              ) : <button onClick={handleGenerate} disabled={generating} className="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5 disabled:opacity-50">{generating ? <Loader2 size={14} className="animate-spin" /> : <Key size={14} />}{generating ? t.devQsGenerating : t.devQsGenerateCreds}</button>}
            </div>
          </div>
        </div>
      )}

      {mainTab === 'js-sdk' && (
        <div className="flex flex-col gap-6 w-full">
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">1</div><h3 className="text-sm font-semibold text-foreground">{t.devQsCopyCreds}</h3></div>
            <p className="text-sm text-muted-foreground mb-3">{t.devQsCredsFlow}</p>
            <div className="flex items-center gap-3 mb-3"><span className="text-sm font-medium flex items-center gap-1.5"><Key size={14} className="text-primary" /> {clientName || t.devQsDefaultClient}</span><Link to="/api-clients" className="text-xs text-primary hover:underline">{t.devQsManageClients}</Link></div>
            <div className="flex items-center gap-2">
              {clientId ? (
                <>
                  <button onClick={() => { const dotEnv = `CLIENT_ID=${clientId}\nCLIENT_SECRET=${clientSecret || 'ics_xxx'}\nENVIRONMENT=development\nTENANT=default`; navigator.clipboard.writeText(dotEnv); setEnvCopied(true); setTimeout(() => setEnvCopied(false), 2000); }} className="px-3 py-1.5 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5">{envCopied ? <Check size={14} /> : <Copy size={14} />}{envCopied ? t.copied : t.devQsCopyEnv}</button>
                  <button onClick={() => setShowSecret(!showSecret)} className="px-3 py-1.5 rounded-md text-sm border border-border text-muted-foreground hover:text-foreground transition-colors">{showSecret ? '隐藏凭据' : t.devQsViewCreds}</button>
                </>
              ) : <button onClick={handleGenerate} disabled={generating} className="px-3 py-1.5 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5 disabled:opacity-50">{generating ? <Loader2 size={14} className="animate-spin" /> : <Key size={14} />}{generating ? t.devQsGenerating : t.devQsGenerateCreds}</button>}
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">2</div><h3 className="text-sm font-semibold text-foreground">{t.step2Title}</h3></div>
            <p className="text-sm text-muted-foreground mb-2">{t.devQsInstallNpm}</p>
            <div className="bg-muted rounded-lg p-3 mb-3 flex items-center gap-2"><Terminal size={14} className="text-muted-foreground shrink-0" /><code className="text-sm font-mono text-foreground">npm install @icoder/sdk dotenv</code><button onClick={() => handleCopy('npm', 'npm install @icoder/sdk dotenv')} className="ml-auto p-1 rounded hover:bg-accent">{copied === 'npm' ? <Check size={12} className="text-secondary" /> : <Copy size={12} className="text-muted-foreground" />}</button></div>
            <p className="text-sm text-muted-foreground mb-2">{t.devQsJsCodeHint}</p>
            <div className="border border-border rounded-xl bg-muted/20 p-4 relative"><button onClick={() => handleCopy('js', jsCode)} className="absolute top-3 right-3 p-1.5 rounded hover:bg-accent transition-colors text-muted-foreground">{copied === 'js' ? <Check size={14} className="text-secondary" /> : <Copy size={14} />}</button><p className="text-xs text-muted-foreground font-semibold mb-2">JavaScript (SDK)</p><pre className="text-sm text-foreground whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">{jsCode}</pre></div>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">3</div><h3 className="text-sm font-semibold text-foreground">{t.devQsReadyTitle}</h3></div>
            <div className="space-y-1.5">
              {[{ label: t.devQsWalkthrough1, link: '/ai-studio/speech-to-text' }, { label: t.devQsWalkthrough2, link: '/ai-studio/agents' }, { label: t.devQsWalkthrough3, link: '/ai-studio/medical-coding' }, { label: t.devQsWalkthrough4, link: '/ai-studio/agents' }].map(item => <Link key={item.label} to={item.link} className="block text-sm text-primary hover:underline">{item.label}</Link>)}
            </div>
          </div>
        </div>
      )}

      {mainTab === 'dotnet-sdk' && (
        <div className="flex flex-col gap-6 w-full">
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">1</div><h3 className="text-sm font-semibold text-foreground">{t.devQsCopyCreds}</h3></div>
            <p className="text-sm text-muted-foreground mb-3">{t.devQsCredsFlowDotnet}</p>
            <div className="flex items-center gap-3 mb-3"><span className="text-sm font-medium flex items-center gap-1.5"><Key size={14} className="text-primary" /> {clientName || t.devQsDefaultClient}</span><Link to="/api-clients" className="text-xs text-primary hover:underline">{t.devQsManageClients}</Link></div>
            <div className="flex items-center gap-2">
              {clientId ? (
                <>
                  <button onClick={() => { const dotEnv = `CLIENT_ID=${clientId}\nCLIENT_SECRET=${clientSecret || 'ics_xxx'}\nENVIRONMENT=development\nTENANT=default`; navigator.clipboard.writeText(dotEnv); setEnvCopied(true); setTimeout(() => setEnvCopied(false), 2000); }} className="px-3 py-1.5 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5">{envCopied ? <Check size={14} /> : <Copy size={14} />}{envCopied ? t.copied : t.devQsCopyEnv}</button>
                  <button onClick={() => setShowSecret(!showSecret)} className="px-3 py-1.5 rounded-md text-sm border border-border text-muted-foreground hover:text-foreground transition-colors">{showSecret ? '隐藏凭据' : t.devQsViewCreds}</button>
                </>
              ) : <button onClick={handleGenerate} disabled={generating} className="px-3 py-1.5 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5 disabled:opacity-50">{generating ? <Loader2 size={14} className="animate-spin" /> : <Key size={14} />}{generating ? t.devQsGenerating : t.devQsGenerateCreds}</button>}
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">2</div><h3 className="text-sm font-semibold text-foreground">{t.step2Title}</h3></div>
            <p className="text-sm text-muted-foreground mb-2">{t.devQsInstallDotnet}</p>
            <div className="bg-muted rounded-lg p-3 mb-3 flex items-center gap-2"><Terminal size={14} className="text-muted-foreground shrink-0" /><code className="text-sm font-mono text-foreground">dotnet add package iCoDer.Sdk</code><button onClick={() => handleCopy('dotnet-pkg', 'dotnet add package iCoDer.Sdk')} className="ml-auto p-1 rounded hover:bg-accent">{copied === 'dotnet-pkg' ? <Check size={12} className="text-secondary" /> : <Copy size={12} className="text-muted-foreground" />}</button></div>
            <p className="text-sm text-muted-foreground mb-2">{t.devQsDotnetCodeHint}</p>
            <div className="border border-border rounded-xl bg-muted/20 p-4 relative"><button onClick={() => handleCopy('dotnet', dotNetCode)} className="absolute top-3 right-3 p-1.5 rounded hover:bg-accent transition-colors text-muted-foreground">{copied === 'dotnet' ? <Check size={14} className="text-secondary" /> : <Copy size={14} />}</button><p className="text-xs text-muted-foreground font-semibold mb-2">.NET (SDK)</p><pre className="text-sm text-foreground whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">{dotNetCode}</pre></div>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-xs font-bold text-primary-foreground">3</div><h3 className="text-sm font-semibold text-foreground">{t.devQsReadyTitle}</h3></div>
            <div className="space-y-1.5">
              {[{ label: t.devQsWalkthrough1, link: '/ai-studio/speech-to-text' }, { label: t.devQsWalkthrough2, link: '/ai-studio/agents' }, { label: t.devQsWalkthrough3, link: '/ai-studio/medical-coding' }, { label: t.devQsWalkthrough4, link: '/ai-studio/agents' }].map(item => <Link key={item.label} to={item.link} className="block text-sm text-primary hover:underline">{item.label}</Link>)}
            </div>
          </div>
        </div>
      )}

      {mainTab === 'api-playground' && (
        <div className="flex flex-col gap-6 w-full">
          <p className="text-base text-muted-foreground">{t.devQsApiPlaygroundDesc}</p>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">{t.devQsApiEndpoint}</label>
            <select
              value={selectedEndpoint}
              onChange={e => { setSelectedEndpoint(e.target.value); }}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-colors"
            >
              {API_ENDPOINTS.map(ep => (
                <option key={ep.key} value={ep.key}>{ep.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">{t.devQsRequestBody}</label>
            <textarea
              value={requestBody}
              onChange={e => setRequestBody(e.target.value)}
              disabled={API_ENDPOINTS.find(e => e.key === selectedEndpoint)?.method === 'GET'}
              rows={8}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-colors resize-y disabled:opacity-50 disabled:cursor-not-allowed"
              placeholder={
                API_ENDPOINTS.find(e => e.key === selectedEndpoint)?.method === 'GET'
                  ? t.devQsNoRequestBody
                  : '{\n  "key": "value"\n}'
              }
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSendRequest}
              disabled={playgroundLoading}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {playgroundLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              {playgroundLoading ? t.devQsSending : t.devQsSendRequest}
            </button>
            {playgroundError && (
              <span className="text-sm text-destructive">{playgroundError}</span>
            )}
          </div>

          {(playgroundResponse || playgroundLoading) && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-foreground">{t.devQsResponse}</h3>
                {playgroundResponse && (
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        playgroundResponse.status < 300
                          ? 'bg-secondary/10 text-secondary'
                          : playgroundResponse.status < 500
                          ? 'bg-primary/10 text-primary'
                          : 'bg-destructive/10 text-destructive'
                      }`}
                    >
                      {playgroundResponse.status} {playgroundResponse.statusText}
                    </span>
                    <span className="text-xs text-muted-foreground">{playgroundResponse.time}ms</span>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(playgroundResponse.body, null, 2));
                        setCopied('pg-resp');
                        setTimeout(() => setCopied(''), 2000);
                      }}
                      className="p-1 rounded hover:bg-accent text-muted-foreground"
                    >
                      {copied === 'pg-resp' ? <Check size={14} className="text-secondary" /> : <Copy size={14} />}
                    </button>
                  </div>
                )}
              </div>
              {playgroundLoading ? (
                <div className="flex items-center justify-center h-32 border border-border rounded-xl bg-muted/20">
                  <Loader2 size={20} className="animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="border border-border rounded-xl bg-muted/20 p-4 overflow-x-auto">
                  <pre className="text-sm text-foreground font-mono whitespace-pre-wrap">
                    {typeof playgroundResponse.body === 'string'
                      ? playgroundResponse.body
                      : JSON.stringify(playgroundResponse.body, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
