import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type {
  RuntimeBackendStatus,
  RuntimeProgress,
  RuntimeTransport,
  RuntimeView,
} from "./types";

const defaultTransport: RuntimeTransport = {
  status: () => invoke<RuntimeBackendStatus>("runtime_durum"),
  prepare: () => invoke<RuntimeBackendStatus>("runtime_hazirla"),
  repair: () => invoke<RuntimeBackendStatus>("runtime_onar"),
  listenProgress: async (listener) =>
    listen<RuntimeProgress>("runtime-ilerleme", (event) => listener(event.payload)),
};

const prepareRequests = new WeakMap<RuntimeTransport, Promise<RuntimeBackendStatus>>();

function prepareOnce(transport: RuntimeTransport): Promise<RuntimeBackendStatus> {
  const current = prepareRequests.get(transport);
  if (current) return current;
  const request = transport.prepare().finally(() => prepareRequests.delete(transport));
  prepareRequests.set(transport, request);
  return request;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function viewFromStatus(status: RuntimeBackendStatus): RuntimeView {
  if (status.state === "hazir") {
    return {
      state: "hazir",
      progress: 100,
      message: status.message,
      version: status.version,
    };
  }
  return {
    state: status.can_repair || status.state === "onarilabilir" ? "onarilabilir" : "hata",
    progress: 0,
    message: status.message,
    version: status.version,
  };
}

const INITIAL_VIEW: RuntimeView = {
  state: "denetleniyor",
  progress: 0,
  message: "Fusion çalışma zamanı denetleniyor…",
};

export function useRuntime(transport: RuntimeTransport = defaultTransport) {
  const [view, setView] = useState<RuntimeView>(INITIAL_VIEW);

  useEffect(() => {
    let active = true;
    let unlisten: (() => void) | undefined;

    const updateProgress = (progress: RuntimeProgress) => {
      if (!active) return;
      const percentage = Math.round((progress.completed / Math.max(progress.total, 1)) * 100);
      setView({
        state: "kuruluyor",
        progress: Math.min(100, Math.max(0, percentage)),
        message: progress.message,
      });
    };

    void (async () => {
      try {
        const stopListening = await transport.listenProgress(updateProgress);
        if (!active) {
          stopListening();
          return;
        }
        unlisten = stopListening;

        const status = await transport.status();
        if (!active) return;
        if (status.state === "hazir") {
          setView(viewFromStatus(status));
          return;
        }
        if (status.state !== "eksik") {
          setView(viewFromStatus(status));
          return;
        }

        setView({ state: "kuruluyor", progress: 0, message: status.message });
        const prepared = await prepareOnce(transport);
        if (active) setView(viewFromStatus(prepared));
      } catch (error) {
        if (active) {
          setView({ state: "onarilabilir", progress: 0, message: errorMessage(error) });
        }
      }
    })();

    return () => {
      active = false;
      unlisten?.();
    };
  }, [transport]);

  const repair = useCallback(async () => {
    setView({
      state: "kuruluyor",
      progress: 0,
      message: "Fusion çalışma zamanı onarılıyor…",
    });
    try {
      setView(viewFromStatus(await transport.repair()));
    } catch (error) {
      setView({ state: "onarilabilir", progress: 0, message: errorMessage(error) });
    }
  }, [transport]);

  return { ...view, repair };
}
