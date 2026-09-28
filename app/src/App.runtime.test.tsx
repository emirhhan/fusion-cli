import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
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
vi.mock("./processes/XtermSession", () => ({ XtermSession: () => null }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
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
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
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
    expect(tauri.listen).toHaveBeenCalledWith("fusion://ses-barge-in", expect.any(Function));
  });

  /* Ölçüldü (28 Eylül, Windows): kapatma Rust'ta durdurulup onay arayüzde
     soruluyor; hazırlanıyor/hata/hesap/rehber ekranları onayı hiç çizmediği için
     uygulama kapanmıyordu. Onay, çekirdek henüz bağlanmadan da görünmeli. */
  it("çekirdek bağlanmadan da kapatma onayı gösterilir", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    const dinleyiciler = new Map<string, () => void>();
    tauri.listen.mockImplementation(async (ad: string, geri: () => void) => {
      dinleyiciler.set(ad, geri);
      return () => undefined;
    });
    const transport: RuntimeTransport = {
      status: vi.fn().mockResolvedValue({ state: "hazir", version: "0.3.0a1", message: "Hazır", can_repair: false }),
      prepare: vi.fn(),
      repair: vi.fn(),
      listenProgress: vi.fn().mockResolvedValue(() => undefined),
    };

    render(<App runtimeTransport={transport} />);
    await waitFor(() => expect(dinleyiciler.has("uygulama://kapatma-istegi")).toBe(true));
    act(() => dinleyiciler.get("uygulama://kapatma-istegi")?.());

    expect(await screen.findByRole("dialog", { name: "Fusion'ı kapat?" })).toBeTruthy();
  });

  /* Ölçüldü (28 Eylül, Windows): "Çekirdek bağlantısı kapatıldı" dışında hiçbir
     iz yoktu. Bağlantı kurulamayınca çekirdeğin son hata çıktısı gösterilmeli. */
  it("çekirdeğe bağlanılamazsa son hata çıktısı gösterilir", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    tauri.invoke.mockImplementation(async (command: string) => {
      if (command === "oturum_olustur") throw new Error("Çekirdek bağlantısı kapatıldı.");
      if (command === "cekirdek_gunlugu") return "Traceback: ornek_modul hatası";
      return undefined;
    });
    // Çekirdek olaylarına abone olunamaması = bağlantı kurulamadı.
    tauri.listen.mockRejectedValue(new Error("Çekirdek bağlantısı kapatıldı."));
    const transport: RuntimeTransport = {
      status: vi.fn().mockResolvedValue({ state: "hazir", version: "0.3.0a1", message: "Hazır", can_repair: false }),
      prepare: vi.fn(),
      repair: vi.fn(),
      listenProgress: vi.fn().mockResolvedValue(() => undefined),
    };

    render(<App runtimeTransport={transport} />);

    expect(await screen.findByText("Çekirdeğin son hata çıktısı")).toBeTruthy();
    expect(screen.getByText("Traceback: ornek_modul hatası")).toBeTruthy();
  });
});
