/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      // Semantic color tokens — reference CSS custom properties defined in index.css
      // (light values in :root, dark values in .dark). Switching <html class="dark">
      // cascades the new values through every class below.
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        muted: 'hsl(var(--muted))',
        'muted-foreground': 'hsl(var(--muted-foreground))',

        // Vermillion primary — Chinese medical seal red
        primary: 'hsl(var(--primary))',
        'primary-foreground': 'hsl(var(--primary-foreground))',

        // Jade secondary — accuracy, confirmed, success
        secondary: 'hsl(var(--secondary))',
        'secondary-foreground': 'hsl(var(--secondary-foreground))',

        // Warm gray accents
        accent: 'hsl(var(--accent))',
        'accent-foreground': 'hsl(var(--accent-foreground))',

        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',

        destructive: 'hsl(var(--destructive))',
        'destructive-foreground': 'hsl(var(--destructive-foreground))',

        // Sidebar
        sidebar: 'hsl(var(--sidebar-background))',
        'sidebar-foreground': 'hsl(var(--sidebar-foreground))',
        'sidebar-border': 'hsl(var(--sidebar-border))',
        'sidebar-primary': 'hsl(var(--sidebar-primary))',
        'sidebar-primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
        'sidebar-accent': 'hsl(var(--sidebar-accent))',
        'sidebar-accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
        'sidebar-ring': 'hsl(var(--sidebar-ring))',

        // Card / popover
        card: 'hsl(var(--card))',
        'card-foreground': 'hsl(var(--card-foreground))',
        popover: 'hsl(var(--popover))',
        'popover-foreground': 'hsl(var(--popover-foreground))',

        // Chart
        'chart-1': 'hsl(var(--chart-1))',
        'chart-2': 'hsl(var(--chart-2))',
        'chart-3': 'hsl(var(--chart-3))',
        'chart-4': 'hsl(var(--chart-4))',
        'chart-5': 'hsl(var(--chart-5))',
      },
      fontFamily: {
        sans: ['"Noto Sans SC"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
        brand: ['"DM Serif Display"', '"Noto Serif SC"', 'serif'],
      },
      // Radius tier system — shape consistency lock (§4.4)
      // Documented rule (follow everywhere):
      //   rounded-xs  (2px)  → micro-badges (text-[9px] inline status tags)
      //   rounded-md  (6px)  → buttons, inputs, small chips
      //   rounded-lg  (8px)  → cards, list items, popover surfaces
      //   rounded-xl  (12px) → modals, drawers, dialogs
      //   rounded-2xl (16px) → chat surfaces (message bubbles, composer)
      //   rounded-full      → pill badges, avatars
      // Removed: rounded-sm, rounded-3xl (no usages).
      borderRadius: {
        xs: 'var(--radius-xs)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
        full: '9999px',
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: 'calc(1/0.75)' }],
        sm: ['0.875rem', { lineHeight: 'calc(1.25/0.875)' }],
        base: ['1rem', { lineHeight: '1.5' }],
        lg: ['1.125rem', { lineHeight: 'calc(1.75/1.125)' }],
        xl: ['1.25rem', { lineHeight: 'calc(1.75/1.25)' }],
        '2xl': ['1.5rem', { lineHeight: 'calc(2/1.5)' }],
        '3xl': ['1.875rem', { lineHeight: '1.2' }],
        '4xl': ['2.25rem', { lineHeight: 'calc(2.5/2.25)' }],
      },
      spacing: { 0.5: '0.125rem' },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        in: 'enter 150ms ease-out',
        out: 'exit 150ms ease-in forwards',
      },
    },
  },
  plugins: [],
};
