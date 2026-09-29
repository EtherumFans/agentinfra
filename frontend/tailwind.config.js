/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      // Native-style workbench tokens — light surfaces and blue emphasis.
      // (light values in :root, dark values in .dark). Switching <html class="dark">
      // cascades the new values through every class below.
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        muted: 'hsl(var(--muted))',
        'muted-foreground': 'hsl(var(--muted-foreground))',

        // Native blue primary actions
        primary: 'hsl(var(--primary))',
        'primary-foreground': 'hsl(var(--primary-foreground))',

        // Quiet secondary surfaces
        secondary: 'hsl(var(--secondary))',
        'secondary-foreground': 'hsl(var(--secondary-foreground))',

        // Blue-gray surfaces
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

        // Low-saturation status palettes preserve existing semantic utility names.
        green: { 50: '#F1F8F4', 100: '#E3F1E8', 200: '#C7E2D1', 300: '#9BC6AB', 400: '#70A887', 500: '#4F8D6B', 600: '#248A3D', 700: '#248A3D', 800: '#254F3B', 900: '#203F32' },
        emerald: { 50: '#F0F8F5', 100: '#E2F1EB', 200: '#C4E0D4', 300: '#98C5B2', 400: '#6EA58D', 500: '#4D8A71', 600: '#248A3D', 700: '#248A3D', 800: '#254D40', 900: '#203E35' },
        blue: { 50: '#F0F5FA', 100: '#E8F2FF', 200: '#CCDBEC', 300: '#A3BCD6', 400: '#799DBF', 500: '#597FA5', 600: '#0071E3', 700: '#0066CC', 800: '#2D4761', 900: '#273C50' },
        amber: { 50: '#FCF8EE', 100: '#F7EED7', 200: '#ECDCB3', 300: '#DBC48A', 400: '#C5A969', 500: '#AB8D4F', 600: '#A05A00', 700: '#A05A00', 800: '#604927', 900: '#503D23' },
        yellow: { 50: '#FCF8EE', 100: '#F7EED7', 200: '#ECDCB3', 300: '#DBC48A', 400: '#C5A969', 500: '#AB8D4F', 600: '#A05A00', 700: '#A05A00', 800: '#604927', 900: '#503D23' },
        red: { 50: '#FCF3F1', 100: '#F5E5E0', 200: '#E9CBC3', 300: '#D6A69A', 400: '#BE8274', 500: '#AE6658', 600: '#D70015', 700: '#D70015', 800: '#6E392F', 900: '#5A3029' },
      },
      boxShadow: {
        sm: '0 1px 3px rgb(0 0 0 / 0.04)',
        DEFAULT: '0 2px 8px rgb(0 0 0 / 0.05)',
        md: '0 4px 14px rgb(0 0 0 / 0.06)',
        lg: '0 6px 20px rgb(0 0 0 / 0.07)',
        xl: '0 8px 24px rgb(0 0 0 / 0.08)',
        '2xl': '0 10px 28px rgb(0 0 0 / 0.09)',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"PingFang SC"', '"Microsoft YaHei"', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
        brand: ['-apple-system', 'BlinkMacSystemFont', '"PingFang SC"', '"Microsoft YaHei"', '"Segoe UI"', 'sans-serif'],
      },
      // Radius tier system — shape consistency lock (§4.4)
      // Documented rule (follow everywhere):
      //   rounded-xs  (2px)  → micro-badges (text-[9px] inline status tags)
      //   rounded-md  (9px)  → buttons, inputs, small chips
      //   rounded-lg  (16px) → cards, list items, popover surfaces
      //   rounded-xl  (18px) → modals, drawers, dialogs
      //   rounded-2xl (18px) → chat surfaces (message bubbles, composer)
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
