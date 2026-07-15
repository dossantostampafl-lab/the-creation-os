import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/universe.css";
import "./styles/overlays.css";
import "./styles/animations.css";

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
