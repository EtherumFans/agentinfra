// iCoDer AI Studio Overview (Phase 3-E+)
import { useNavigate } from 'react-router-dom';
import {
  Layers, Mic, FileText, MessageSquare, Braces, Stethoscope,
  ArrowRight, ArrowUpRight, Compass, ShieldCheck, SlidersHorizontal,
  Code2, LifeBuoy, MessageCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { useT } from '../i18n';

type CapabilityCard = {
  name: string;
  desc: string;
  exploreHref: string;
  docsHref: string;
  Icon: LucideIcon;
};

type HeroCol = {
  label: string;
  desc: string;
  Icon: LucideIcon;
};

export default function AIStudioOverviewPage() {
  const navigate = useNavigate();
  const t = useT();

  const heroCols: HeroCol[] = [
    { label: t.aiStudioOverviewExploreLabel, desc: t.aiStudioOverviewExploreDesc, Icon: Compass },
    { label: t.aiStudioOverviewInspectLabel, desc: t.aiStudioOverviewInspectDesc, Icon: ShieldCheck },
    { label: t.aiStudioOverviewConfigureLabel, desc: t.aiStudioOverviewConfigureDesc, Icon: SlidersHorizontal },
  ];

  // Every capability card routes to its live standalone workbench.
  const capabilities: CapabilityCard[] = [
    {
      name: t.aiStudioOverviewAgentsName,
      desc: t.aiStudioOverviewAgentsDesc,
      exploreHref: '/ai-studio/agents',
      docsHref: '/docs',
      Icon: Layers,
    },
    {
      name: t.aiStudioOverviewSttName,
      desc: t.aiStudioOverviewSttDesc,
      exploreHref: '/ai-studio/speech-to-text',
      docsHref: '/docs',
      Icon: Mic,
    },
    {
      name: t.aiStudioOverviewTextGenName,
      desc: t.aiStudioOverviewTextGenDesc,
      exploreHref: '/ai-studio/text-generation',
      docsHref: '/docs',
      Icon: FileText,
    },
    {
      name: t.aiStudioOverviewEmbeddedName,
      desc: t.aiStudioOverviewEmbeddedDesc,
      exploreHref: '/ai-studio/embedded-assistant',
      docsHref: '/docs',
      Icon: MessageSquare,
    },
    {
      name: t.aiStudioOverviewFactExtractName,
      desc: t.aiStudioOverviewFactExtractDesc,
      exploreHref: '/ai-studio/fact-extraction',
      docsHref: '/docs',
      Icon: Braces,
    },
    {
      name: t.aiStudioOverviewCodingName,
      desc: t.aiStudioOverviewCodingDesc,
      exploreHref: '/ai-studio/medical-coding',
      docsHref: '/docs',
      Icon: Stethoscope,
    },
  ];

  const renderCapability = (cap: CapabilityCard, idx: number) => {
    const { Icon, name, desc, exploreHref, docsHref } = cap;
    return (
      <div
        key={idx}
        className="flex flex-col border-border xl:border-r border-b xl:border-b-0 xl:last:border-r-0 last:border-b-0"
      >
        {/* Image / icon preview area */}
        <div className="xl:h-52 h-32 overflow-hidden bg-muted/30 flex items-center justify-center border-border border-b">
          <Icon size={64} className="text-muted-foreground/40" />
        </div>
        <div className="flex flex-1 flex-col gap-4 p-6">
          <div className="flex flex-1 flex-col gap-1">
            <div className="flex items-center gap-2">
              <Icon size={16} className="text-foreground" />
              <p className="font-medium text-foreground text-sm">{name}</p>
            </div>
            <p className="text-base text-muted-foreground leading-6">{desc}</p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(exploreHref)}
              className="inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap font-medium text-sm transition-colors h-9 rounded-md px-3 border border-input bg-accent/0 text-foreground hover:bg-accent hover:text-accent-foreground flex-1"
            >
              {t.aiStudioOverviewExploreCta}
              <ArrowRight size={16} />
            </button>
            <a
              href={docsHref}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap font-medium text-sm transition-colors h-9 rounded-md px-3 border border-input bg-accent/0 text-foreground hover:bg-accent hover:text-accent-foreground"
            >
              {t.aiStudioOverviewDocsCta}
              <ArrowUpRight size={14} />
            </a>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex-1 overflow-y-auto bg-muted/20">
      {/* Full-width container with vertical dividers on xl */}
      <div className="mx-auto flex w-full flex-1 flex-col xl:border-x border-border bg-background">
        {/* Hero - H1 / tagline (eyebrow dropped per §4.7) */}
        <div className="flex flex-col gap-2 px-6 pt-6 pb-0">
          <h1 className="font-medium text-2xl">{t.aiStudioOverviewHeroTitle}</h1>
          <p className="text-base text-muted-foreground">{t.aiStudioOverviewHeroTagline}</p>
        </div>

        {/* 3 hero columns - Explore / Inspect / Configure */}
        <div className="mt-6 grid xl:grid-cols-3 grid-cols-1 border-border border-t">
          {heroCols.map((col, i) => {
            const { Icon, label, desc } = col;
            return (
              <div
                key={i}
                className="flex flex-col gap-2 border-border xl:border-r border-b xl:border-b-0 p-6 xl:last:border-r-0 last:border-b-0"
              >
                <div className="flex size-10 items-center justify-center rounded-lg border border-border">
                  <Icon size={20} className="text-foreground" />
                </div>
                <p className="font-medium text-foreground text-sm mt-1">{label}</p>
                <p className="text-sm text-muted-foreground leading-6">{desc}</p>
              </div>
            );
          })}
        </div>

        {/* Dashed divider */}
        <div
          className="h-[9px] w-full border-border border-t border-b"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'%3E%3Cpath d='M0 0L8 8M-1 7L1 9M7-1L9 1' stroke='%23EDEDED' stroke-opacity='0.5'/%3E%3C/svg%3E\")",
          }}
        />

        {/* "Explore capabilities" header */}
        <div className="border-border border-b px-6 py-6">
          <h2 className="font-medium text-xl">{t.aiStudioOverviewExploreCapabilities}</h2>
        </div>

        {/* First 3 capability cards */}
        <div className="grid xl:grid-cols-3 grid-cols-1 border-border border-b">
          {capabilities.slice(0, 3).map(renderCapability)}
        </div>

        {/* Next 3 capability cards */}
        <div className="grid xl:grid-cols-3 grid-cols-1 border-border border-b">
          {capabilities.slice(3, 6).map(renderCapability)}
        </div>

        {/* CTA - "Ready to dive into code?" */}
        <div className="border-border border-b p-4">
          <div className="flex h-full flex-col items-center justify-center gap-3 p-4">
            <Code2 size={32} className="text-muted-foreground" />
            <p className="text-center text-muted-foreground text-sm">{t.aiStudioOverviewDiveIntoCode}</p>
            <button
              onClick={() => navigate('/developer-quickstart')}
              className="inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap font-medium text-sm transition-colors h-9 rounded-md px-3 border border-input bg-accent/0 text-foreground hover:bg-accent hover:text-accent-foreground"
            >
              {t.aiStudioOverviewDevQuickstart}
              <ArrowRight size={16} />
            </button>
          </div>
        </div>

        {/* Dashed divider */}
        <div
          className="h-[9px] w-full border-border border-t border-b"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'%3E%3Cpath d='M0 0L8 8M-1 7L1 9M7-1L9 1' stroke='%23EDEDED' stroke-opacity='0.5'/%3E%3C/svg%3E\")",
          }}
        />

        {/* Footer - Documentation / SDKs & Tools / Need Help */}
        <div className="bg-background p-6">
          <div className="flex lg:flex-row flex-col gap-6">
            <div className="column flex flex-1 flex-col gap-3">
              <span className="column-header text-muted-foreground text-xs uppercase">
                {t.aiStudioOverviewFooterDocs}
              </span>
              <button
                onClick={() => navigate('/docs')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                {t.aiStudioOverviewFooterAuth}
                <ArrowUpRight size={14} className="opacity-0 transition-opacity group-hover/link:opacity-100" />
              </button>
              <button
                onClick={() => navigate('/docs')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                {t.aiStudioOverviewFooterGuides}
                <ArrowUpRight size={14} className="opacity-0 transition-opacity group-hover/link:opacity-100" />
              </button>
              <button
                onClick={() => navigate('/docs')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                {t.aiStudioOverviewFooterApiRef}
                <ArrowUpRight size={14} className="opacity-0 transition-opacity group-hover/link:opacity-100" />
              </button>
            </div>
            <div className="column flex flex-1 flex-col gap-3">
              <span className="column-header text-muted-foreground text-xs uppercase">
                {t.aiStudioOverviewFooterSdks}
              </span>
              <button
                onClick={() => navigate('/docs')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                {t.aiStudioOverviewFooterJsSdk}
                <ArrowUpRight size={14} className="opacity-0 transition-opacity group-hover/link:opacity-100" />
              </button>
              <button
                onClick={() => navigate('/docs')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                {t.aiStudioOverviewFooterPostman}
                <ArrowUpRight size={14} className="opacity-0 transition-opacity group-hover/link:opacity-100" />
              </button>
              <button
                onClick={() => navigate('/docs')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                {t.aiStudioOverviewFooterAiCoding}
                <ArrowUpRight size={14} className="opacity-0 transition-opacity group-hover/link:opacity-100" />
              </button>
            </div>
            <div className="column flex flex-1 flex-col gap-3">
              <span className="column-header text-muted-foreground text-xs uppercase">
                {t.aiStudioOverviewFooterHelp}
              </span>
              <button
                onClick={() => navigate('/support')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                <MessageCircle size={14} />
                {t.aiStudioOverviewFooterChat}
              </button>
              <button
                onClick={() => navigate('/support')}
                className="group/link inline-flex items-center gap-1 text-foreground text-sm hover:underline w-fit"
              >
                <LifeBuoy size={14} />
                {t.aiStudioOverviewFooterTicket}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
