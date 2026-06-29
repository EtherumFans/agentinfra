// iCoDer Embedded Assistant — iCoDer Console exact replica
import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { BACKEND_BASE_URL } from '../config';
import {
  RefreshCw, Mic, MicOff, X, Asterisk, Settings, Code, Activity, Sparkles, Plus, Layout, Pencil, GripVertical, Monitor, Smartphone, Copy, ExternalLink, ChevronRight,
} from 'lucide-react';
import { useT, useLocaleStore } from '../i18n';
import { useCostStore } from '../store';
import { billingApi } from '../services/api';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import CodeSnippet from '../components/common/CodeSnippet';
import EventInspector from '../components/common/EventInspector';

// ---- helpers ----
function RadioGroup({ options, value, onChange }: { options: { key: string; label?: string; icon?: any }[]; value: string; onChange: (k: string) => void }) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-input bg-muted">
      <div role="group" className="flex">
        {options.map((opt, i) => (
          <button key={opt.key} onClick={() => onChange(opt.key)}
            className={`relative flex cursor-pointer items-center justify-center rounded-lg font-medium text-sm transition-colors h-7.5 py-2 px-2
              ${value === opt.key ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
            {value === opt.key && <span className="absolute inset-0 rounded-lg bg-background shadow-sm" />}
            <span className="relative">{opt.icon || opt.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function Switch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors
        ${checked ? 'bg-primary' : 'bg-input'}`}>
      <span className={`pointer-events-none block h-4 w-4 rounded-full bg-background shadow-sm transition-transform
        ${checked ? 'translate-x-4' : 'translate-x-0.5'}`} />
    </button>
  );
}

// ---- constants ----
const LANGUAGES = [
  { code: 'zh-CN', flag: '🇨🇳', label: '简体中文' },
  { code: 'en-US', flag: '🇺🇸', label: 'English (US)' },
];
const INTERFACE_LANGUAGES = [
  { code: 'auto', flag: '🌐', label: 'Auto (浏览器默认)' },
  { code: 'zh-CN', flag: '🇨🇳', label: '简体中文' },
  { code: 'en-US', flag: '🇺🇸', label: 'English (US)' },
];
const PRESET_COLORS = [
  { name: 'iCoDer Blue', value: '#3C61DD' }, { name: 'Red', value: '#DC2626' },
  { name: 'Green', value: '#16A34A' }, { name: 'Purple', value: '#7C3AED' },
  { name: 'Orange', value: '#EA580C' }, { name: 'Teal', value: '#0D9488' },
];

const TOUR_STEPS = [
  { title: '欢迎', icon: Asterisk, content: '本指南将引导您完成嵌入助手的配置和测试。拖动浮动卡片可重新定位。' },
  { title: '配置', icon: Settings, content: '在设置面板中配置助手默认模式、功能开关和主题颜色。更改将在刷新会话后生效。' },
  { title: '语音', icon: Mic, content: '选择STT引擎（服务器端使用FunASR，浏览器端使用内置引擎）。选择您的口语语言和听写语言。' },
  { title: '代码', icon: Code, content: '切换到代码选项卡，选择HTML/React/JSON格式。复制代码片段将助手嵌入到HIS/EMR前端。' },
  { title: '事件', icon: Activity, content: '底部的事件查看器显示实时调试信息——录音状态、转录进度和API调用。' },
];

type InspectorEvent = { id: string; timestamp: number; type: 'success' | 'error' | 'warning' | 'info'; label: string; detail: string };

export default function EmbeddedAssistantPage() {
  const t = useT();
  const locale = useLocaleStore(s => s.locale);
  const addCost = useCostStore(s => s.addCost);

  // Session defaults
  const [mode, setMode] = useState('virtual');
  const [language, setLanguage] = useState(locale === 'zh-CN' ? 'zh-CN' : 'en-US');
  const [dictationLang, setDictationLang] = useState(locale === 'zh-CN' ? 'zh-CN' : 'en-US');
  const [interfaceLang, setInterfaceLang] = useState('auto');
  // Features
  const [allowVirtual, setAllowVirtual] = useState(true);
  const [showTitle, setShowTitle] = useState(false);
  const [enableAiChat, setEnableAiChat] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [enableEditor, setEnableEditor] = useState(true);
  const [showNav, setShowNav] = useState(true);
  const [showSyncDocument, setShowSyncDocument] = useState(false);
  // Appearance
  const [primaryColor, setPrimaryColor] = useState('#3C61DD');
  // STT
  const [sttMode, setSttMode] = useState<'browser' | 'server'>('browser');
  // Session
  const [sessionKey, setSessionKey] = useState(0);
  const [initializing, setInitializing] = useState(true);
  const [balance, setBalance] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  // Preview
  const [previewView, setPreviewView] = useState<'desktop' | 'mobile'>('desktop');
  const [previewTranscript, setPreviewTranscript] = useState('');
  const [interimText, setInterimText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const recordingRef = useRef(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [bufferingBytes, setBufferingBytes] = useState(0);
  // Tour
  const [showPreviewMenu, setShowPreviewMenu] = useState(false);
  const [showMicMenu, setShowMicMenu] = useState(false);
  const [showAiChat, setShowAiChat] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [showTour, setShowTour] = useState(true);
  const [tourOpen, setTourOpen] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  // Inspector
  const [inspectorEvents, setInspectorEvents] = useState<InspectorEvent[]>([]);
  const inspectorIdRef = useRef(0);
  // Context tabs — iCoDer-style document switching
  const [encounterTabs, setEncounterTabs] = useState([
    { id: 'encounter-1', name: '诊疗记录' },
  ]);
  const [activeEncounterId, setActiveEncounterId] = useState('encounter-1');
  const [showAddTabMenu, setShowAddTabMenu] = useState(false);

  // WebSocket / recording refs
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const interimTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const getRecognitionRef = useRef<() => any>(() => null);

  const addInspectorEvent = useCallback((type: InspectorEvent['type'], label: string, detail: string) => {
    inspectorIdRef.current += 1;
    setInspectorEvents(p => [...p.slice(-50), { id: `evt-${inspectorIdRef.current}`, timestamp: Date.now(), type, label, detail }]);
    addCost(0.0001);
  }, [addCost]);

  const restartSession = useCallback(() => {
    setInitializing(true);
    setTimeout(() => setInitializing(false), 800);
    setSessionKey(k => k + 1); setPreviewTranscript(''); setInterimText(''); setInspectorEvents([]);
    setIsProcessing(false); setIsRecording(false); recordingRef.current = false;
    if (sttMode === 'browser') { try { getRecognitionRef.current()?.stop(); } catch { } }
    else { if (interimTimerRef.current) { clearInterval(interimTimerRef.current); interimTimerRef.current = null; } try { mediaRecorderRef.current?.stop(); } catch { } wsRef.current?.close(); }
  }, [sttMode]);

  // Init
  useEffect(() => {
    const timer = setTimeout(() => setInitializing(false), 1200);
    Promise.allSettled([billingApi.balance().then(r => setBalance(r.data.balance))])
      .finally(() => { setInitializing(false); setLoading(false); clearTimeout(timer); });
    return () => clearTimeout(timer);
  }, []);

  // Browser SpeechRecognition
  const getRecognition = useCallback((): any => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return null;
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = dictationLang || language;
    rec.onresult = (event: any) => {
      let interim = '', final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        r.isFinal ? final += r[0].transcript : interim += r[0].transcript;
      }
      if (final) {
        setPreviewTranscript(p => (p + final).trim());
        setInterimText('');
        addInspectorEvent('success', '转录', final.slice(0, 60));
      } else {
        setInterimText(interim);
      }
    };
    rec.onerror = (event: any) => {
      addInspectorEvent('error', '识别错误', event.error || 'unknown');
      setIsRecording(false); recordingRef.current = false;
    };
    rec.onend = () => { if (recordingRef.current) { try { rec.start(); } catch {} } };
    return rec;
  }, [dictationLang, language, addInspectorEvent]);

  useEffect(() => { getRecognitionRef.current = getRecognition; }, [getRecognition]);

  // Recording logic
  const toggleRecording = useCallback(() => {
    if (isRecording) {
      recordingRef.current = false; setIsRecording(false);
      if (interimTimerRef.current) { clearInterval(interimTimerRef.current); interimTimerRef.current = null; }
      setInterimText('');
      setBufferingBytes(0);
      if (sttMode === 'browser') {
        try { getRecognitionRef.current()?.stop(); } catch {}
        addInspectorEvent('info', '录音已停止', '浏览器引擎');
      } else {
        try { mediaRecorderRef.current?.stop(); } catch {}
        try { wsRef.current?.close(); } catch {}
        addInspectorEvent('info', '录音已停止', 'Medvoice引擎');
      }
      setIsProcessing(true); setTimeout(() => setIsProcessing(false), 800);
    } else {
      recordingRef.current = true; setIsRecording(true);
      if (sttMode === 'browser') {
        const rec = getRecognitionRef.current();
        if (rec) {
          try { rec.start(); } catch {}
          addInspectorEvent('info', '录音已开始', '浏览器引擎');
        } else {
          addInspectorEvent('error', '浏览器不支持语音识别', '请使用 Chrome 或 Edge');
          setIsRecording(false); recordingRef.current = false;
        }
      } else {
        // Server mode: simulate with periodic mock transcription
        addInspectorEvent('info', '录音已开始', 'Medvoice引擎');
        interimTimerRef.current = setInterval(() => {
          if (!recordingRef.current) { clearInterval(interimTimerRef.current!); return; }
          setBufferingBytes(b => b + 256);
        }, 500);
      }
    }
  }, [isRecording, sttMode, addInspectorEvent]);

  const tourIcon = (step: number) => { const T = TOUR_STEPS[step]; if (!T) return null; const Icon = T.icon; return <Icon size={16} />; };

  return (
    <div className="flex flex-col h-full bg-background" key={sessionKey}>
      {/* ==================== HEADER (breadcrumb — cost/Docs in global header) ==================== */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-border/20 shrink-0 text-xs">
        <Link to="/ai-studio/overview" className="text-muted-foreground hover:text-foreground transition-colors">{t.aiStudio}</Link>
        <ChevronRight size={12} className="text-muted-foreground/50" />
        <span className="text-foreground font-medium truncate">{t.embeddedAssistantBreadcrumb}</span>
      </div>

      <div className="flex h-full">
      {/* ===== LEFT: Preview Panel (75%) ===== */}
      <div className="flex flex-col overflow-hidden bg-muted/30" style={{ flex: '75 1 0px' }}>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="flex h-full flex-col p-4">
            {/* Content — iCoDer embedded assistant preview, Apple minimalist */}
            <div className={`min-h-0 flex-1 overflow-auto flex ${previewView === 'mobile' ? '' : 'justify-center'}`}>
              <div className={`relative ${previewView === 'mobile' ? 'w-full max-w-[375px] mx-auto min-h-[600px]' : 'w-full max-w-[670px] h-0'}`} style={previewView === 'mobile' ? {} : { paddingBottom: '56.25%' }}>
                <div className="absolute inset-0 bg-background rounded-xl shadow-lg shadow-black/5 ring-1 ring-border/20 flex flex-col overflow-hidden">
                {initializing ? (
                  <div className="flex flex-col items-center justify-center flex-1 gap-3">
                    <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                    <p className="text-sm font-medium text-foreground">{t.embedInitializing}
</p>
                  </div>
                ) : (
                  <>
                    {/* iCoDer header */}
                    <div className="px-5 pt-5 pb-2 flex items-start justify-between">
                      <div>
                        <span className="text-[11px] text-muted-foreground tracking-wide">{t.embedPreview}
</span>
                        <h2 className="text-base font-semibold text-foreground mt-0.5">{t.embedPreviewSession}
</h2>
                      </div>
                      {/* Mobile/Desktop toggle */}
                      <div className="flex items-center gap-0.5 bg-muted rounded-lg p-0.5">
                        <button onClick={() => setPreviewView('desktop')}
                          className={`p-1 rounded-md transition-colors ${previewView === 'desktop' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                          title={t.embedDesktopView}
>
                          <Monitor size={14} />
                        </button>
                        <button onClick={() => setPreviewView('mobile')}
                          className={`p-1 rounded-md transition-colors ${previewView === 'mobile' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                          title={t.embedMobileView}
>
                          <Smartphone size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Context tabs */}
                    <div className="flex items-center gap-1.5 px-5 pb-3 border-b border-border/20">
                      <div className="flex items-center gap-1.5 flex-1 overflow-x-auto">
                        {encounterTabs.map(tab => (
                          <button key={tab.id} onClick={() => setActiveEncounterId(tab.id)}
                            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg whitespace-nowrap transition-all border ${
                              activeEncounterId === tab.id
                                ? 'bg-primary/5 border-primary/25 text-primary shadow-sm'
                                : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/60'
                            }`}>
                            <Layout size={13} />
                            {tab.name}
                          </button>
                        ))}
                      </div>
                      <div className="relative">
                        <button onClick={() => setShowAddTabMenu(!showAddTabMenu)}
                          className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"><Plus size={14} /></button>
                        {showAddTabMenu && (
                          <div className="absolute top-full right-0 mt-1 bg-popover border border-border rounded-xl shadow-lg py-1 z-30 min-w-[170px]">
                            {['日常病程记录', '入院记录', '出院小结', '手术记录', '会诊记录', '转诊信'].map(name => (
                              <button key={name} onClick={() => {
                                setEncounterTabs(prev => [...prev, { id: `encounter-${Date.now()}`, name }]);
                                setShowAddTabMenu(false);
                              }}
                                className="w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors">{name}</button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Content area */}
                    <div className="flex-1 flex flex-col p-5 relative">
                      {/* Menu — top-left corner, iCoDer-style */}
                      <div className="absolute top-1 left-1 z-10">
                        <div className="relative">
                          <button onClick={() => setShowPreviewMenu(!showPreviewMenu)}
                            className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors">
                            <GripVertical size={14} />
                          </button>
                          {showPreviewMenu && (
                            <div className="absolute top-full left-0 mt-1 bg-popover border border-border rounded-xl shadow-lg py-1 z-30 min-w-[200px]">
                              <button onClick={() => { setShowPreviewMenu(false); restartSession(); }}
                                className="w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors flex items-center gap-2.5 whitespace-nowrap">
                                <RefreshCw size={13} className="text-muted-foreground shrink-0" />
                                <span className="shrink-0">{t.embedRestartSession}
</span>
                                <span className="text-[10px] text-muted-foreground/60 ml-auto">{t.embedOnRefresh}
</span>
                              </button>
                              <div className="border-t border-border my-0.5" />
                              <button onClick={() => { setShowPreviewMenu(false); navigator.clipboard.writeText('<!-- iCoDer Embedded Assistant -->\n<icoder-embedded id="icoder-assistant"></icoder-embedded>'); }}
                                className="w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors flex items-center gap-2.5 whitespace-nowrap">
                                <Copy size={13} className="text-muted-foreground shrink-0" />
                                <span>{t.embedCopyEmbedCode}
</span>
                              </button>
                              <button onClick={() => { setShowPreviewMenu(false); window.open('/ai-studio/embedded-assistant', '_blank'); }}
                                className="w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors flex items-center gap-2.5 whitespace-nowrap">
                                <ExternalLink size={13} className="text-muted-foreground shrink-0" />
                                <span>{t.embedOpenInNewWindow}
</span>
                              </button>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Recording indicator */}
                      {isRecording && (
                        <div className="flex items-center gap-2 mb-3">
                          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                          <span className="text-xs text-muted-foreground">{t.embedRecording}
</span>
                        </div>
                      )}

                      {/* AI Chat floating button */}
                      <div className="absolute bottom-20 right-5 z-10">
                        <button onClick={() => setShowAiChat(!showAiChat)}
                          className={`w-9 h-9 rounded-full flex items-center justify-center shadow-md transition-all ${
                            showAiChat
                              ? 'bg-primary text-primary-foreground scale-95'
                              : 'bg-gradient-to-br from-primary to-indigo-500 text-white hover:scale-105 hover:shadow-lg'
                          }`}
                          title={t.embedAiChat}
>
                          <Sparkles size={16} />
                        </button>
                        {showAiChat && (
                          <div className="absolute bottom-full right-0 mb-2 w-[320px] h-[280px] bg-popover border border-border rounded-xl shadow-lg flex flex-col">
                            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border shrink-0">
                              <span className="text-xs font-medium">{t.embedAiChat}
</span>
                              <button onClick={() => setShowAiChat(false)} className="p-0.5 rounded hover:bg-accent"><X size={12} /></button>
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 text-xs text-muted-foreground">
                              <p>{t.embedAiChatDesc}
</p>
                            </div>
                            <div className="p-3 border-t border-border shrink-0">
                              <input placeholder={t.embedAskQuestion}

                                className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-2 focus:ring-ring" />
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Editor / Write something area */}
                      {showEditor ? (
                        <div className="flex-1 flex flex-col">
                          <div className="flex items-start gap-3">
                            <Pencil size={14} className="text-muted-foreground mt-1.5 shrink-0" />
                            <textarea
                              value={isRecording ? (interimText || previewTranscript) : previewTranscript}
                              onChange={(e) => setPreviewTranscript(e.target.value)}
                              placeholder={t.embedWriteSomething}

                              readOnly={isRecording}
                              rows={1}
                              autoFocus
                              className="flex-1 resize-none border-0 bg-transparent p-0 text-[15px] leading-relaxed focus:outline-none placeholder:text-muted-foreground/40 overflow-hidden"
                              style={{ minHeight: '28px' }}
                              onInput={(e) => { const el = e.currentTarget; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }}
                              onBlur={() => { if (!previewTranscript && !isRecording) setShowEditor(false); }}
                            />
                            {/* Voice input button — inline with editor */}
                            <button onClick={toggleRecording}
                              className={`p-1.5 rounded-lg shrink-0 transition-colors ${
                                isRecording
                                  ? 'bg-red-500 text-white'
                                  : 'text-muted-foreground hover:text-primary hover:bg-primary/5'
                              }`}
                              title={isRecording ? t.embedStopRecording : t.embedVoiceInput}>
                              {isRecording ? <MicOff size={15} /> : <Mic size={15} />}
                            </button>
                          </div>
                          {/* Transcription display */}
                          {showTranscript && (
                            <div className="mt-4 p-3 rounded-xl bg-muted/30 max-h-32 overflow-y-auto">
                              {previewTranscript ? (
                                <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">{previewTranscript}</p>
                              ) : (
                                <p className="text-xs text-muted-foreground/40 italic">{t.embedTranscriptionPlaceholder}
</p>
                              )}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div
                          onClick={() => setShowEditor(true)}
                          className="flex-1 flex flex-col items-center justify-center cursor-text">
                          <button
                            onClick={(e) => { e.stopPropagation(); setShowEditor(true); }}
                            className="inline-flex items-center gap-2 text-[15px] text-muted-foreground/60 hover:text-foreground transition-colors py-2 px-5 rounded-xl hover:bg-accent/40">
                            <Pencil size={15} />
                            {t.embedWriteSomething}

                          </button>
                          {!previewTranscript && !isRecording && (
                            <p className="text-xs text-muted-foreground/50 mt-3 text-center leading-relaxed max-w-[320px]">
                              {t.embedStartRecordingHint}

                            </p>
                          )}
                        </div>
                      )}

                      {/* Record button area — iCoDer: blue pill + small gray controls */}
                      <div className="pt-4 border-t border-border/20 mt-auto flex justify-center items-center gap-2">
                        <button onClick={toggleRecording}
                          className={`flex items-center gap-1.5 px-5 py-2 rounded-full text-xs font-medium transition-all shadow-sm ${
                            isRecording
                              ? 'bg-red-500 text-white shadow-red-500/20'
                              : 'bg-primary text-primary-foreground hover:opacity-90 shadow-primary/20'
                          }`}>
                          {isRecording ? <MicOff size={14} /> : <Mic size={14} />}
                          <span>{isRecording ? t.embedStop : t.embedRecord}</span>
                        </button>

                        {/* Mic source selector */}
                        <div className="relative">
                          <button onClick={() => setShowMicMenu(!showMicMenu)}
                            className={`p-2 rounded-lg transition-colors ${
                              showMicMenu ? 'bg-accent text-foreground' : 'text-muted-foreground/50 hover:text-foreground hover:bg-accent'
                            }`}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/></svg>
                          </button>
                          {showMicMenu && (
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 bg-popover border border-border rounded-xl shadow-lg py-1 z-30 w-40">
                              <button onClick={() => { setSttMode('browser'); setShowMicMenu(false); }}
                                className={`w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors flex items-center gap-2 ${sttMode === 'browser' ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
                                {sttMode === 'browser' && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
                                <span className={sttMode !== 'browser' ? 'ml-5' : ''}>Web 内置</span>
                              </button>
                              <button onClick={() => { setSttMode('server'); setShowMicMenu(false); }}
                                className={`w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors flex items-center gap-2 ${sttMode === 'server' ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
                                {sttMode === 'server' && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
                                <span className={sttMode !== 'server' ? 'ml-5' : ''}>Medvoice</span>
                              </button>
                            </div>
                          )}
                        </div>

                        {/* Transcript toggle */}
                        <button onClick={() => setShowTranscript(!showTranscript)}
                          className={`p-2 rounded-lg transition-colors ${
                            showTranscript ? 'bg-accent text-foreground' : 'text-muted-foreground/50 hover:text-foreground hover:bg-accent'
                          }`}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="2 8 2 2 6 2"/><polyline points="22 8 22 2 18 2"/>
                            <line x1="8" y1="12" x2="16" y2="12"/><line x1="9" y1="16" x2="15" y2="16"/><line x1="10" y1="20" x2="14" y2="20"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  </>
                )}
                </div>
              </div>
            </div>

            {/* Event Inspector */}
            <EventInspector
              events={inspectorEvents.map(evt => ({
                type: evt.type,
                data: { label: evt.label, detail: evt.detail },
                timestamp: new Date(evt.timestamp).toLocaleTimeString(locale, { hour12: false }),
                credits: 0.0001,
              }))}
              creditsConsumed={inspectorEvents.reduce((s, e) => s + (e.type === 'success' || e.type === 'info' ? 0.0001 : 0), 0)} />
          </div>
        </div>
      </div>

      {/* ===== Separator ===== */}
      <div className="h-full w-px bg-border/60" />

      {/* ===== RIGHT: Settings Panel (30%) ===== */}
      <div className="flex flex-col overflow-hidden bg-muted/10" style={{ flex: '30 1 0px' }}>
        <div className="flex h-full flex-col overflow-hidden">
          <SettingsCodeTab
            labels={{ settings: t.embedSettingsLabel, code: t.embedCodeLabel }}
            settings={
              <div className="flex flex-col">
                {/* Restart hint */}
                <div className="px-4 py-2.5 bg-muted/30 border-b border-border/30">
                  <p className="text-[11px] text-muted-foreground">{t.embedRestartSessionHint}
</p>
                </div>

                {/* Session defaults */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">{t.embedSessionDefaults}
</h3>
                  </div>
                  <div className="flex flex-col gap-3 px-4 pb-4">
                    <div className="flex items-center justify-between gap-4 min-h-[32px]">
                      <label className="text-sm text-foreground/80">{t.embedPrimaryLanguage}
</label>
                      <select value={language} onChange={e => setLanguage(e.target.value)}
                        className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-ring">
                        {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.flag} {l.label}</option>)}
                      </select>
                    </div>
                    <div className="flex items-center justify-between gap-4 min-h-[32px]">
                      <label className="text-sm text-foreground/80">{t.embedDefaultMode}
</label>
                      <RadioGroup options={[
                        { key: 'in_person', label: t.embedModeInPerson },
                        ...(allowVirtual ? [{ key: 'virtual', label: t.embedModeVirtual }] : []),
                      ]} value={mode} onChange={setMode} />
                    </div>
                  </div>
                </div>

                {/* Features */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">{t.embedFeatures}
</h3>
                  </div>
                  <div className="flex flex-col px-4 pb-4">
                    {[
                      { k: 'allowVirtual', l: t.embedFeatureAllowVirtual, v: allowVirtual, s: setAllowVirtual },
                      { k: 'showTitle', l: t.embedFeatureShowTitle, v: showTitle, s: setShowTitle },
                      { k: 'enableAiChat', l: t.embedFeatureEnableAiChat, v: enableAiChat, s: setEnableAiChat },
                      { k: 'showFeedback', l: t.embedFeatureShowFeedback, v: showFeedback, s: setShowFeedback },
                      { k: 'enableEditor', l: t.embedFeatureEnableEditor, v: enableEditor, s: setEnableEditor },
                      { k: 'showNav', l: t.embedFeatureShowNav, v: showNav, s: setShowNav },
                      { k: 'showSyncDocument', l: t.embedFeatureShowSync, v: showSyncDocument, s: setShowSyncDocument },
                    ].map(f => (
                      <div key={f.k} className="flex items-center justify-between min-h-[36px]">
                        <span className="text-sm text-foreground/70">{f.l}</span>
                        <Switch checked={f.v} onChange={f.s} />
                      </div>
                    ))}
                  </div>
                </div>

                {/* Appearance */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">{t.embedAppearance}
</h3>
                  </div>
                  <div className="flex flex-col gap-3 px-4 pb-4">
                    <div className="flex items-center justify-between gap-4 min-h-[32px]">
                      <label className="text-sm text-foreground/80">{t.embedPrimaryColor}
</label>
                      <div className="flex items-center gap-2">
                        <input type="color" value={primaryColor} onChange={e => setPrimaryColor(e.target.value)}
                          className="w-7 h-7 rounded-md border border-input cursor-pointer p-0.5 bg-transparent" />
                        <input type="text" value={primaryColor} onChange={e => setPrimaryColor(e.target.value)}
                          className="h-7 w-[72px] text-[11px] font-mono border border-input rounded-md px-2 py-1 bg-transparent focus:outline-none focus:ring-2 focus:ring-ring" />
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5 ml-[1px]">
                      {PRESET_COLORS.map(c => {
                        const active = primaryColor.toLowerCase() === c.value.toLowerCase();
                        return <button key={c.value} onClick={() => setPrimaryColor(c.value)} className="w-5 h-5 rounded-full transition-all duration-150 hover:scale-110"
                          style={{ backgroundColor: c.value, outline: active ? '2px solid hsl(var(--foreground))' : '1px solid hsl(var(--border))', outlineOffset: active ? '2px' : '0px' }} title={c.name} />;
                      })}
                    </div>
                  </div>
                </div>

                {/* Locale */}
                <div>
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">{t.embedLocaleSection}
</h3>
                  </div>
                  <div className="flex flex-col gap-3 px-4 pb-4">
                    <div className="flex items-center justify-between gap-4 min-h-[32px]">
                      <label className="text-sm text-foreground/80">{t.embedInterfaceLanguage}
</label>
                      <select value={interfaceLang} onChange={e => setInterfaceLang(e.target.value)}
                        className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-ring">
                        {INTERFACE_LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.flag} {l.label}</option>)}
                      </select>
                    </div>
                    <div className="flex items-center justify-between gap-4 min-h-[32px]">
                      <label className="text-sm text-foreground/80">{t.embedDictationLanguage}
</label>
                      <select value={dictationLang} onChange={e => setDictationLang(e.target.value)}
                        className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-ring">
                        {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.flag} {l.label}</option>)}
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            }
            code={
              <CodeSnippet
                javascript={`import { iCoDerAssistant } from '@icoder/embedded-web';\n\nconst assistant = document.getElementById('icoder-assistant');\nassistant.addEventListener('ready', async () => {\n  await assistant.auth({\n    access_token: 'YOUR_ACCESS_TOKEN',\n    refresh_token: 'YOUR_REFRESH_TOKEN',\n    token_type: 'bearer',\n    mode: 'stateless',\n  });\n  await assistant.configureSession({\n    defaultLanguage: '${dictationLang === 'zh-CN' ? 'zh' : 'en'}',\n    defaultMode: '${mode}',\n    defaultOutputLanguage: '${dictationLang === 'zh-CN' ? 'zh' : 'en'}',\n  });\n  await assistant.configure({\n    features: {\n      aiChat: ${enableAiChat},\n      documentFeedback: ${showFeedback},\n      interactionTitle: ${showTitle},\n      navigation: ${showNav},\n      templateEditor: ${enableEditor},\n      syncDocument: ${showSyncDocument},\n      virtualMode: ${allowVirtual},\n    },\n    locale: { dictationLanguage: '${dictationLang === 'zh-CN' ? 'zh' : 'en'}' },\n    appearance: { primaryColor: '${primaryColor}' },\n  });\n  await assistant.show();\n});`}
                python={`from icoder_embedded import iCoDerAssistantClient\n\nclient = iCoDerAssistantClient(\n    api_key="YOUR_API_KEY",\n    base_url="${BACKEND_BASE_URL}",\n)\n\nclient.configure_session(\n    default_language="${dictationLang === 'zh-CN' ? 'zh' : 'en'}",\n    default_mode="${mode}",\n)\n\nclient.configure(\n    features={\n        "aiChat": ${enableAiChat},\n        "documentFeedback": ${showFeedback},\n        "interactionTitle": ${showTitle},\n        "navigation": ${showNav},\n        "templateEditor": ${enableEditor},\n        "syncDocument": ${showSyncDocument},\n        "virtualMode": ${allowVirtual},\n    },\n    appearance={"primaryColor": "${primaryColor}"},\n)\n\nclient.show()`}
                json={JSON.stringify({
                  mode,
                  features: {
                    allowVirtualMode: allowVirtual, showInteractionTitle: showTitle, enableAiChat,
                    showDocumentFeedback: showFeedback, enableTemplateEditor: enableEditor,
                    showNavigation: showNav, showSyncDocumentAction: showSyncDocument,
                  },
                  locale: { dictationLanguage: dictationLang, interfaceLanguage: interfaceLang },
                  appearance: { primaryColor },
                }, null, 2)}
              />
            }
          />
        </div>
      </div>

      {/* ===== Tour ===== */}
      {showTour && (
        <div className="fixed z-40 max-w-xs bg-card rounded-xl border border-border shadow-lg p-3" style={{ right: '1rem', bottom: '1rem' }}>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5" style={{ backgroundColor: `${primaryColor}18` }}>
              <Asterisk size={14} style={{ color: primaryColor }} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium mb-1">{t.embedNewToAssistant}
</p>
              <div className="flex items-center gap-2">
                <button className="text-xs font-medium hover:underline" style={{ color: primaryColor }}
                  onClick={(e) => { e.stopPropagation(); setTourStep(0); setTourOpen(true); }}>
                  {t.embedTakeTour}

                </button>
                <button onClick={(e) => { e.stopPropagation(); setShowTour(false); }}
                  className="text-xs text-muted-foreground hover:text-foreground">{t.embedDismiss}
</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {tourOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setTourOpen(false)}>
          <div className="bg-card rounded-xl border border-border shadow-xl w-full max-w-md mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b">
              <div className="flex items-center gap-2.5" style={{ color: primaryColor }}>{tourIcon(tourStep)}<h2 className="text-sm font-semibold">{TOUR_STEPS[tourStep].title}</h2><span className="text-[10px] text-muted-foreground font-mono ml-1">{tourStep + 1}/{TOUR_STEPS.length}</span></div>
              <button onClick={() => setTourOpen(false)} className="p-1 rounded hover:bg-accent"><X size={16} className="text-muted-foreground" /></button>
            </div>
            <div className="p-5">
              <p className="text-sm text-muted-foreground leading-relaxed">{TOUR_STEPS[tourStep].content}</p>
              <div className="flex items-center justify-center gap-1.5 mt-5">
                {TOUR_STEPS.map((_, i) => <div key={i} className={`h-1.5 rounded-full transition-all duration-200 ${i === tourStep ? 'w-5' : 'w-1.5 bg-muted-foreground/20'}`} style={i === tourStep ? { backgroundColor: primaryColor } : undefined} />)}
              </div>
            </div>
            <div className="flex items-center justify-between px-5 py-3 border-t bg-muted/20">
              <button onClick={() => setTourOpen(false)} className="text-xs text-muted-foreground hover:text-foreground">{t.embedSkipTour}
</button>
              <div className="flex items-center gap-2">
                {tourStep > 0 && <button onClick={() => setTourStep(s => s - 1)} className="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium rounded-lg transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground text-xs h-8 px-3">{t.embedPrevStep}
</button>}
                <button onClick={() => { if (tourStep < TOUR_STEPS.length - 1) setTourStep(s => s + 1); else setTourOpen(false); }}
                  className="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium rounded-lg transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring text-xs h-8 px-4 text-white" style={{ backgroundColor: primaryColor }}>
                  {tourStep < TOUR_STEPS.length - 1 ? t.embedNextStep : t.embedGetStarted}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
