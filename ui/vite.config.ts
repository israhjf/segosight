import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// In development the UI runs on 5173 and proxies /api to the FastAPI process,
// which owns the DuckDB write lock. In production `vite build` emits to
// ui/dist and FastAPI serves it from the same origin, so there is one process
// and one port for an evaluator to start.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: true },
});
