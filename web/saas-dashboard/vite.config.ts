import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: false
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/@ant-design/pro-components")) return "pro-components";
          if (id.includes("node_modules/antd") || id.includes("node_modules/@ant-design/icons")) return "antd";
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id.replaceAll("\\", "/"))) return "react";
          if (id.includes("node_modules/i18next") || id.includes("node_modules/react-i18next")) return "i18n";
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000"
    }
  }
});
