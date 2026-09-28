import '@testing-library/jest-dom/vitest'

// jsdom does not implement matchMedia, which ThemeProvider and the responsive
// hooks rely on.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
})

// Recharts' ResponsiveContainer needs these to render in tests.
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as never
