import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const currentDir = dirname(fileURLToPath(import.meta.url));
const backend = process.env.HOSPICE_BACKEND || 'http://localhost:8003';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: resolve(currentDir, '../../apps/clinician'),
    emptyOutDir: true,
    sourcemap: false,
    assetsDir: 'assets',
  },
  server: {
    port: 5556,
    host: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true, ws: true },
      '/hospice-media': { target: backend, changeOrigin: true },
    },
  },
});

