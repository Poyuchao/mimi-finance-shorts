import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev:把 /api 代理到 FastAPI(:8000),避免 CORS。
// prod:npm run build 出 dist/,可交給 FastAPI StaticFiles 同源服務。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
