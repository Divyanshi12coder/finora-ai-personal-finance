/// <reference types="vitest" />
import { defineConfig, mergeConfig } from 'vitest/config'
import path from 'node:path'

import viteConfig from './vite.config'

/**
 * Test config is kept separate from vite.config.ts so the production build does
 * not typecheck Vitest-only options.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
    },
  }),
)
