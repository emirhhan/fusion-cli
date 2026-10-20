import { afterEach, describe, expect, it, vi } from "vitest";
import {
  applyVoiceWindowGeometry,
  getSpeechRecognitionStatus,
  isVoiceWindow,
  minimizeVoiceWindow,
  startSpeechRecognition,
  stopSpeechRecognition,
} from "./windowBridge";

const tauri = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));

afterEach(() => {
  vi.clearAllMocks();
});

describe("konuşma penceresi", () => {
  it("yalnız kendi arama parametresiyle tanınır", () => {
    expect(isVoiceWindow("?pencere=ses")).toBe(true);
    expect(isVoiceWindow("?pencere=ana")).toBe(false);
    expect(isVoiceWindow("")).toBe(false);
    // Benzer ama farklı değer ana pencereyi konuşma penceresi sanmamalı.
    expect(isVoiceWindow("?pencere=sesli")).toBe(false);
  });

  it("tanımayı backend'de tek sahipli komutla başlatır", async () => {
    tauri.invoke.mockResolvedValueOnce(42);

    await expect(startSpeechRecognition()).resolves.toBe(42);

    expect(tauri.invoke).toHaveBeenCalledWith("tanima_baslat");
  });

  it("tanıma child sürecini açık durdurma komutuyla sonlandırır", async () => {
    tauri.invoke.mockResolvedValueOnce(undefined);

    await stopSpeechRecognition();

    expect(tauri.invoke).toHaveBeenCalledWith("tanima_durdur");
  });

  it("backend'in güncel tanıma durumunu döndürür", async () => {
    tauri.invoke.mockResolvedValueOnce(true);

    await expect(getSpeechRecognitionStatus()).resolves.toBe(true);
    expect(tauri.invoke).toHaveBeenCalledWith("tanima_durum");
  });

  it("kaydedilmiş Talk geometrisini tek backend komutuyla geri uygular", async () => {
    tauri.invoke.mockResolvedValueOnce(undefined);
    const geometry = {
      x: 120,
      y: 80,
      normalWidth: 480,
      normalHeight: 640,
      wide: true,
      onTop: false,
    };

    await applyVoiceWindowGeometry(geometry);

    expect(tauri.invoke).toHaveBeenCalledWith("ses_penceresi_geometri_uygula", { geometry });
  });

  it("Talk penceresini tanımayı kapatmadan yerel olarak simge durumuna küçültür", async () => {
    tauri.invoke.mockResolvedValueOnce(undefined);

    await minimizeVoiceWindow();

    expect(tauri.invoke).toHaveBeenCalledWith("ses_penceresi_simge_durumu");
    expect(tauri.invoke).not.toHaveBeenCalledWith("tanima_durdur");
  });
});
