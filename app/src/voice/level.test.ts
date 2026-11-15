import { describe, expect, it, vi } from "vitest";
import { startLevelMeter } from "./level";

describe("startLevelMeter", () => {
  it("AudioContext kurulamazsa mikrofon akışı durdurulur (U2-33)", async () => {
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    vi.stubGlobal("AudioContext", class { constructor() { throw new Error("ses aygıtı yok"); } });
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {} });
    try {
      await expect(startLevelMeter(async () => stream)).resolves.toBeNull();
      expect(stopTrack).toHaveBeenCalledOnce();
    } finally { vi.unstubAllGlobals(); }
  });
});
