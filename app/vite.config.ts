import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

// Cesium loads workers, widgets and imagery at runtime from
// window.CESIUM_BASE_URL (set in main.tsx), so its prebuilt static assets are
// copied into the output under /cesium.
const cesiumSource = "node_modules/cesium/Build/Cesium";
const cesiumBaseUrl = "cesium";

// The desktop app's Content Security Policy. `vite preview` serves the build
// with the same policy, so violations show up when testing in a browser.
const tauriConfig = JSON.parse(readFileSync(new URL("./src-tauri/tauri.conf.json", import.meta.url), "utf-8"));
const csp: string = tauriConfig.app.security.csp;

export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      targets: ["Workers", "ThirdParty", "Assets", "Widgets"].map((dir) => ({
        src: `${cesiumSource}/${dir}`,
        dest: cesiumBaseUrl,
        // Drop the node_modules/cesium/Build/Cesium prefix: /cesium/Workers/...
        rename: { stripBase: 4 },
      })),
    }),
  ],
  // Tauri expects a fixed dev port and prints its own output.
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  preview: { port: 1420, strictPort: true, headers: { "Content-Security-Policy": csp } },
  build: { target: "es2022", chunkSizeWarningLimit: 6000 },
});
