import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { codecovVitePlugin } from "@codecov/vite-plugin";
import path from "path";
import pkg from "./package.json";

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
    codecovVitePlugin({
      enableBundleAnalysis: process.env.CODECOV_TOKEN !== undefined,
      bundleName: "weftmark-frontend",
      uploadToken: process.env.CODECOV_TOKEN,
    }),
  ],
  define: {
    // npm sets npm_package_version from package.json at build time
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? "0.0.0"),
    __FRONTEND_DEPS__: JSON.stringify(pkg.dependencies ?? {}),
    __FRONTEND_DEV_DEPS__: JSON.stringify(pkg.devDependencies ?? {}),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/auth": "http://localhost:8000",
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/system": "http://localhost:8000",
      "/dev": "http://localhost:8000",
    },
  },
});
