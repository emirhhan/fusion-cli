import { beforeAll, describe, expect, it, vi } from "vitest";
import { FakeContext, render } from "./offlineAudio";

/**
 * `playHum` düşünme sesinin GERÇEK çıktı dalgası: çizge çevrimdışı işlenir ve
 * süre, temel frekans, tını ve zarf sayıyla sınanır (kulakla değil).
 */
const HIZ = 16000;

let ornekler: Float32Array;

/** Otokorelasyonla temel frekans (Hz); aday aralığı dışarıdan verilir. */
function temelFrekans(x: Float32Array, baslangic: number, bitis: number, enAz: number, enCok: number): number {
  const parca = x.subarray(baslangic, bitis);
  let enIyiGecikme = 0;
  let enIyiDeger = -Infinity;
  for (let gecikme = Math.floor(HIZ / enCok); gecikme <= Math.ceil(HIZ / enAz); gecikme++) {
    let toplam = 0;
    for (let i = 0; i + gecikme < parca.length; i++) toplam += parca[i] * parca[i + gecikme];
    if (toplam > enIyiDeger) {
      enIyiDeger = toplam;
      enIyiGecikme = gecikme;
    }
  }
  return HIZ / enIyiGecikme;
}

function rms(x: Float32Array, a: number, b: number): number {
  let t = 0;
  for (let i = a; i < b; i++) t += x[i] * x[i];
  return Math.sqrt(t / (b - a));
}

/** Naif DFT ile [aHz, bHz) bandındaki enerji (Hann pencereli). */
function bandEnerjisi(x: Float32Array, a: number, b: number, aHz: number, bHz: number): number {
  const n = b - a;
  let toplam = 0;
  for (let k = Math.ceil((aHz * n) / HIZ); k < Math.floor((bHz * n) / HIZ); k++) {
    let re = 0;
    let im = 0;
    for (let i = 0; i < n; i++) {
      const pencere = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1));
      const aci = (2 * Math.PI * k * i) / n;
      re += x[a + i] * pencere * Math.cos(aci);
      im -= x[a + i] * pencere * Math.sin(aci);
    }
    toplam += re * re + im * im;
  }
  return toplam;
}

describe("hmm düşünme sesi", () => {
  beforeAll(async () => {
    const ctx = new FakeContext();
    class Sahte {
      constructor() {
        return ctx;
      }
    }
    vi.stubGlobal("AudioContext", Sahte);
    Object.defineProperty(window, "AudioContext", { value: Sahte, configurable: true });
    const { playHum } = await import("./cues");
    playHum();
    ornekler = render(ctx, 1.3, HIZ);
  });

  it("yaklaşık 1 sn sürer ve sonra tamamen susar", () => {
    const pencere = Math.round(0.05 * HIZ);
    const dolu = (a: number) => rms(ornekler, a, a + pencere);
    const zirve = Math.max(...Array.from({ length: 20 }, (_, i) => dolu(Math.round((0.1 + i * 0.045) * HIZ))));
    // Duyulur süre: seviye zirvenin %1'inin (−40 dB) üstünde kaldığı son an.
    // (−20 dB'de ≈0,78 sn ölçülür: son 0,4 sn üstel sönümdür.)
    let son = 0;
    for (let a = 0; a + pencere < ornekler.length; a += pencere) {
      if (rms(ornekler, a, a + pencere) > zirve * 0.01) son = (a + pencere) / HIZ;
    }
    expect(son).toBeGreaterThan(0.85);
    expect(son).toBeLessThan(1.15);
    // Durma noktasından (1.10 sn) sonrası sessiz.
    expect(rms(ornekler, Math.round(1.15 * HIZ), ornekler.length)).toBeLessThan(zirve * 0.001);
  });

  it("tık yapmadan yumuşak başlar ve belirgin bir seviyeye çıkar", () => {
    const ilk = rms(ornekler, 0, Math.round(0.005 * HIZ));
    const orta = rms(ornekler, Math.round(0.3 * HIZ), Math.round(0.6 * HIZ));
    expect(orta).toBeGreaterThan(0.01);
    expect(ilk).toBeLessThan(orta * 0.1);
  });

  it("temel frekansı 100-300 Hz aralığında, insan homurtusu perdesindedir", () => {
    const f0 = temelFrekans(ornekler, Math.round(0.25 * HIZ), Math.round(0.75 * HIZ), 80, 400);
    expect(f0).toBeGreaterThan(100);
    expect(f0).toBeLessThan(300);
  });

  it("kapalı-ağız tınısı: enerji alçak bantta toplanır, tiz bant bastırılır", () => {
    const a = Math.round(0.3 * HIZ);
    const b = Math.round(0.8 * HIZ);
    const alcak = bandEnerjisi(ornekler, a, b, 80, 1000);
    const tiz = bandEnerjisi(ornekler, a, b, 1500, 6000);
    // 950 Hz alçak geçiren + testere dalgası: tiz bant en az 30 dB (1000 kat) altta.
    expect(alcak / tiz).toBeGreaterThan(1000);
    // Burun formantı (270 Hz çevresi) çevre bandın üstünde yükselir.
    const burun = bandEnerjisi(ornekler, a, b, 230, 310) / 80;
    const ust = bandEnerjisi(ornekler, a, b, 600, 680) / 80;
    expect(burun).toBeGreaterThan(ust);
  });
});
