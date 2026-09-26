import { useEffect, useRef, useState } from "react";
import { PWA_CONTROLLER_EVENT, PWA_UPDATE_EVENT } from "./pwa";
import type { PwaRegistrationLike } from "./pwa";

export function createUpdateController(reload: () => void) {
  let requested = false;
  return {
    request(registration: PwaRegistrationLike): boolean {
      if (!registration.waiting?.postMessage) return false;
      requested = true;
      registration.waiting.postMessage({ type: "SKIP_WAITING" });
      return true;
    },
    controllerChanged() {
      if (requested) reload();
    },
  };
}

export function PwaStatus() {
  const [online, setOnline] = useState(() => typeof navigator === "undefined" || navigator.onLine);
  const [registration, setRegistration] = useState<PwaRegistrationLike | null>(null);
  const [reloadRequested, setReloadRequested] = useState(false);
  const updateController = useRef(createUpdateController(() => window.location.reload()));

  useEffect(() => {
    const markOnline = () => setOnline(true);
    const markOffline = () => setOnline(false);
    const updateAvailable = (event: Event) => setRegistration((event as CustomEvent<PwaRegistrationLike>).detail);
    const controllerChanged = () => updateController.current.controllerChanged();
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    window.addEventListener(PWA_UPDATE_EVENT, updateAvailable);
    window.addEventListener(PWA_CONTROLLER_EVENT, controllerChanged);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
      window.removeEventListener(PWA_UPDATE_EVENT, updateAvailable);
      window.removeEventListener(PWA_CONTROLLER_EVENT, controllerChanged);
    };
  }, []);

  function activateUpdate() {
    if (registration && updateController.current.request(registration)) setReloadRequested(true);
  }

  if (!online) {
    return <div className="pwa-banner pwa-offline" role="status" aria-live="polite">Connection unavailable. Live data is not current.</div>;
  }
  if (registration) {
    return (
      <div className="pwa-banner pwa-update" role="status" aria-live="polite">
        <span>A new version is ready.</span>
        <button type="button" onClick={activateUpdate} disabled={reloadRequested}>{reloadRequested ? "Reloading…" : "Reload now"}</button>
      </div>
    );
  }
  return null;
}
