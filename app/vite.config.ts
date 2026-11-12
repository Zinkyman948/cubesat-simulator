import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

// Cesium loads workers, widgets and imagery at runtime from
// window.CESIUM_BASE_URL (set in main.tsx), so its prebuilt static assets are
// copied into the output under /cesium.
const cesiumSource = "node_modules/cesium/Build/Cesium";
const cesiumBaseUrl = "cesium";

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
  build: { target: "es2022", chunkSizeWarningLimit: 6000 },
});
