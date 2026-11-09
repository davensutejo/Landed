import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// Two pages: the landing page and the agent workspace (/agent).
// In dev, /api is proxied to the FastAPI server (uvicorn api.main:app --port 8000).
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        agent: resolve(__dirname, 'agent.html')
      }
    }
  },
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  }
});
