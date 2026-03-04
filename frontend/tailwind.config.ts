import type { Config } from 'tailwindcss'

// Tailwind CSS v4 uses CSS-first configuration.
// Theme customizations are defined in src/style.css via @theme directives.
// This file exists for tooling compatibility (IDE plugins, editor integrations).
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
      },
    },
  },
} satisfies Config
