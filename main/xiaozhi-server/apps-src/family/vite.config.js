import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// 后端 dev 端口（从 .config_hospice.yaml 默认取 8003）
const BACKEND = process.env.HOSPICE_BACKEND || 'http://localhost:8003';

export default defineConfig({
  plugins: [react()],
  // 相对路径，方便部署在任何 /family/ 挂载点下
  base: './',
  build: {
    // 输出到原 apps/family/，无需改动 server 的静态路由
    outDir: resolve(__dirname, '../../apps/family'),
    emptyOutDir: true,
    sourcemap: false,
    // 生成 index.html + assets/*-[hash].js|css
    assetsDir: 'assets',
  },
  // 开发时代理后端：前端跑 5173，API/SSE/WS/静态媒体走 8003
  server: {
    port: 5555,
    host: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true, ws: true },
      '/shared': { target: BACKEND, changeOrigin: true },
      '/hospice-media': { target: BACKEND, changeOrigin: true },
    },
  },
});
