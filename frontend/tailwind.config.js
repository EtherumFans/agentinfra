/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Vermillion + Jade + Warm neutral design tokens
        background: 'hsl(40 14% 98%)',
        foreground: 'hsl(40 6% 9%)',
        muted: 'hsl(40 10% 95%)',
        'muted-foreground': 'hsl(40 4% 43%)',

        // Vermillion primary — Chinese medical seal red
        primary: 'hsl(9 68% 48%)',
        'primary-foreground': 'hsl(0 0% 100%)',

        // Jade secondary — accuracy, confirmed, success
        secondary: 'hsl(155 33% 38%)',
        'secondary-foreground': 'hsl(0 0% 100%)',

        // Warm gray accents
        accent: 'hsl(40 12% 94%)',
        'accent-foreground': 'hsl(40 6% 12%)',

        border: 'hsl(40 10% 89%)',
        input: 'hsl(40 10% 92%)',
        ring: 'hsl(9 68% 48%)',

        destructive: 'hsl(0 72% 48%)',
        'destructive-foreground': 'hsl(0 0% 100%)',

        // Sidebar
        sidebar: 'hsl(40 10% 96%)',
        'sidebar-foreground': 'hsl(40 4% 35%)',
        'sidebar-border': 'hsl(40 8% 85%)',
        'sidebar-primary': 'hsl(9 68% 48%)',
        'sidebar-primary-foreground': 'hsl(0 0% 100%)',
        'sidebar-accent': 'hsl(40 10% 93%)',
        'sidebar-accent-foreground': 'hsl(40 6% 12%)',
        'sidebar-ring': 'hsl(9 68% 48%)',

        // Card / popover
        card: 'hsl(0 0% 100%)',
        'card-foreground': 'hsl(40 6% 9%)',
        popover: 'hsl(0 0% 100%)',
        'popover-foreground': 'hsl(40 6% 9%)',
      },
      fontFamily: {
        sans: ['"Noto Sans SC"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
        brand: ['"DM Serif Display"', '"Noto Serif SC"', 'serif'],
      },
      borderRadius: {
        xs: '0.125rem',
        sm: 'calc(0.5rem - 4px)',
        md: 'calc(0.5rem - 2px)',
        lg: '0.5rem',
        xl: '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
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
      // Dark mode semantic color overrides via CSS custom properties
      // Applied when <html class="dark">
      backgroundColor: {
        dark: 'hsl(40 4% 10%)',
      },
    },
  },
  plugins: [],
};
