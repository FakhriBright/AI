import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { existsSync } from 'fs'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  // In local dev, read ../.env (root project). In Docker, .env won't exist
  // at '../' so fall back to default (current dir / process.env).
  envDir: existsSync(resolve(import.meta.dirname, '../.env')) ? '../' : '.',
  define: {
    // Forward OS-level VITE_* env vars (injected by docker-compose env_file)
    // so they are available via import.meta.env even without a .env file on disk.
    ...(process.env.VITE_API_URL
      ? { 'import.meta.env.VITE_API_URL': JSON.stringify(process.env.VITE_API_URL) }
      : {}),
    ...(process.env.VITE_API_BASE_URL
      ? { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify(process.env.VITE_API_BASE_URL) }
      : {}),
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      usePolling: true,
    },
  },
})
