import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  server: {
    // During development the surfclip backend runs on 127.0.0.1:8765 (config/default.toml).
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  build: { outDir: 'dist' },
})
