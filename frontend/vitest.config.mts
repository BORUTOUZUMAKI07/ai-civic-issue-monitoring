import { defineConfig } from "vitest/config"
import path from "path"

export default defineConfig({
  // JSX is handled by tsconfig's `react-jsx`; Vitest 4 no longer accepts an
  // `esbuild.jsx` override here.
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    exclude: ["e2e/**", "node_modules/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
})
