/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const apiTarget = process.env.VSH_API_TARGET ?? "http://localhost:8000";
// The agent ticket factory (ADR-0029) verifies candidates in checkouts under .git/infra-factory/,
// which Vite's default fs.deny ("**/.git/**") would refuse entirely. Only ops/factory/run_suite.py
// sets this; the normal dev server keeps Vite's defaults.
const factoryColdCheckout = process.env.VSH_FACTORY_COLD === "1";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler)\//.test(id)) return "react";
          if (/node_modules\/(@tanstack|i18next|react-i18next)\//.test(id)) return "data";
          if (/node_modules\/lucide-react\//.test(id)) return "icons";
          if (/src\/i18n\/locales\//.test(id)) return "locales";
          return undefined;
        },
      },
    },
  },
  server: {
    ...(factoryColdCheckout ? { fs: { deny: [".env", ".env.*", "*.{crt,pem}"] } } : {}),
    host: "0.0.0.0",
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  preview: {
    port: 3000,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
