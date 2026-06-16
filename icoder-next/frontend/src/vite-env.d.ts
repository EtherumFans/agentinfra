/// <reference types="vite/client" />

import type { DetailedHTMLProps, HTMLAttributes } from "react";

// The vanilla <icoder-embedded> custom element, exposed to JSX/TS. Its imperative
// API (configureSession/configure/run) is called via a ref — see useEmbedded().
export interface IcoderEmbeddedElement extends HTMLElement {
  configureSession(opts: { token: string }): void;
  configure(cfg: { agentId?: string; codingSystem?: string }): void;
  run(text: string): void;
}

declare global {
  namespace JSX {
    interface IntrinsicElements {
      "icoder-embedded": DetailedHTMLProps<
        HTMLAttributes<HTMLElement> & { "base-url"?: string; ref?: React.Ref<IcoderEmbeddedElement> },
        HTMLElement
      >;
    }
  }
}
