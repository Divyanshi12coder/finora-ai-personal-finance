/**
 * Finora design system.
 *
 * Colours are defined as CSS custom properties in index.css and referenced here
 * as `rgb(var(--token) / <alpha-value>)`. That gives one source of truth for
 * both themes: dark mode redefines the variables, and every utility class
 * follows automatically without a single `dark:` variant on a colour.
 *
 * Palette intent:
 *   white  -> dominant surface
 *   navy   -> brand, navigation, income, primary actions
 *   red    -> expenses, warnings, negative trends, emphasis only
 */
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Semantic surfaces
        canvas: 'rgb(var(--canvas) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        elevated: 'rgb(var(--elevated) / <alpha-value>)',
        subtle: 'rgb(var(--subtle) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',

        // Text
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        faint: 'rgb(var(--faint) / <alpha-value>)',

        // Brand navy
        navy: {
          DEFAULT: 'rgb(var(--navy) / <alpha-value>)',
          deep: 'rgb(var(--navy-deep) / <alpha-value>)',
          soft: 'rgb(var(--navy-soft) / <alpha-value>)',
          tint: 'rgb(var(--navy-tint) / <alpha-value>)',
          ink: 'rgb(var(--navy-ink) / <alpha-value>)',
        },

        // Accent red
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          strong: 'rgb(var(--accent-strong) / <alpha-value>)',
          soft: 'rgb(var(--accent-soft) / <alpha-value>)',
          tint: 'rgb(var(--accent-tint) / <alpha-value>)',
        },

        // Status
        positive: 'rgb(var(--positive) / <alpha-value>)',
        'positive-soft': 'rgb(var(--positive-soft) / <alpha-value>)',
        warning: 'rgb(var(--warning) / <alpha-value>)',
        'warning-soft': 'rgb(var(--warning-soft) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.04em' }],
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        card: '0 1px 2px rgb(11 31 58 / 0.04), 0 4px 16px -4px rgb(11 31 58 / 0.08)',
        'card-hover': '0 2px 4px rgb(11 31 58 / 0.05), 0 12px 32px -8px rgb(11 31 58 / 0.16)',
        float: '0 20px 48px -12px rgb(11 31 58 / 0.24)',
        ring: '0 0 0 3px rgb(var(--navy) / 0.12)',
        'ring-accent': '0 0 0 3px rgb(var(--accent) / 0.16)',
      },
      backgroundImage: {
        'navy-gradient': 'linear-gradient(135deg, rgb(var(--navy)) 0%, rgb(var(--navy-deep)) 100%)',
        'hero-gradient':
          'linear-gradient(135deg, rgb(var(--navy)) 0%, rgb(var(--navy-deep)) 55%, rgb(var(--accent) / 0.85) 190%)',
        'subtle-grid':
          'linear-gradient(rgb(var(--line) / 0.6) 1px, transparent 1px), linear-gradient(90deg, rgb(var(--line) / 0.6) 1px, transparent 1px)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.9)', opacity: '0.7' },
          '70%': { transform: 'scale(1.3)', opacity: '0' },
          '100%': { transform: 'scale(1.3)', opacity: '0' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in': 'fade-in 0.3s ease-out both',
        shimmer: 'shimmer 1.8s linear infinite',
        float: 'float 6s ease-in-out infinite',
        'pulse-ring': 'pulse-ring 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}
