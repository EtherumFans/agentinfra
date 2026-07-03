import { useState } from "react";

// Same-origin in a real deployment: the FastAPI process serves both this SPA and the
// API, so snippets that target the live origin are runnable as-is against the running
// instance. Falls back to a stable placeholder host during SSR / non-browser builds.
export function useBase(): string {
  return typeof window !== "undefined" ? window.location.origin : "https://hospital.internal";
}

// A dark, copyable code block. The copy path matters for the deployment target:
// navigator.clipboard only exists in secure contexts (https / localhost), but hospital
// on-prem is often plain-http intranet where it's undefined — so we fall back to the
// legacy execCommand('copy') textarea trick.
export function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    let ok = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
        ok = true;
      }
    } catch {
      ok = false;
    }
    if (!ok) {
      try {
        const ta = document.createElement("textarea");
        ta.value = code;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ok = document.execCommand("copy");
        ta.remove();
      } catch {
        ok = false;
      }
    }
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    }
  }

  return (
    <div className="overflow-hidden rounded-lg bg-[#0f1722]">
      <div className="flex items-center justify-between border-b border-white/5 px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-wide text-[#8596a8]">{lang}</span>
        <button
          onClick={copy}
          className="rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-[#9fb4c0] transition-colors hover:bg-white/10 hover:text-white"
        >
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="overflow-auto p-4 font-mono text-xs leading-6 text-[#cfe9e4]">{code}</pre>
    </div>
  );
}
