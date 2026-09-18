import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  BAGLAM_KRITIK_ESIGI,
  BAGLAM_UYARI_ESIGI,
  ContextGauge,
  baglamEtiketi,
  baglamSeviyesi,
} from "./ContextGauge";

afterEach(cleanup);

const olcu = (yuzde: number) => ({ kullanilan: yuzde * 240, sinir: 24000, yuzde });

describe("baglamSeviyesi", () => {
  it("eşiklerin altında normal, eşiklerde uyarı ve kritik döner", () => {
    expect(baglamSeviyesi(0)).toBe("normal");
    expect(baglamSeviyesi(BAGLAM_UYARI_ESIGI - 1)).toBe("normal");
    expect(baglamSeviyesi(BAGLAM_UYARI_ESIGI)).toBe("uyari");
    expect(baglamSeviyesi(BAGLAM_KRITIK_ESIGI - 1)).toBe("uyari");
    expect(baglamSeviyesi(BAGLAM_KRITIK_ESIGI)).toBe("kritik");
    expect(baglamSeviyesi(100)).toBe("kritik");
  });
});

describe("baglamEtiketi", () => {
  it("normalde metin yazmaz, uyarıda kalanı, kritikte özetleme ipucunu yazar", () => {
    expect(baglamEtiketi(40)).toBeNull();
    expect(baglamEtiketi(75)).toBe("Bağlam %25 kaldı");
    expect(baglamEtiketi(95)).toBe("Yakında özetlenecek");
  });
});

describe("ContextGauge", () => {
  it("ölçü yokken hiçbir şey çizmez", () => {
    const { container } = render(<ContextGauge olcu={null} />);
    expect(container.innerHTML).toBe("");
  });

  it("doluluğu erişilebilir ölçer olarak bildirir, düşükken yalnız halka çizer", () => {
    render(<ContextGauge olcu={olcu(30)} />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("30");
    expect(meter.getAttribute("data-seviye")).toBe("normal");
    expect(meter.getAttribute("aria-label")).toMatch(/Bağlam doluluğu: %30/);
    expect(meter.textContent).toBe("");
  });

  it("%70 üstünde uyarı seviyesine geçer ve kalanı yazar", () => {
    render(<ContextGauge olcu={olcu(82)} />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("data-seviye")).toBe("uyari");
    expect(meter.textContent).toBe("Bağlam %18 kaldı");
  });

  it("%90 üstünde yakında özetleneceğini söyler", () => {
    render(<ContextGauge olcu={olcu(97)} />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("data-seviye")).toBe("kritik");
    expect(meter.textContent).toBe("Yakında özetlenecek");
  });
});
