import { useLocaleStore } from '../i18n';
import { useT } from '../i18n';
// iCoDer Speech To Text — iCoDer Console 1:1 replica
import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Mic, MicOff, Copy, X, Plus, Settings2, AudioWaveform, Sparkles, ListTree, ChevronRight } from 'lucide-react';
import { appendWithPunctuation, llmPunctuate } from '../utils/stt-punctuation';
import EventInspector from '../components/common/EventInspector';
import CodeSnippet from '../components/common/CodeSnippet';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import WorkbenchLayout from '../components/layout/WorkbenchLayout';


const TEMPLATES = ['出院小结', '病程记录', '出院指导', '入院记录', '手术记录', '会诊记录'];

interface CommandVariable {
  key: string;
  type: 'enum';
  values: string[];
}

const DEFAULT_COMMANDS = [
  { id: 'next_section', name: '跳转段落', phrases: ['下一部分', '跳转到下一部分', '下一段'], action: '跳转到下一文书段落' },
  { id: 'delete', name: '撤销录入', phrases: ['删除上一条', '删除最后一条', '撤销'], action: '撤销最近录入的文本' },
  { id: 'insert_template', name: '插入模板', phrases: ['插入模板', '插入出院小结', '插入病程记录', '插入出院指导', '插入入院记录', '插入手术记录', '插入会诊记录'], action: '插入文书模板' },
  { id: 'new_paragraph', name: '新建段落', phrases: ['新段落', '换行', '另起一段'], action: '插入换行符' },
  { id: 'period', name: '句号', phrases: ['句号', '加句号'], action: '插入句号' },
];

const LANGUAGES = [
  { code: 'zh-CN', label: '简体中文' },
  { code: 'en-US', label: 'English (US)' },
];

