import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react")) return "react";
          if (id.includes("node_modules/antd") || id.includes("node_modules/@ant-design/icons")) return "antd";
          if (id.includes("node_modules/@ant-design/pro-components")) return "pro-components";
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
