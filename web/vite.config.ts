import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.SHOPASSIST_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // 默认只绑 IPv6 的 localhost（[::1]），用 127.0.0.1 打开会连不上。
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/health": { target: backend, changeOrigin: true },
    },
  },
});
