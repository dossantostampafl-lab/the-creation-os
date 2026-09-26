import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { PWA_CONTROLLER_EVENT, PWA_UPDATE_EVENT, registerPwa } from "./pwa";
import "./styles.css";
import "./release-fixes.css";

class RootErrorBoundary extends React.Component<
  React.PropsWithChildren,
  { failed: boolean; message: string }
> {
  state = { failed: false, message: "" };

  static getDerivedStateFromError(error: unknown) {
    return {
      failed: true,
      message: error instanceof Error ? error.message : "UNKNOWN_FRONTEND_ERROR",
    };
  }

  componentDidCatch(error: unknown) {
    console.error("THE_CREATION_UI_FATAL", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="boot-fallback" role="alert">
        <section>
          <span>THE CREATION OS</span>
          <h1>Creator Interface recovery mode</h1>
          <p>The visual runtime failed, but the interface is still reachable.</p>
          <code>{this.state.message}</code>
          <button type="button" onClick={() => window.location.reload()}>Reload interface</button>
        </section>
      </main>
    );
  }
}

if (import.meta.env.PROD) {
  void registerPwa({
    onUpdateAvailable: (registration) => window.dispatchEvent(new CustomEvent(PWA_UPDATE_EVENT, { detail: registration })),
    onControllerChange: () => window.dispatchEvent(new Event(PWA_CONTROLLER_EVENT)),
  });
}

const root = document.getElementById("root");
if (!root) throw new Error("ROOT_ELEMENT_MISSING");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>,
);
