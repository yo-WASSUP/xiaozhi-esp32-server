import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BACKEND = process.env.HOSPICE_BACKEND || 'http://localhost:8003';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: resolve(__dirname, '../../apps/patient'),
    emptyOutDir: true,
    sourcemap: false,
    assetsDir: 'assets',
  },
  // 开发时：Vite 跑 5556，API / SSE / WS / 静态媒体 / xiaozhi-client 依赖的 /test-assets 都代理到后端
  server: {
    port: 5556,
    host: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true, ws: true },
      '/shared': { target: BACKEND, changeOrigin: true },
      '/hospice-media': { target: BACKEND, changeOrigin: true },
      '/test-assets': { target: BACKEND, changeOrigin: true },
      '/xiaozhi': { target: BACKEND, changeOrigin: true, ws: true },
    },
  },
});
