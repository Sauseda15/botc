import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': apiTarget
    }
  },
  preview: {
    host: '0.0.0.0',
    allowedHosts: ['botc.up.railway.app'],
    proxy: {
      '/api': apiTarget
    }
  }
});