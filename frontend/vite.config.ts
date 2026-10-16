import { svelte } from '@sveltejs/vite-plugin-svelte';
// `vitest/config` etend la configuration Vite avec la cle `test`.
import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    strictPort: true,
    // `shared/safety-limits.json` se trouve a la racine du depot, hors de `frontend/`.
    // On autorise explicitement la lecture de ce seul dossier parent.
    fs: {
      allow: ['..'],
    },
  },
  build: {
    // Blockly est volumineux ; on evite l'avertissement de taille de chunk.
    chunkSizeWarningLimit: 2000,
  },
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    root: fileURLToPath(new URL('.', import.meta.url)),
  },
});