/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs separately in development (python -m uvicorn --app-dir backend
// kromi_api.main:app, port 8000); the dev server forwards /api to it, so the
// browser sees one origin exactly as in production.
const API_TARGET = process.env.KROMI_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": API_TARGET },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    // Mantine and AG Grid together exceed Vite's default warning size; one
    // bundle is fine for an internal app on the local network.
    chunkSizeWarningLimit: 4000,
  },
  test: {
    // happy-dom: jsdom 30 cannot send a FormData file through fetch (uploads).
    environment: "happy-dom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
