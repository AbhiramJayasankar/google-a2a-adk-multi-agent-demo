import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Forward all /api/* calls to the FastAPI BFF that wraps HostAgent.
      // The `bypass` function is important: without it, Vite's default
      // behaviour on a 5xx proxy error is to fall through to the SPA
      // fallback and serve `index.html`. The browser then calls
      // res.json() on `<!doctype html>...` and throws a confusing
      // "Unexpected token '<'" error in the topbar. We instead let the
      // BFF's real error response (or a 502 from the proxy) reach the
      // browser so the front-end can handle it as a normal fetch
      // failure.
      "/api": {
        target: "http://127.0.0.1:7000",
        changeOrigin: true,
        bypass: (req) => {
          // Never let /api/* fall through to the SPA index.html.
          // Returning undefined lets http-proxy forward the request.
          if (req.url?.startsWith("/api/")) return undefined;
          return null;
        },
        configure: (proxy) => {
          proxy.on("error", (err, req) => {
            // Surface real BFF connection failures instead of letting
            // Vite serve a 200 with the SPA HTML. The browser will see
            // a fetch network error, which the store already handles.
            console.warn(`[vite proxy] /api ${req.url} -> ${err.message}`);
          });
        },
      },
    },
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
