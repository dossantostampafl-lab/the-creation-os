export const PWA_UPDATE_EVENT = "pwa:update-available";
export const PWA_CONTROLLER_EVENT = "pwa:controller-change";

export interface PwaWorkerLike {
  state?: string;
  postMessage?: (message: unknown) => void;
  addEventListener?: (type: string, listener: () => void) => void;
}

export interface PwaRegistrationLike {
  waiting?: PwaWorkerLike | null;
  installing?: PwaWorkerLike | null;
  addEventListener: (type: string, listener: () => void) => void;
}

interface PwaContainerLike {
  controller: unknown;
  register: (url: string, options: { scope: string; updateViaCache: "none" }) => Promise<PwaRegistrationLike>;
  addEventListener: (type: string, listener: () => void) => void;
}

export interface PwaRegistrationOptions {
  serviceWorker?: PwaContainerLike | null;
  onUpdateAvailable?: (registration: PwaRegistrationLike) => void;
  onControllerChange?: () => void;
  onError?: (error: unknown) => void;
}

export async function registerPwa(options: PwaRegistrationOptions = {}): Promise<PwaRegistrationLike | null> {
  const serviceWorker = options.serviceWorker === undefined
    ? (typeof navigator !== "undefined" && "serviceWorker" in navigator
      ? navigator.serviceWorker as unknown as PwaContainerLike
      : null)
    : options.serviceWorker;

  if (!serviceWorker) return null;

  try {
    const registration = await serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
    const announceUpdate = () => options.onUpdateAvailable?.(registration);

    if (registration.waiting) announceUpdate();
    registration.addEventListener("updatefound", () => {
      const installing = registration.installing;
      installing?.addEventListener?.("statechange", () => {
        if (installing.state === "installed" && serviceWorker.controller) announceUpdate();
      });
    });
    serviceWorker.addEventListener("controllerchange", () => options.onControllerChange?.());
    return registration;
  } catch (error) {
    options.onError?.(error);
    return null;
  }
}
