// iCoDer Home - Corti Project Home 4-tab IA replica.
// Source: /project/<id> on console.corti.app - 4 entry-point tabs:
//   Transcribe / Document / Chat / Code NEW.
// Each tab is a card with a one-line description + a CTA that links into
// the matching AI Studio workbench.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mic, FileText, MessageSquare, Stethoscope, ArrowRight, Sparkles,
} from 'lucide-react';

import { useT } from '../i18n';

interface HomeTab {
  key: 'transcribe' | 'document' | 'chat' | 'code';
  labelKey: 'homeTabTranscribe' | 'homeTabDocument' | 'homeTabChat' | 'homeTabCode';
  descKey: 'homeTabTranscribeDesc' | 'homeTabDocumentDesc' | 'homeTabChatDesc' | 'homeTabCodeDesc';
  ctaKey: 'homeTabTranscribeCta' | 'homeTabDocumentCta' | 'homeTabChatCta' | 'homeTabCodeCta';
  to: string;
  icon: any;
  badge?: 'NEW';
}

const TABS: HomeTab[] = [
  {
    key: 'transcribe',
    labelKey: 'homeTabTranscribe',
    descKey: 'homeTabTranscribeDesc',
    ctaKey: 'homeTabTranscribeCta',
    to: '/ai-studio/speech-to-text',
    icon: Mic,
  },
  {
    key: 'document',
    labelKey: 'homeTabDocument',
    descKey: 'homeTabDocumentDesc',
    ctaKey: 'homeTabDocumentCta',
    // Phase 3-B2 Loop 0: TextGeneration deprecated - redirect to Medical Coding
    // (closest available document workflow). Will be re-pointed to a real
    // Guided Documents page in Phase 3-C.
    to: '/ai-studio/medical-coding',
    icon: FileText,
  },
  {
    key: 'chat',
    labelKey: 'homeTabChat',
    descKey: 'homeTabChatDesc',
    ctaKey: 'homeTabChatCta',
    // Phase 3-B2 Loop 0: EmbeddedAssistant deprecated - redirect to Agent Hub.
    // Loop 2 will land a real Chat page at /agents/{id}/chat.
    to: '/ai-studio/agents',
    icon: MessageSquare,
  },
  {
    key: 'code',
    labelKey: 'homeTabCode',
    descKey: 'homeTabCodeDesc',
    ctaKey: 'homeTabCodeCta',
    to: '/ai-studio/medical-coding',
    icon: Stethoscope,
    badge: 'NEW',
  },
];

export default function HomePage() {
  const t = useT();
  const navigate = useNavigate();
  const [active, setActive] = useState<HomeTab['key']>('transcribe');

  // Reset scroll when tab changes
  useEffect(() => {
    const el = document.getElementById('home-content');
    if (el) el.scrollTop = 0;
  }, [active]);

  const tab = TABS.find(x => x.key === active) ?? TABS[0];
  const TabIcon = tab.icon;

  return (
    <div className="flex h-full bg-muted/20">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl px-6 py-8 space-y-6">

          {/* Hero (Corti: minimal, no big heading) */}
          <div className="mb-2">
            <h1 className="text-xl font-bold text-foreground tracking-tight">{t.home}</h1>
            <p className="text-xs text-muted-foreground mt-1">{t.homeSubtitle ?? t.aiStudio}</p>
          </div>

          {/* ===== 4-tab switcher (Corti Project Home IA) ===== */}
          <div role="tablist" className="inline-flex items-center rounded-xl border border-border/20 bg-background p-1 shadow-sm">
            {TABS.map((tt) => {
              const Ic = tt.icon;
              const selected = active === tt.key;
              return (
                <button key={tt.key} role="tab" aria-selected={selected}
                  onClick={() => setActive(tt.key)}
                  className={`flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg transition-colors ${
                    selected ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}>
                  <Ic size={14} />
                  <span>{t[tt.labelKey] as string}</span>
                  {tt.badge && (
                    <span className={`text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                      selected ? 'bg-white/20 text-primary-foreground' : 'bg-primary/15 text-primary'
                    }`}>
                      {tt.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* ===== Active tab content panel ===== */}
          <div id="home-content" className="bg-background rounded-xl shadow-sm overflow-hidden">
            {/* Header (icon + label + description) */}
            <div className="px-6 py-5 border-b border-border/10">
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                  tab.badge ? 'bg-primary/10 text-primary' : 'bg-muted text-foreground'
                }`}>
                  <TabIcon size={20} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold text-foreground">{t[tab.labelKey] as string}</h2>
                    {tab.badge && (
                      <span className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/15 text-primary">
                        {tab.badge}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">{t[tab.descKey] as string}</p>
                </div>
              </div>
            </div>

            {/* CTA + value props */}
            <div className="p-6 space-y-4">
              <button onClick={() => navigate(tab.to)}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors shadow-sm">
                <Sparkles size={14} />
                {t[tab.ctaKey] as string}
                <ArrowRight size={14} />
              </button>

              {/* Per-tab value-prop list */}
              {active === 'transcribe' && (
                <ul className="text-xs text-muted-foreground space-y-1.5">
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropRealtime}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropDication}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropDetect}</li>
                </ul>
              )}
              {active === 'document' && (
                <ul className="text-xs text-muted-foreground space-y-1.5">
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropTemplate}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropMultilang}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropStructured}</li>
                </ul>
              )}
              {active === 'chat' && (
                <ul className="text-xs text-muted-foreground space-y-1.5">
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropEmbed}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropSession}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropMultimodal}</li>
                </ul>
              )}
              {active === 'code' && (
                <ul className="text-xs text-muted-foreground space-y-1.5">
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropIcdCn}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropEvidence}</li>
                  <li className="flex items-start gap-2"><span className="text-primary">·</span> {t.homePropRule}</li>
                </ul>
              )}
            </div>
          </div>

          {/* Subtle footer hint */}
          <p className="text-[10px] text-muted-foreground/60 text-center pt-2">
            {t.homeFooterHint ?? 'All workbenches support API access via API Clients.'}
          </p>
        </div>
      </div>
    </div>
  );
}