import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  test: {
    // Use jsdom for a browser-like DOM environment
    environment: 'jsdom',
    // Make vitest globals (describe, it, expect, vi) available without imports
    globals: true,
    // Run setup file before each test suite
    setupFiles: ['./src/__tests__/setup.ts'],
    // Include all test files matching these patterns
    include: ['src/__tests__/**/*.test.ts'],
    // Coverage configuration
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts', 'src/**/*.vue'],
      exclude: ['src/__tests__/**', 'src/main.ts'],
      reporter: ['text', 'html'],
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
