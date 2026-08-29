import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { RuntimeBackendStatus, RuntimeTransport } from "./runtime/types";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn(async (command: string) => {
    if (command === "oturum_olustur") {
      return {
        oturum_id: "varsayilan",
        kok: "/proje",
        pid: 41,
        durum: "calisiyor",
        kapanis_nedeni: null,
      };
    }
    return undefined;
  }),
  listen: vi.fn().mockResolvedValue(() => undefined),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: tauri.listen }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("App runtime kapısı", () => {
  it("runtime hazır olmadan çekirdeği başlatmaz", async () => {
    const prepared = deferred<RuntimeBackendStatus>();
    const transport: RuntimeTransport = {
      status: vi.fn().mockResolvedValue({
        state: "eksik",
        message: "Kurulum gerekli",
        can_repair: false,
      }),
      prepare: vi.fn(() => prepared.promise),
      repair: vi.fn(() => prepared.promise),
      listenProgress: vi.fn().mockResolvedValue(() => undefined),
    };

    render(<App runtimeTransport={transport} />);
    await screen.findByText("Kurulum gerekli");
    expect(tauri.invoke).not.toHaveBeenCalledWith("oturum_olustur", expect.anything());

    prepared.resolve({
      state: "hazir",
      version: "0.3.0a1",
      message: "Hazır",
      can_repair: false,
    });
    await waitFor(() =>
      expect(tauri.invoke).toHaveBeenCalledWith("oturum_olustur", {
        oturumId: "varsayilan",
        kok: null,
      }),
    );
  });
});
