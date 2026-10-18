import { defineConfig } from "vite";

export default defineConfig({
  build: { outDir: "dist", assetsDir: "static/assets", emptyOutDir: true },
  server: {
    proxy: {
      // Preserve the browser Host so the backend same-origin POST guard also works in development.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
      "/healthz": "http://127.0.0.1:8000",
      "/docs": "http://127.0.0.1:8000",
      "/openapi.json": "http://127.0.0.1:8000",
    },
  },
});
