import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// O backend fica em :8000. O proxy evita CORS no dia a dia e deixa a interface
// falar com "/api" tanto em dev quanto servida junto do FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: true },
});
