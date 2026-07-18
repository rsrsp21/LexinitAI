import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import { defineConfig } from "vite";

const backendTarget = "http://127.0.0.1:5000";
const backendProxy = {
  target: backendTarget,
  changeOrigin: true,
  secure: false,
};

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": backendProxy,
      "/auth": backendProxy,
      "/login": backendProxy,
      "/send-code": backendProxy,
      "/verify-code": backendProxy,
      "/forgot_password": backendProxy,
      "/submit-topic": backendProxy,
      "/upload": backendProxy,
      "/upload-image": backendProxy,
      "/save-score": backendProxy,
      "/save-watchtime": backendProxy,
      "/summarize": backendProxy,
      "/improve-score": backendProxy,
    },
  },
});
