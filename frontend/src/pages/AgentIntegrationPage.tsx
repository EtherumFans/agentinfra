import AgentWorkflow from '../components/agents/AgentWorkflow';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { useAuthStore } from '../store';

interface Manifest {
  agent_id: string; name: string; version: string; configuration_digest: string;
  run_path: string; token_path: string;
}
const demoText = '合成文书，仅用于软件测试，非真实患者。\n出院诊断：测试诊断\n诊疗经过：已完成合成流程验证。\n出院医嘱：此处为测试占位内容，不构成医疗建议。\n随访/复诊计划：测试流程复核。\n出院状态/转归：测试记录结束。';

export default function AgentIntegrationPage() {
  const { agentId } = useParams();
  const [searchParams] = useSearchParams();
  const version = searchParams.get('version');
  const orgId = useAuthStore(s => s.currentOrgId);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [tab, setTab] = useState('网页');
  const [inputText, setInputText] = useState(demoText);
  const [purpose,setPurpose]=useState('quality_improvement');
  const [inputFormat,setInputFormat]=useState('text');
  const [elapsed,setElapsed]=useState<number|null>(null);
  let input:any={text:inputText};let inputError='';
  if(inputFormat==='json'){try{input=JSON.parse(inputText);if(!input||typeof input.text!=='string'||!input.text.trim()||Object.keys(input).some(k=>k!=='text'))inputError='请提供仅含非空 text 字段的 JSON 对象。';}catch{inputError='JSON 格式不正确。';}}
  if(!inputError&&(!input.text.trim()||input.text.length>32000))inputError='资料正文须为 1–32000 字符。';
  const runAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    let active = true;
    runAbort.current?.abort(); setBusy(false);
    setManifest(null); setResult(null); setError('');setElapsed(null);setInputText(demoText);setInputFormat('text');
    api.get(`/rest/v1/agent_definitions/${encodeURIComponent(agentId || '')}/integration`, {params:version?{version}:undefined})
      .then(r => { if (active) setManifest(r.data); })
      .catch(() => { if (active) setError('无法获取集成配置。请确认智能体属于当前组织且已发布。'); });
    return () => { active = false; runAbort.current?.abort(); };
  }, [agentId, orgId, version]);
  const payload = {
    input, purpose_of_use: purpose,
    expected_agent_version: manifest?.version,
    expected_configuration_digest: manifest?.configuration_digest,
  };
  async function check() {
    if (!manifest || inputError) return;
    const started=performance.now();
    const controller = new AbortController();
    runAbort.current = controller;
    setBusy(true); setError(''); setResult(null);
    try {
      const r = await api.post(manifest.run_path.replace(/^\/api/, ''), payload, { timeout: 180000, signal: controller.signal });
      if (controller.signal.aborted) return;
      setResult(r.data);
      if (r.data.error) setError(r.data.error_reason || '执行未完成，请查看运行结果。');
    } catch (e: any) {
      if (controller.signal.aborted) return;
      const detail = e.response?.data?.detail ?? e.response?.data;
      setError(detail?.code === 'ORIGIN_NOT_ALLOWED'
        ? '当前页面地址未被服务端允许，请检查部署的浏览器来源配置。'
        : typeof detail === 'string' ? detail
        : detail?.message || detail?.error || '请求失败，请检查授权、模型就绪状态或网络。');
    } finally { if (!controller.signal.aborted) {setBusy(false);setElapsed(Math.round(performance.now()-started));} }
  }
  const html = `<form id="icoder-task">
  <textarea name="text" required aria-label="任务资料"></textarea>
  <button>运行智能体</button>
</form>
<pre id="icoder-result" aria-live="polite"></pre>
<script>
document.querySelector('#icoder-task').onsubmit = async event => {
  event.preventDefault();
  const form = event.currentTarget, button = form.querySelector('button');
  const output = document.querySelector('#icoder-result');
  button.disabled = true;
  try {
    const response = await fetch('/icoder/run', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: new FormData(form).get('text')})
    });
    const result = await response.json();
    output.textContent = JSON.stringify(result, null, 2);
    if (!response.ok || result.error) throw new Error('运行未完成，请查看结果');
    form.dispatchEvent(new CustomEvent('icoder:completed', {detail: result, bubbles: true}));
  } catch (error) { output.textContent += '\\n' + error.message; }
  finally { button.disabled = false; }
};
</script>`;
  const react = `import {useState} from 'react';
export default function AgentTask({onCompleted}) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  return <form onSubmit={async e => {
    e.preventDefault(); setBusy(true);
    try {
      const r = await fetch('/icoder/run', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({text})});
      const data = await r.json(); setResult(data);
      if (r.ok && !data.error) onCompleted?.(data);
    } catch { setResult({error:true, message:'连接失败'}); }
    finally { setBusy(false); }
  }}>
    <textarea required value={text} onChange={e => setText(e.target.value)} aria-label="任务资料"/>
    <button disabled={busy}>运行智能体</button>
    <pre aria-live="polite">{JSON.stringify(result,null,2)}</pre>
  </form>;
}`;
  const env = manifest ? JSON.stringify({
    ICODER_BASE_URL: window.location.origin,
    ICODER_AGENT_ID: manifest.agent_id,
    ICODER_AGENT_VERSION: manifest.version,
    ICODER_CONFIGURATION_DIGEST: manifest.configuration_digest,
    ICODER_PURPOSE: purpose,
    ICODER_CLIENT_ID: '填写服务端客户端 ID',
    ICODER_CLIENT_SECRET: '仅在服务端填写',
    DEMO_PASSWORD: '设置本地演示登录密码',
  }, null, 2) : '';
  function download() {
    const url = URL.createObjectURL(new Blob([env], {type:'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = 'integration-config.json'; a.click();
    URL.revokeObjectURL(url);
  }
  return <div className="p-4 sm:p-6 w-full min-w-0 max-w-5xl mx-auto space-y-5 overflow-y-auto h-full">
    <Link className="text-primary text-sm" to={`/ai-studio/agents/${agentId}`}>返回智能体与运行记录</Link>
    <h1 className="text-xl font-semibold">集成到我的系统</h1>{agentId&&<AgentWorkflow agentId={agentId}/>}
    <Link className="text-primary underline" to={`/ai-studio/agents/${agentId}/jobs${version?`?version=${encodeURIComponent(version)}`:""}`}>异步与批量任务</Link>
    <p className="text-sm text-muted-foreground">将智能体接入现有网页或服务端，处理结果供人工复核。</p>
    {error && <p role="alert" className="p-4 bg-red-50 text-red-700 rounded-lg">{error}</p>}
    {manifest && <>
      <section className="inspector-card"><h2 className="font-semibold">1. 确认发布配置</h2>
        <p>{manifest.name} · {manifest.version}</p>
        <label>接入用途<select aria-label="接入用途" disabled={busy} value={purpose} onChange={e=>{setPurpose(e.target.value);setResult(null);setError('');}}>{[['quality_improvement','质量改进'],['research','研究'],['treatment','诊疗'],['payment','支付'],['healthcare_operations','医疗运营'],['public_health','公共卫生']].map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>
        <p className="text-xs text-muted-foreground mt-2">此集成固定调用所选发布快照，修改草稿或发布新版本不会改变它。版本与摘要不匹配会被拒绝；外部模型和工具服务仍需独立管理。</p>
        <Link className="text-primary underline" to={`/ai-studio/agents/${agentId}/releases`}>选择版本或回滚默认版本</Link>
      </section>
      <section className="inspector-card space-y-3"><h2 className="font-semibold">2. 配置服务端访问</h2>
        <p className="text-sm">在 API 客户端中创建专用凭据，scope 为 api:write，仅授权此智能体与当前选择的 {purpose} 用途。凭据保存在用户系统的服务端。</p>
        <p className="text-xs break-all">智能体 ID：{manifest.agent_id}</p>
        <Link className="text-primary underline" to="/api-clients">配置或撤销 API 客户端访问</Link>
        <div className="flex flex-wrap gap-4"><a className="text-primary underline" href="/integration/server.py" download>下载本地接入示例</a>
          <a className="text-primary underline" href="/integration/verify_notification.py" download>下载回调验签模块</a>
          <button onClick={download} className="text-primary underline">下载该智能体配置</button></div>
        <p className="text-sm">将示例、验签模块与配置放在同一目录，填写配置中的服务端凭据与演示密码。安装 fastapi、uvicorn、httpx 后运行 python server.py，访问 http://127.0.0.1:13010，用户名 demo。点击“检查服务端接入”，验证专用凭据、版本绑定与实际执行，并按诊断提示修复。该检查会运行一次合成任务。示例仅绑定本机；正式接入时用现有用户认证替换演示登录。</p>
      </section>
      <section className="inspector-card space-y-3"><h2 className="font-semibold">3. 接入用户界面</h2>
        <p className="text-sm text-muted-foreground">网页和 React 调用用户系统的 /icoder/run，由服务端完成 OAuth 授权及固定配置调用。API 页签展示 iCoDer 上游请求体。</p>
        <div className="flex gap-3">{['网页','React','API'].map(x => <button key={x} aria-pressed={x===tab} className={x===tab?'text-primary font-semibold':'text-muted-foreground'} onClick={()=>setTab(x)}>{x}</button>)}</div>
        <pre className="bg-muted p-4 rounded-lg text-xs overflow-auto whitespace-pre max-h-96">{tab==='网页'?html:tab==='React'?react:JSON.stringify({url:manifest.run_path,body:payload},null,2)}</pre>
      </section>
      <section className="inspector-card space-y-3"><h2 className="font-semibold">4. 检查执行与回调</h2>
        <p className="text-sm">当前检查使用你的登录身份发送合成文书资料，会产生一次运行；不能替代外部客户端授权验收。外部示例支持结果展示及 icoder:completed 回调。</p>
        <label>输入方式<select aria-label="接入输入方式" disabled={busy} value={inputFormat} onChange={e=>{setInputFormat(e.target.value);setInputText(e.target.value==='json'?JSON.stringify({text:demoText},null,2):demoText);setResult(null);}}><option value="text">文书正文</option><option value="json">JSON（text 字段）</option></select></label>
        {inputError&&<p role="alert">{inputError}</p>}
        <textarea disabled={busy} aria-label="集成检查资料" className="w-full min-h-40 p-3 border border-border rounded-md bg-background" maxLength={32000} value={inputText} onChange={e => setInputText(e.target.value)}/>
        <button className="bg-primary text-primary-foreground px-4 py-2" disabled={busy || !!inputError} onClick={check}>{busy?'正在检查…':'运行合成文书检查'}</button>
        {result && <><p>耗时：{elapsed} ms · 实际执行版本：{result.executed_agent_version || '未返回'} · {result.error?'执行未通过':result.executed_agent_version===manifest.version?'执行版本已匹配':'版本证据不完整'}</p><pre className="text-xs max-h-80 overflow-auto whitespace-pre-wrap">{JSON.stringify(result,null,2)}</pre>
          {result.run_id && <Link className="text-primary underline" to={`/runs/${encodeURIComponent(result.run_id)}/trace`}>查看本次运行记录</Link>}</>}
      </section>
      <section className="inspector-card space-y-3"><h2 className="font-semibold">5. 第三方服务验收</h2><p>在下载的应用中运行“检查服务端接入”，下载包含检查时间、耗时、版本与运行标识的验收报告。此处登录用户的检查不作为机器凭据验收结论。</p><p>异步任务使用同一份固定配置。需要回调时，在服务端配置 ICODER_CALLBACK_URL 与 ICODER_CALLBACK_SECRET，并由部署管理员在 iCoDer 登记相同 HTTPS 地址与签名密钥。接收路径为 /icoder/notifications；验证签名后以数据库唯一键去重。</p><p>未配置回调时仅验收任务轮询；“任务完成”与“已收到回调”分别报告，不会相互替代。完成后核对报告中的版本与运行记录，再接入业务流程。</p></section>
    </>}
  </div>;
}
