import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(
  readFileSync(join(__dirname, "package.json"), "utf8")
) as { version: string };
const buildId = new Date().toISOString();

export default defineConfig({
  define: {
    __NDE_APP_SEMVER__: JSON.stringify(pkg.version),
    __NDE_APP_BUILD_ID__: JSON.stringify(buildId),
  },
  plugins: [react()],
  publicDir: "public",
  server: {
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:3999",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
