import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env["VITE_PROXY_TARGET"] ?? "http://localhost:8000";

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: 5173,
      // Same-origin in dev: the browser talks to :5173 and Vite forwards /api to FastAPI,
      // so the httpOnly refresh cookie "just works" and no CORS setup is needed.
      proxy: { "/api": { target: backend, changeOrigin: true } },
    },
  };
});
