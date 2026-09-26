import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { PWA_CONTROLLER_EVENT, PWA_UPDATE_EVENT, registerPwa } from "./pwa";
import "./styles.css";

if (import.meta.env.PROD) {
  void registerPwa({
    onUpdateAvailable: (registration) => window.dispatchEvent(new CustomEvent(PWA_UPDATE_EVENT, { detail: registration })),
    onControllerChange: () => window.dispatchEvent(new Event(PWA_CONTROLLER_EVENT)),
  });
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>,
);