export default function SpeechToTextPage() {
  const locale = useLocaleStore(s => s.locale);
  const t = useT();
  const [transcript, setTranscript] = useState('');
  const [interim, setInterim] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [language, setLanguage] = useState('zh-CN');
  const [punctuationMode, setPunctuationMode] = useState<'spoken' | 'auto'>('auto');
  const [interimResults, setInterimResults] = useState(true);
  const [copied, setCopied] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [detectedCmd, setDetectedCmd] = useState<string | null>(null);
  const [commands, setCommands] = useState(DEFAULT_COMMANDS);
  const [showAddCmd, setShowAddCmd] = useState(false);
  const [newCmdName, setNewCmdName] = useState('');
  const [newCmdPhrases, setNewCmdPhrases] = useState('');
  const [newCmdAction, setNewCmdAction] = useState('');
  const [newCmdVars, setNewCmdVars] = useState<CommandVariable[]>([]);
  const [showVarForm, setShowVarForm] = useState(false);
  const [varKey, setVarKey] = useState('');
  const [varValues, setVarValues] = useState('');
  const [sttMode, setSttMode] = useState<'browser' | 'server'>('server');
  const [sttBuffering, setSttBuffering] = useState(0);
  const [sttEvents, setSttEvents] = useState<{type:string;data:Record<string,unknown>;timestamp:string;credits?:number}[]>([]);
  const [sttCredits, setSttCredits] = useState(0);
  const recognitionRef = useRef<any | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const interimTimerRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const getRecognitionRef = useRef<(() => any | null) | null>(null);
  const transcriptRef = useRef('');

  // Keep transcriptRef in sync
  useEffect(() => { transcriptRef.current = transcript; }, [transcript]);

  // LLM punctuation refinement when recording stops
  const prevListeningRef = useRef(false);
  useEffect(() => {
    const wasRecording = prevListeningRef.current;
    prevListeningRef.current = isListening;
    if (wasRecording && !isListening && transcriptRef.current.trim()) {
      llmPunctuate(transcriptRef.current).then(refined => {
        if (refined && refined !== transcriptRef.current) {
          setTranscript(refined);
        }
      }).catch(() => {});
    }
  }, [isListening]);

  const getRecognition = useCallback((): any | null => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = interimResults;
    rec.lang = language;
    rec.onresult = (event: any /* SpeechRecognitionEvent */) => {
      let interimText = '', finalText = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        r.isFinal ? finalText += r[0].transcript : interimText += r[0].transcript;
      }
      if (finalText) {
        setSttEvents(prev => [...prev.slice(-50), { type: 'transcript', data: { text: finalText.trim().slice(0, 80) }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }), credits: 0.000001 }]);
        setSttCredits(c => c + 0.000001);
        let processed = finalText.trim();
        let cmdMatched = false;

        // Check each command's phrases against the recognized text
        for (const cmd of commands) {
          for (const phrase of cmd.phrases) {
            if (processed.includes(phrase)) {
              cmdMatched = true;
              setDetectedCmd(cmd.id);
              setTimeout(() => setDetectedCmd(null), 2000);

              // Execute command action
              if (cmd.id === 'next_section') {
                processed = processed.replace(phrase, '\n\n---\n\n');
              } else if (cmd.id === 'delete') {
                // Remove last sentence
                setTranscript(p => { const parts = p.split(/[。.！!？?\n]/); parts.pop(); return parts.join('。') + '。'; });
                setInterim('');
                return; // Don't append the command text
              } else if (cmd.id === 'new_paragraph') {
                processed = processed.replace(phrase, '\n\n');
              } else if (cmd.id === 'period') {
                processed = processed.replace(phrase, '。');
              } else if (cmd.id === 'insert_template') {
                // Detect which template was requested
                const matched = TEMPLATES.find(t => processed.includes(t));
                const templateName = matched || '出院小结';
                processed = processed.replace(phrase, '').trim();
                setTranscript(p => (p + ' ' + processed + `\n[${templateName} 模板已插入]\n`).trim());
                setInterim('');
                return;
              }
              break;
            }
          }
          if (cmdMatched) break;
        }

        if (!cmdMatched || processed !== finalText.trim()) {
          setTranscript(p => appendWithPunctuation(p, processed));
        }
        setInterim('');
      } else {
        setInterim(interimText);
      }
    };
    rec.onerror = (event: any /* SpeechRecognitionError */) => { if (event.error !== 'no-speech') console.error(event.error); setIsListening(false); };
    rec.onend = () => setIsListening(false);
    return rec;
  }, [language, interimResults]);

  // Server-side STT via WebSocket
  const startServerSTT = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      const rec = new MediaRecorder(stream, { mimeType: mime });
      mediaRecorderRef.current = rec;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      // Dev: frontend on :3000, backend on :8001 → connect directly to backend
      const wshost = window.location.port === '3000' ? `${window.location.hostname}:8001` : window.location.host;
      const wsUrl = `${protocol}//${wshost}/ws/speech-to-text`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      // Connection timeout — show error if WebSocket doesn't connect in 5s
      const connectTimeout = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          ws.close();
          setErrorMsg('无法连接到语音识别服务。请确认后端服务已启动（端口 8001），并检查防火墙设置。');
        }
      }, 5000);

      ws.onopen = () => {
        clearTimeout(connectTimeout);
        ws.send(JSON.stringify({ type: 'start', mimeType: mime }));
        rec.start(250);
        setIsListening(true);
        setSttEvents(prev => [...prev.slice(-50), { type: 'stt_start', data: { mode: 'server', language }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }), credits: 0.000001 }]);
        setSttCredits(c => c + 0.000001);
        // Server pushes interim automatically — no client polling needed
      };

      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.type === 'ready') { setSttEvents(prev => [...prev.slice(-50), { type: 'stt_ready', data: {}, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }) }]); }
        else if (m.type === 'interim') { if (m.text) { setInterim(m.text); setSttEvents(prev => [...prev.slice(-50), { type: 'interim', data: { text: m.text.slice(0, 60) }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }) }]); } }
        else if (m.type === 'final') {
          const incoming = m.text;
          setTranscript(p => appendWithPunctuation(p, incoming));
          setInterim('');
          setSttEvents(prev => [...prev.slice(-50), { type: 'final', data: { text: incoming.slice(0, 80) }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }), credits: 0.000001 }]);
          setSttCredits(c => c + 0.000001);
        }
        else if (m.type === 'buffering') { setSttBuffering(m.bytes || 0); }
        else if (m.type === 'error') { setInterim('转录失败: ' + m.message); setSttEvents(prev => [...prev.slice(-50), { type: 'error', data: { message: m.message }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }) }]); }
      };

      ws.onerror = () => { clearTimeout(connectTimeout); setSttEvents(prev => [...prev.slice(-50), { type: 'error', data: { message: 'WebSocket连接失败' }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }) }]); stopServerSTT(); setErrorMsg('语音识别服务连接失败，请确认后端服务正在运行。'); };
      ws.onclose = () => { clearTimeout(connectTimeout); wsRef.current = null; setIsListening(false); };

      rec.ondataavailable = (e) => {
        if (e.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(e.data);
        }
      };

      rec.onstop = () => {
        if (interimTimerRef.current) { clearInterval(interimTimerRef.current); interimTimerRef.current = null; }
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'end' }));
          setTimeout(() => {
            wsRef.current?.close();
            stream.getTracks().forEach(t => t.stop());
            setIsListening(false);
          }, 10000);
        } else {
          stream.getTracks().forEach(t => t.stop());
          setIsListening(false);
        }
      };
    } catch (err: any) {
      setErrorMsg('无法启动录音: ' + (err.message || '请检查麦克风权限'));
    }
  }, []);

  const stopServerSTT = useCallback(() => {
    if (interimTimerRef.current) { clearInterval(interimTimerRef.current); interimTimerRef.current = null; }
    try { mediaRecorderRef.current?.stop(); } catch {}
    try { wsRef.current?.close(); } catch {}
    try { streamRef.current?.getTracks().forEach(t => t.stop()); } catch {}
    mediaRecorderRef.current = null;
    wsRef.current = null;
    streamRef.current = null;
    setIsListening(false);
  }, []);

  // Main toggle — startServerSTT/stopServerSTT have [] deps (stable), direct ref OK.
  // getRecognition uses ref to avoid stale closure from language/interimResults changes.
  const toggleListening = useCallback(() => {
    if (isListening) {
      if (sttMode === 'server') { stopServerSTT(); return; }
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }
    if (sttMode === 'server') { setErrorMsg(null); startServerSTT(); return; }
    // Browser mode — use ref to get latest getRecognition
    setErrorMsg(null);
    const gn = getRecognitionRef.current;
    const rec = gn ? gn() : null;
    if (!rec) { setErrorMsg('此浏览器不支持语音识别，请使用Chrome或切换到服务端模式。'); return; }
    recognitionRef.current = rec;
    try { rec.start(); setIsListening(true); } catch { setErrorMsg('无法启动语音识别，请检查麦克风权限。'); }
  }, [isListening, sttMode, startServerSTT, stopServerSTT]);

  // Keep getRecognition ref in sync
  useEffect(() => { getRecognitionRef.current = getRecognition; }, [getRecognition]);


  // ---- WorkbenchLayout slot content ----
  const inputSlot = (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between shrink-0 mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-foreground">识别引擎</span>
          <div className="flex items-center rounded-lg bg-muted p-0.5">
            <button onClick={() => { if (isListening) stopServerSTT(); setSttMode('server'); }}
              className={`px-3 py-1 text-[11px] rounded-md transition-all font-medium ${sttMode === 'server' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Medvoice</button>
            <button onClick={() => setSttMode('browser')}
              className={`px-3 py-1 text-[11px] rounded-md transition-all font-medium ${sttMode === 'browser' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Web 内置</button>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="mb-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700 flex items-center justify-between">
          <span>{errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="p-0.5 rounded hover:bg-red-100 shrink-0 ml-2"><X size={12} /></button>
        </div>
      )}

      <div className="flex-1 flex flex-col items-center justify-center">
        <button onClick={toggleListening}
          className={`p-4 rounded-full transition-all ${
            isListening
              ? 'bg-red-500 hover:bg-red-600 text-white scale-110 shadow-lg shadow-red-500/20'
              : 'bg-primary text-primary-foreground hover:opacity-90 shadow-sm shadow-primary/20'
          }`}>
          {isListening ? <MicOff size={22} /> : <Mic size={22} />}
        </button>
      </div>

      <div className="flex items-center gap-1.5 mt-2 shrink-0 flex-wrap">
        <span className="text-xs text-muted-foreground/60 shrink-0 mr-1">识别到指令：</span>
        {commands.map(cmd => (
          <span key={cmd.id}
            className={`text-[11px] px-3 py-1 rounded-md transition-colors cursor-default font-medium ${
              detectedCmd === cmd.id
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground/70 hover:text-foreground hover:bg-muted'
            }`}>
            {cmd.name}
          </span>
        ))}
        <span className="flex-1" />
        <button onClick={() => { setNewCmdName(''); setNewCmdPhrases(''); setNewCmdAction(''); setNewCmdVars([]); setShowVarForm(false); setShowAddCmd(true); }}
          className="p-1 rounded-md text-muted-foreground/40 hover:text-foreground hover:bg-accent transition-colors"><Plus size={14} /></button>
      </div>
    </div>
  );

  const outputSlot = (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 shrink-0 mb-2">
        <AudioWaveform size={14} className="text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">转录文本</span>
        {(transcript || interim) && (
          <div className="flex items-center gap-1 ml-auto">
            <button onClick={() => { navigator.clipboard.writeText(transcript); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"><Copy size={13} /></button>
            <button onClick={() => { setTranscript(''); setInterim(''); }}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"><X size={13} /></button>
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        <p className="text-lg text-foreground whitespace-pre-wrap leading-relaxed">
          {transcript}
          {interim && <span className="text-muted-foreground/40"> {interim}</span>}
        </p>
        {!transcript && !interim && (
          <p className="text-muted-foreground/25 text-base">点击麦克风开始录音</p>
        )}
      </div>
    </div>
  );

  const settingsSlot = (
    <SettingsCodeTab
      labels={{ settings: '设置', code: '代码' }}
      settings={
        <div className="flex flex-col">
          <div className="border-b border-border/20">
            <div className="flex items-center gap-2 px-4 pt-4 pb-2">
              <div className="w-1 h-4 rounded-full bg-primary/40" />
              <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">语音设置</h3>
            </div>
            <div className="flex flex-col gap-3 px-4 pb-4">
              <div className="flex items-center justify-between gap-4 min-h-[32px]">
                <span className="text-sm text-foreground/80">听写语言</span>
                <select value={language} onChange={e => setLanguage(e.target.value)}
                  className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-ring">
                  {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="border-b border-border/20">
            <div className="flex items-center gap-2 px-4 pt-4 pb-2">
              <div className="w-1 h-4 rounded-full bg-primary/40" />
              <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">标点符号</h3>
            </div>
            <div className="flex flex-col gap-2 px-4 pb-4">
              <label className="flex items-center gap-2 text-sm text-foreground/70">
                <input type="radio" name="punctuation" checked={punctuationMode === 'spoken'} onChange={() => setPunctuationMode('spoken')} />
                语音标点
              </label>
              <label className="flex items-center gap-2 text-sm text-foreground/70">
                <input type="radio" name="punctuation" checked={punctuationMode === 'auto'} onChange={() => setPunctuationMode('auto')} />
                自动标点
              </label>
            </div>
          </div>

          <div className="border-b border-border/20">
            <div className="flex items-center gap-2 px-4 pt-4 pb-2">
              <div className="w-1 h-4 rounded-full bg-primary/40" />
              <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">格式化</h3>
            </div>
            <div className="flex flex-col gap-2 px-4 pb-4">
              <label className="flex items-center gap-2 text-sm text-foreground/70">
                <input type="checkbox" checked={interimResults} onChange={e => setInterimResults(e.target.checked)} />
                显示暂态结果
              </label>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 px-4 pt-4 pb-2">
              <div className="w-1 h-4 rounded-full bg-primary/40" />
              <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">语音指令</h3>
            </div>
            <div className="flex flex-col gap-1.5 px-4 pb-4">
              {commands.map(cmd => (
                <div key={cmd.id} className="text-xs py-1">
                  <p className="font-medium text-foreground">{cmd.name}</p>
                  <p className="text-muted-foreground/60 text-[11px] mt-0.5">{cmd.phrases.slice(0, 3).join('、')}</p>
                </div>
              ))}
              <button onClick={() => { setNewCmdName(''); setNewCmdPhrases(''); setNewCmdAction(''); setNewCmdVars([]); setShowVarForm(false); setShowAddCmd(true); }}
                className="text-xs text-primary hover:underline mt-2 flex items-center gap-1">
                <Plus size={12} /> 添加指令
              </button>
            </div>
          </div>
        </div>
      }
      code={
        <CodeSnippet
          javascript={`import { iCoDerClient } from "@icoder/sdk";

const client = new iCoDerClient({ apiKey: "YOUR_API_KEY" });

const session = await client.speechToText.startSession({
  language: "${language}",
  punctuation: "${punctuationMode}",
  interimResults: ${interimResults},
});

session.onTranscript((text) => {
  console.log("Transcript:", text);
});`}
          python={`from icoder_speech import iCoDerSTTClient

client = iCoDerSTTClient(api_key="YOUR_API_KEY")

session = client.create_session(
    language="${language}",
    punctuation="${punctuationMode}",
    interim_results=${interimResults},
)

session.start()
for transcript in session.transcripts():
    print(f"Transcript: {transcript}")`}
          csharp={`using iCoDer.Speech;

var config = new iCoDerConfig { ApiKey = "YOUR_API_KEY" };
using var client = new iCoDerSttClient(config);

var session = await client.StartSessionAsync(new SttSessionOptions
{
    Language = "${language}",
    Punctuation = PunctuationMode.${punctuationMode === 'auto' ? 'Auto' : 'Spoken'},
    InterimResults = ${interimResults}
});

session.OnTranscript += (sender, text) =>
{
    Console.WriteLine($"Transcript: {text}");
};

await session.StartAsync();`}
          json={`{
  "apiKey": "YOUR_API_KEY",
  "language": "${language}",
  "punctuation": "${punctuationMode}",
  "interimResults": ${interimResults}
}`}
        />
      }
    />
  );

  const inspectorSlot = (
    <EventInspector events={sttEvents} creditsConsumed={sttCredits} />
  );

  return (
    <>
      <WorkbenchLayout
        title={t.speechToTextBreadcrumb}
        description="将语音实时转录为结构化文本"
        inputLabel="语音控制"
        outputLabel="转录文本"
        input={inputSlot}
        output={outputSlot}
        settings={settingsSlot}
        eventInspector={inspectorSlot}
      />

      {/* Add Command Modal */}
      {showAddCmd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowAddCmd(false)}>
          <div className="bg-card rounded-xl border border-border shadow-xl w-full max-w-md overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-border">
              <h3 className="text-sm font-semibold text-foreground">添加语音指令</h3>
              <button onClick={() => setShowAddCmd(false)} className="p-1 rounded hover:bg-accent"><X size={14} className="text-muted-foreground" /></button>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">指令名称</label>
                <input value={newCmdName} onChange={e => setNewCmdName(e.target.value)} placeholder="例如：新建段落" className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" autoFocus />
              </div>
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">触发短语 <span className="text-muted-foreground font-normal">（逗号分隔多个）</span></label>
                <input value={newCmdPhrases} onChange={e => setNewCmdPhrases(e.target.value)} placeholder="下一部分, 跳转, 下一段" className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
              </div>
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">操作说明</label>
                <input value={newCmdAction} onChange={e => setNewCmdAction(e.target.value)} placeholder="跳转到下一文书段落" className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
              </div>

              {/* Variables section */}
              <div className="border-t border-border pt-3">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-foreground">变量</label>
                  {!showVarForm && (
                    <button onClick={() => { setVarKey(''); setVarValues(''); setShowVarForm(true); }}
                      className="text-[10px] text-primary hover:underline flex items-center gap-0.5">
                      <Plus size={10} /> 添加变量
                    </button>
                  )}
                </div>

                {showVarForm && (
                  <div className="space-y-2 mb-2 p-2.5 bg-muted/30 rounded-lg border border-border">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[10px] text-muted-foreground block mb-0.5">变量键</label>
                        <input value={varKey} onChange={e => setVarKey(e.target.value)} placeholder="template_name" className="w-full text-xs border border-border rounded px-2 py-1.5 bg-transparent font-mono focus:outline-none focus:ring-1 focus:ring-ring" />
                      </div>
                      <div>
                        <label className="text-[10px] text-muted-foreground block mb-0.5">类型</label>
                        <select disabled className="w-full text-xs border border-border rounded px-2 py-1.5 bg-transparent text-muted-foreground">
                          <option>enum</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground block mb-0.5">枚举值 <span className="font-normal">（逗号分隔）</span></label>
                      <input value={varValues} onChange={e => setVarValues(e.target.value)} placeholder="soap, progress, discharge" className="w-full text-xs border border-border rounded px-2 py-1.5 bg-transparent font-mono focus:outline-none focus:ring-1 focus:ring-ring" />
                    </div>
                    <div className="flex items-center justify-end gap-1.5 pt-1">
                      <button onClick={() => setShowVarForm(false)} className="text-[10px] px-2 py-1 rounded border border-border hover:bg-accent">取消</button>
                      <button onClick={() => {
                        if (!varKey.trim() || !varValues.trim()) return;
                        setNewCmdVars(prev => [...prev, {
                          key: varKey.trim(),
                          type: 'enum',
                          values: varValues.split(/[,，]/).map(s => s.trim()).filter(Boolean),
                        }]);
                        setVarKey(''); setVarValues(''); setShowVarForm(false);
                      }} disabled={!varKey.trim() || !varValues.trim()}
                        className="text-[10px] px-2 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50">添加</button>
                    </div>
                  </div>
                )}

                {newCmdVars.length > 0 && (
                  <div className="space-y-1.5">
                    {newCmdVars.map((v, i) => (
                      <div key={i} className="flex items-center justify-between bg-muted/20 rounded px-2.5 py-1.5 border border-border text-xs">
                        <span className="font-mono text-foreground">
                          {`{${v.key}}`}<span className="text-muted-foreground">=</span>{v.values.join(' | ')}
                        </span>
                        <button onClick={() => setNewCmdVars(prev => prev.filter((_, j) => j !== i))}
                          className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-red-500 ml-2 shrink-0">
                          <X size={10} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-muted/30">
              <button onClick={() => setShowAddCmd(false)} className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-accent">取消</button>
              <button
                onClick={() => {
                  if (!newCmdName.trim() || !newCmdPhrases.trim()) return;
                  setCommands(prev => [...prev, {
                    id: `cmd_${Date.now()}`,
                    name: newCmdName.trim(),
                    phrases: newCmdPhrases.split(/[,，]/).map(s => s.trim()).filter(Boolean),
                    action: newCmdAction.trim() || newCmdName.trim(),
                    variables: newCmdVars,
                  }]);
                  setNewCmdVars([]);
                  setShowAddCmd(false);
                }}
                disabled={!newCmdName.trim() || !newCmdPhrases.trim()}
                className="text-xs px-4 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-1.5">
                <Plus size={12} /> 添加
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
