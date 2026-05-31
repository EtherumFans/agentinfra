// iCoDer AI Studio Overview — iCoDer 1:1 with i18n
import { useNavigate } from 'react-router-dom';
import { Bot, Mic, FileText, Puzzle, Search, Stethoscope, Asterisk, ArrowRight, ChevronRight, Eye, Wrench, Settings } from 'lucide-react';
import { useT } from '../i18n';

export default function AIStudioOverviewPage() {
  const t = useT();
  const navigate = useNavigate();

  const CAPABILITIES = [
    { to: '/ai-studio/agents', icon: Bot, title: t.agents, desc: t.overviewAgentsDesc, docUrl: '/docs/agents' },
    { to: '/ai-studio/speech-to-text', icon: Mic, title: t.speechToText, desc: t.overviewSttDesc, docUrl: '/docs/speech-to-text' },
    { to: '/ai-studio/text-generation', icon: FileText, title: t.textGeneration, desc: t.overviewTextGenDesc, docUrl: '/docs/text-generation' },
    { to: '/ai-studio/fact-extraction', icon: Search, title: t.factExtraction, desc: t.overviewFactExtDesc, docUrl: '/docs/fact-extraction' },
    { to: '/ai-studio/medical-coding', icon: Stethoscope, title: t.medicalCoding, desc: t.overviewMedCodeDesc, docUrl: '/docs/medical-coding' },
    { to: '/ai-studio/embedded-assistant', icon: Puzzle, title: t.embeddedAssistant, desc: t.overviewEmbeddedDesc, docUrl: '/docs/embedded-assistant' },
  ];

  const EXPLAINER_COLS = [
    { icon: Eye, title: t.overviewExplore, desc: t.overviewExploreDesc },
    { icon: Wrench, title: t.overviewInspect, desc: t.overviewInspectDesc },
    { icon: Settings, title: t.overviewConfigure, desc: t.overviewConfigureDesc },
  ];

  return (
    <div className="flex h-full">
      <div className="flex-1 overflow-y-auto bg-muted/20">
        <div className="mx-6 mt-6 bg-background rounded-xl shadow-sm ring-1 ring-border/20 px-6 py-5">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
            <span className="hover:text-foreground cursor-pointer" onClick={() => navigate('/')}>{t.home}</span><ChevronRight size={12} /><span className="text-foreground font-medium">{t.aiStudio}</span><ChevronRight size={12} /><span className="text-foreground font-medium">{t.overview}</span>
          </div>
          <h2 className="text-xl font-semibold text-foreground mt-1">{t.overviewTitle}</h2>
          <p className="text-sm text-muted-foreground mt-0.5">{t.overviewSubtitle}</p>
        </div>
        <div className="mx-6 mt-6 bg-background rounded-xl shadow-sm ring-1 ring-border/20 overflow-hidden">
          <div className="grid grid-cols-1 md:grid-cols-3">
            {EXPLAINER_COLS.map(col => (
              <div key={col.title} className="px-6 py-5 border-border md:border-r last:border-r-0 border-b md:border-b-0 border-border/20"><col.icon size={18} className="text-muted-foreground mb-2" /><h3 className="text-sm font-semibold text-foreground mb-1">{col.title}</h3><p className="text-xs text-muted-foreground leading-relaxed">{col.desc}</p></div>
            ))}
          </div>
        </div>
        <div className="mx-6 mt-6 flex items-center gap-2 mb-3">
          <div className="w-1 h-4 rounded-full bg-primary/40" />
          <p className="font-medium text-xs uppercase tracking-wider text-muted-foreground">{t.overviewExploreCapabilities}</p>
        </div>
        <div className="mx-6 bg-background rounded-xl shadow-sm ring-1 ring-border/20 overflow-hidden">
          {[CAPABILITIES.slice(0, 3), CAPABILITIES.slice(3, 6)].map((row, ri) => (
            <div key={ri} className="grid grid-cols-1 md:grid-cols-3 border-b border-border/20 last:border-b-0">
              {row.map(cap => (
                <div key={cap.title} className="px-6 py-5 border-border/20 md:border-r last:border-r-0 cursor-pointer hover:bg-accent/50 transition-colors" onClick={() => navigate(cap.to)}>
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0"><cap.icon size={18} /></div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-foreground mb-1">{cap.title}</h3>
                      <p className="text-xs text-muted-foreground leading-relaxed mb-2">{cap.desc}</p>
                      <div className="flex items-center gap-3">
                        <button onClick={(e) => { e.stopPropagation(); navigate(cap.to); }} className="text-xs text-primary hover:underline">{t.overviewExploreBtn}</button>
                        <a href={cap.docUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="text-xs text-muted-foreground hover:text-foreground transition-colors">{t.overviewDocsBtn}</a>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="mx-6 mt-6 mb-6 bg-background rounded-xl shadow-sm ring-1 ring-border/20 px-6 py-4 flex items-center justify-between">
          <p className="text-sm text-foreground font-medium">{t.overviewReadyToCode}</p>
          <button onClick={() => navigate('/developer-quickstart')} className="text-sm text-primary hover:underline flex items-center gap-1">{t.overviewDevQuickstart} <ArrowRight size={14} /></button>
        </div>
      </div>
    </div>
  );
}
