/** @type {import('tailwindcss').Config} */
// Colors are backed by CSS variables (RGB channel triples) so a single `.dark` class
// on <html> reskins the whole app while every Tailwind opacity utility (teal/40,
// line/60, panel/80, …) keeps working. Light values resolve to the exact prior hex,
// so the light theme is unchanged. See src/index.css for the :root / .dark palettes.
const withVar = (v) => `rgb(var(${v}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Single teal accent over a near-monochrome neutral scale (Apple-minimal).
        teal: {
          DEFAULT: withVar("--c-teal"),
          50: withVar("--c-teal-50"),
          100: withVar("--c-teal-100"),
          600: withVar("--c-teal-600"),
          700: withVar("--c-teal-700"),
        },
        ink: withVar("--c-ink"),
        muted: withVar("--c-muted"),
        faint: withVar("--c-faint"),
        line: withVar("--c-line"),
        surface: withVar("--c-surface"),
        canvas: withVar("--c-canvas"),
        // Elevated surface (cards, inputs, sticky bar). Light = white; dark = lifted slate.
        panel: withVar("--c-panel"),
      },
      fontFamily: {
        sans: [
          "-apple-system", "BlinkMacSystemFont", "Inter", "Segoe UI",
          "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "system-ui", "sans-serif",
        ],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: { xl2: "14px" },
      boxShadow: {
        // Whisper-soft, Apple-restrained — no heavy drop shadows.
        card: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
        lift: "0 4px 16px rgba(16,24,40,0.08)",
      },
      transitionDuration: { fast: "120ms", base: "200ms" },
    },
  },
  plugins: [],
};
