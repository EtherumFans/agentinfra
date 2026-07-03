import { useEffect, useRef, useState } from "react";
import type { IcoderEmbeddedElement } from "../vite-env";

export interface EmbeddedEvent {
  type: string;
  payload: unknown;
  at: number;
}

// Bridges the framework-agnostic <icoder-embedded> custom element into React:
// holds a ref to the element, re-establishes session/config when token/agent change,
// and collects its bubbling `embedded-event` bus into state for an inline event log.
// We deliberately do NOT reimplement the widget's rendering (evidence highlight,
// code cards, compliance gate, DRG route) — that all lives in the vanilla component.
export function useEmbedded(token: string, agentId: string, codingSystem: string) {
  const ref = useRef<IcoderEmbeddedElement | null>(null);
  const [events, setEvents] = useState<EmbeddedEvent[]>([]);
  // A coding-review run is a 30–40s LLM call. Mirror the widget's run lifecycle into
  // React so the host can disable the button (no double-submit) and show progress.
  const [running, setRunning] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail as { type: string; payload: unknown };
      if (detail.type === "run.started") setRunning(true);
      else if (detail.type === "run.completed" || detail.type === "error.triggered") {
        setRunning(false);
      }
      setEvents((prev) => [{ ...detail, at: Date.now() }, ...prev].slice(0, 50));
    };
    el.addEventListener("embedded-event", onEvent);
    el.configureSession({ token });
    el.configure({ agentId, codingSystem });
    return () => el.removeEventListener("embedded-event", onEvent);
  }, [token, agentId, codingSystem]);

  const run = (text: string) => {
    const el = ref.current;
    if (!el) return;
    el.configureSession({ token }); // host re-injects auth on each run (stateless)
    el.configure({ agentId, codingSystem });
    el.run(text);
  };

  const clearEvents = () => setEvents([]);

  return { ref, events, run, clearEvents, running };
}
