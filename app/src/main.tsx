import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// Where Cesium fetches its workers and bundled imagery (copied there by vite.config.ts).
// Read lazily on first use, so setting it here, before the first render, is early enough.
(window as unknown as { CESIUM_BASE_URL: string }).CESIUM_BASE_URL = "/cesium";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
