import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist/client' },
  server: {
    strictPort: true,
    port: 4413,
    host: '127.0.0.1',
    proxy: { '/api': process.env.KITS_API_TARGET ?? 'http://127.0.0.1:4410' },
  },
});
