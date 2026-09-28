import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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
    expect(baglamEtiketi(75)).toBe("Özetlemeye %25 kaldı");
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
    expect(meter.getAttribute("aria-label")).toMatch(/Geçmişin özetleme eşiğine doluluğu: %30/);
    expect(meter.textContent).toBe("");
  });

  it("%70 üstünde uyarı seviyesine geçer ve kalanı yazar", () => {
    render(<ContextGauge olcu={olcu(82)} />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("data-seviye")).toBe("uyari");
    expect(meter.textContent).toBe("Özetlemeye %18 kaldı");
  });

  it("%90 üstünde yakında özetleneceğini söyler", () => {
    render(<ContextGauge olcu={olcu(97)} />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("data-seviye")).toBe("kritik");
    expect(meter.textContent).toBe("Yakında özetlenecek");
  });

  it("doğrulanmış model penceresini ayrı, bilinmeyen pencereyi belirsiz gösterir", () => {
    const view = render(<ContextGauge olcu={{ ...olcu(30), model: "openrouter/model", model_siniri_token: 65536 }} />);
    expect(screen.getByRole("meter").getAttribute("title")).toMatch(/65\.536 token/);
    view.rerender(<ContextGauge olcu={{ ...olcu(30), model: "nvidia_nim/model", model_siniri_token: null }} />);
    expect(screen.getByRole("meter").getAttribute("title")).toMatch(/penceresi doğrulanamadı/);
  });

  it("son model çağrısının gerçek token kullanımını özetleme yüzdesinden ayrı belirtir", () => {
    render(<ContextGauge olcu={{ ...olcu(30), son_girdi_token: 1234, son_girdi_model: "openrouter/model", son_girdi_pencere_token: 10000, son_girdi_pencere_yuzde: 12 }} />);
    const title = screen.getByRole("meter").getAttribute("title") ?? "";
    expect(title).toMatch(/1\.234 girdi tokenı/);
    expect(title).toMatch(/penceresinin %12'si/);
    expect(title).toMatch(/Bu yüzde model penceresinin doluluğu değildir/);
  });

  /* Bkz. bug: halkaya tıklayınca/üzerine gelince hiçbir şey olmuyordu; tek
     ipucu sönük bir `title` idi. Artık tıklama, kullanılan/toplam bağlam,
     yüzde ve bir "sıkıştır" düğmesi taşıyan bir kart açar. */
  describe("açılır kart", () => {
    it("varsayılan olarak kapalıdır, halkaya tıklayınca açılır", () => {
      render(<ContextGauge olcu={olcu(30)} />);
      expect(screen.queryByRole("dialog")).toBeNull();

      fireEvent.click(screen.getByRole("meter"));

      const kart = screen.getByRole("dialog", { name: "Bağlam kullanımı" });
      expect(kart.textContent).toMatch(/%30/);
      expect(kart.textContent).toMatch(/7\.200 \/ 24\.000 karakter/);
      expect(kart.textContent).toMatch(/konuşma geçmişi/i);
    });

    it("Escape ve dışarı tıklama kartı kapatır", () => {
      render(
        <div>
          <button>dışarı</button>
          <ContextGauge olcu={olcu(30)} />
        </div>,
      );
      fireEvent.click(screen.getByRole("meter"));
      expect(screen.getByRole("dialog")).toBeTruthy();

      fireEvent.keyDown(document, { key: "Escape" });
      expect(screen.queryByRole("dialog")).toBeNull();

      fireEvent.click(screen.getByRole("meter"));
      fireEvent.mouseDown(screen.getByRole("button", { name: "dışarı" }));
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("onCompact verilmişse 'Bağlamı sıkıştır' /compact gönderir ve kartı kapatır", () => {
      const onCompact = vi.fn();
      render(<ContextGauge olcu={olcu(92)} onCompact={onCompact} />);
      fireEvent.click(screen.getByRole("meter"));

      fireEvent.click(screen.getByRole("button", { name: /Bağlamı sıkıştır/ }));

      expect(onCompact).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("onCompact verilmezse sıkıştır düğmesi çizilmez", () => {
      render(<ContextGauge olcu={olcu(30)} />);
      fireEvent.click(screen.getByRole("meter"));
      expect(screen.queryByRole("button", { name: /Bağlamı sıkıştır/ })).toBeNull();
    });
  });
});
