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
  update?: () => Promise<void> | void;
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


export interface PwaUpdatePollingOptions {
  document?: Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">;
  intervalMs?: number;
  setInterval?: typeof window.setInterval;
  clearInterval?: typeof window.clearInterval;
}

export function startPwaUpdatePolling(
  registration: Pick<PwaRegistrationLike, "update">,
  options: PwaUpdatePollingOptions = {},
): () => void {
  if (!registration.update) return () => undefined;
  const documentLike = options.document ?? document;
  const intervalMs = options.intervalMs ?? 60_000;
  const schedule = options.setInterval ?? window.setInterval.bind(window);
  const cancel = options.clearInterval ?? window.clearInterval.bind(window);
  const check = () => {
    if (documentLike.visibilityState !== "visible") return;
    void Promise.resolve(registration.update?.()).catch(() => undefined);
  };
  const timer = schedule(check, intervalMs);
  documentLike.addEventListener("visibilitychange", check);
  return () => {
    cancel(timer);
    documentLike.removeEventListener("visibilitychange", check);
  };
}


export interface ClientFreshnessPollingOptions {
  currentAsset?: () => string | null;
  fetchShell?: () => Promise<string>;
  reload?: () => void;
  document?: Pick<Document, "visibilityState" | "querySelector" | "addEventListener" | "removeEventListener">;
  intervalMs?: number;
  setInterval?: typeof window.setInterval;
  clearInterval?: typeof window.clearInterval;
}

function moduleAssetFromHtml(html: string): string | null {
  for (const match of html.matchAll(/<script\b[^>]*>/gi)) {
    const tag = match[0];
    if (!/\btype\s*=\s*["']module["']/i.test(tag)) continue;
    const src = tag.match(/\bsrc\s*=\s*["']([^"']+)["']/i)?.[1];
    if (src) return src;
  }
  return null;
}

export function startClientFreshnessPolling(
  options: ClientFreshnessPollingOptions = {},
): () => void {
  const documentLike = options.document ?? document;
  const currentAsset = options.currentAsset ?? (() =>
    documentLike.querySelector<HTMLScriptElement>('script[type="module"][src]')?.getAttribute("src") ?? null);
  const fetchShell = options.fetchShell ?? (async () => {
    const response = await fetch("/", { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`PWA_SHELL_HTTP_${response.status}`);
    return response.text();
  });
  const reload = options.reload ?? (() => window.location.reload());
  const intervalMs = options.intervalMs ?? 60_000;
  const schedule = options.setInterval ?? window.setInterval.bind(window);
  const cancel = options.clearInterval ?? window.clearInterval.bind(window);
  let reloadRequested = false;

  const check = async () => {
    if (reloadRequested || documentLike.visibilityState !== "visible") return;
    const before = currentAsset();
    if (!before) return;
    try {
      const after = moduleAssetFromHtml(await fetchShell());
      if (after && after !== before) {
        reloadRequested = true;
        reload();
      }
    } catch {
      // Network loss is handled elsewhere; freshness checks must never break the UI.
    }
  };

  const onVisible = () => { void check(); };
  const timer = schedule(() => { void check(); }, intervalMs);
  documentLike.addEventListener("visibilitychange", onVisible);
  return () => {
    cancel(timer);
    documentLike.removeEventListener("visibilitychange", onVisible);
  };
}
