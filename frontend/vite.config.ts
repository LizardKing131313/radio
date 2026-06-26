import tailwindcss from "@tailwindcss/vite";
import {resolve} from "node:path";
import {defineConfig} from "vite";

export default defineConfig({
  root: __dirname,
  plugins: [tailwindcss()],
  resolve: {
    alias: {
      "@radio/api": resolve(__dirname, "packages/api/src"),
      "@radio/ui": resolve(__dirname, "packages/ui/src"),
      "@radio/player": resolve(__dirname, "apps/player/src")
    }
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      input: {
        player: resolve(__dirname, "apps/player/index.html"),
        admin: resolve(__dirname, "apps/admin/index.html")
      }
    }
  },
  test: {
    environment: "node",
    include: ["apps/**/*.test.ts", "packages/**/*.test.ts"]
  }
});
