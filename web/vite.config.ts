import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `base: "./"` so the built bundle works wherever FastAPI mounts it.
// The dev server proxies /api to FastAPI so the same fetch code runs in both
// (SDD §22): a front end that talks to a different origin in development is a
// front end whose CORS and cookie behaviour is only tested in production.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
