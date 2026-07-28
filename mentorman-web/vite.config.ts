/// <reference types="vitest" />
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// SPA dev server on :5173 calls FastAPI on :8000 (CORS handles cross-origin).
// In production the build is served same-origin by FastAPI.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // fileURLToPath (not .pathname) so this decodes correctly when the
      // project path has spaces, e.g. "ai mentor" on Windows.
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
  test: {
    globals: true,
    environment: 'node',
  },
} as any);
