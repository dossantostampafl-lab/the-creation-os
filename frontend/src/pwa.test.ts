import { describe, expect, it, vi } from "vitest";
import { createUpdateController } from "./PwaStatus";
import { registerPwa } from "./pwa";

function registration(overrides: Record<string, unknown> = {}) {
  const listeners = new Map<string, () => void>();
  return {
    waiting: null,
    installing: null,
    addEventListener: vi.fn((type: string, listener: () => void) => listeners.set(type, listener)),
    listeners,
    ...overrides,
  };
}

describe("registerPwa", () => {
  it("does nothing when service workers are unavailable", async () => {
    await expect(registerPwa({ serviceWorker: null })).resolves.toBeNull();
  });

  it("registers the root worker without using the HTTP cache", async () => {
    const value = registration();
    const serviceWorker = {
      controller: null,
      register: vi.fn().mockResolvedValue(value),
      addEventListener: vi.fn(),
    };

    await expect(registerPwa({ serviceWorker })).resolves.toBe(value);
    expect(serviceWorker.register).toHaveBeenCalledWith("/sw.js", { scope: "/", updateViaCache: "none" });
  });

  it("announces a waiting update without activating it", async () => {
    const waiting = { postMessage: vi.fn() };
    const value = registration({ waiting });
    const onUpdateAvailable = vi.fn();
    const serviceWorker = { controller: {}, register: vi.fn().mockResolvedValue(value), addEventListener: vi.fn() };

    await registerPwa({ serviceWorker, onUpdateAvailable });

    expect(onUpdateAvailable).toHaveBeenCalledWith(value);
    expect(waiting.postMessage).not.toHaveBeenCalled();
  });

  it("announces an installed update when an active controller exists", async () => {
    const installingListeners = new Map<string, () => void>();
    const installing = {
      state: "installing",
      addEventListener: vi.fn((type: string, listener: () => void) => installingListeners.set(type, listener)),
    };
    const value = registration({ installing });
    const onUpdateAvailable = vi.fn();
    const serviceWorker = { controller: {}, register: vi.fn().mockResolvedValue(value), addEventListener: vi.fn() };

    await registerPwa({ serviceWorker, onUpdateAvailable });
    value.listeners.get("updatefound")?.();
    installing.state = "installed";
    installingListeners.get("statechange")?.();

    expect(onUpdateAvailable).toHaveBeenCalledWith(value);
  });

  it("reports controller changes for a safe reload", async () => {
    const value = registration();
    const controllerListeners = new Map<string, () => void>();
    const serviceWorker = {
      controller: {},
      register: vi.fn().mockResolvedValue(value),
      addEventListener: vi.fn((type: string, listener: () => void) => controllerListeners.set(type, listener)),
    };
    const onControllerChange = vi.fn();

    await registerPwa({ serviceWorker, onControllerChange });
    controllerListeners.get("controllerchange")?.();

    expect(onControllerChange).toHaveBeenCalledOnce();
  });

  it("contains registration failures and reports them", async () => {
    const failure = new Error("registration failed");
    const onError = vi.fn();
    const serviceWorker = { controller: null, register: vi.fn().mockRejectedValue(failure), addEventListener: vi.fn() };

    await expect(registerPwa({ serviceWorker, onError })).resolves.toBeNull();
    expect(onError).toHaveBeenCalledWith(failure);
  });
});

describe("createUpdateController", () => {
  it("reloads only after the requested worker takes control", () => {
    const reload = vi.fn();
    const postMessage = vi.fn();
    const controller = createUpdateController(reload);

    controller.controllerChanged();
    expect(reload).not.toHaveBeenCalled();
    expect(controller.request({ waiting: { postMessage }, addEventListener: vi.fn() })).toBe(true);
    expect(postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
    controller.controllerChanged();
    expect(reload).toHaveBeenCalledOnce();
  });

  it("refuses activation when no waiting worker is available", () => {
    const reload = vi.fn();
    const controller = createUpdateController(reload);
    expect(controller.request({ waiting: null, addEventListener: vi.fn() })).toBe(false);
    controller.controllerChanged();
    expect(reload).not.toHaveBeenCalled();
  });
});
