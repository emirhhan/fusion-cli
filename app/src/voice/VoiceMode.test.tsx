import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceMode } from "./VoiceMode";

vi.mock("./level", () => ({ startLevelMeter: vi.fn(async () => null) }));
const startDragging = vi.fn(async () => undefined);
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ startDragging }) }));

afterEach(() => {
  cleanup();
  startDragging.mockClear();
});

describe("VoiceMode", () => {
  it("pencere denetimlerini gerçek eylemlerine bağlar", () => {
    const onClose = vi.fn();
    const onMinimize = vi.fn();
    const onWideChange = vi.fn();
    render(
      <VoiceMode
        listening={false}
        onClose={onClose}
        onMinimize={onMinimize}
        onWideChange={onWideChange}
        state="idle"
        wide
      />,
    );

    const header = screen.getByRole("banner");
    const controls = screen.getByLabelText("Pencere denetimleri");
    expect(header.hasAttribute("data-tauri-drag-region")).toBe(false);
    expect(controls.hasAttribute("data-tauri-drag-region")).toBe(false);
    expect(Array.from(header.children).map((child) => child.className)).toEqual([
      "voice-panel__window-controls",
      "voice-panel__drag voice-panel__drag--left",
      "voice-panel__drag voice-panel__drag--center",
      "voice-panel__drag voice-panel__drag--right",
    ]);
    expect(header.querySelectorAll("[data-tauri-drag-region]")).toHaveLength(4);
    expect(controls.querySelector("[data-tauri-drag-region]")).toBeNull();
    expect(screen.queryByTestId("right-side-window-actions")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Konuşma kipini kapat" }));
    fireEvent.click(screen.getByRole("button", { name: "Pencereyi simge durumuna küçült" }));
    fireEvent.click(screen.getByRole("button", { name: "Paneli küçült" }));

    expect(onClose).toHaveBeenCalledOnce();
    expect(onMinimize).toHaveBeenCalledOnce();
    expect(onWideChange).toHaveBeenCalledWith(false);
  });

  it("yalnız sol orta ve sağ boş başlık alanları yerel pencere sürüklemeyi başlatır", () => {
    render(
      <VoiceMode listening={false} onClose={vi.fn()} onMinimize={vi.fn()} onWideChange={vi.fn()} state="idle" wide />,
    );

    const panel = screen.getByRole("region", { name: "Fusion Talk" });
    const dragRegions = panel.querySelectorAll<HTMLElement>(".voice-panel__drag");
    for (const region of dragRegions) fireEvent.pointerDown(region, { button: 0 });
    fireEvent.pointerDown(screen.getByRole("button", { name: "Konuşma kipini kapat" }), { button: 0 });

    expect(startDragging).toHaveBeenCalledTimes(3);
  });

  it("trafik ışıklarını macOS sırasıyla ve hover sırasında çizilecek sabit gliflerle sunar", () => {
    render(
      <VoiceMode listening={false} onClose={vi.fn()} onMinimize={vi.fn()} onWideChange={vi.fn()} state="idle" wide />,
    );

    const controls = screen.getByLabelText("Pencere denetimleri");
    expect(Array.from(controls.querySelectorAll("button")).map((button) => button.getAttribute("aria-label"))).toEqual([
      "Konuşma kipini kapat",
      "Pencereyi simge durumuna küçült",
      "Paneli küçült",
    ]);
    expect(controls.textContent).toBe("");
    expect(controls.querySelectorAll("svg[aria-hidden='true']")).toHaveLength(3);
    expect(controls.querySelectorAll(".voice-panel__traffic-glyph")).toHaveLength(3);
    expect(Array.from(controls.querySelectorAll(".voice-panel__traffic-glyph")).map((glyph) => glyph.getAttribute("data-glyph"))).toEqual([
      "close",
      "minimize",
      "zoom",
    ]);
  });

  it("mini kipte mikrofon göstergesi görünür, tuş sunulmaz", () => {
    render(
      <VoiceMode
        listening={false}
        onClose={vi.fn()}
        onMinimize={vi.fn()}
        onWideChange={vi.fn()}
        state="idle"
        wide={false}
      />,
    );

    // Dinleme sürekli açıktır; konuşmak için basılacak bir tuş yoktur.
    expect(screen.queryByRole("button", { name: "Konuşmaya başla" })).toBeNull();
    expect(screen.getByRole("status", { name: "Dinleme hazırlanıyor" })).toBeTruthy();
  });

  it("dar kipte döküm ve ayarlar gizlenir", () => {
    render(
      <VoiceMode
        listening
        onClose={vi.fn()}
        onMinimize={vi.fn()}
        onPrefsChange={vi.fn()}
        onTopChange={vi.fn()}
        onWideChange={vi.fn()}
        state="listening"
        transcript="merhaba"
        wide={false}
      />,
    );
    expect(screen.queryByText("merhaba")).toBeNull();
    expect(screen.queryByLabelText("Hız")).toBeNull();
    expect(screen.getByRole("region", { name: "Fusion Talk" }).getAttribute("data-mode")).toBe("mini");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("geniş kipte döküm ve ayarlar görünür", () => {
    render(
      <VoiceMode
        listening
        onClose={vi.fn()}
        onMinimize={vi.fn()}
        onPrefsChange={vi.fn()}
        onTopChange={vi.fn()}
        onWideChange={vi.fn()}
        state="listening"
        transcript="merhaba"
        wide
      />,
    );
    expect(screen.getByText("merhaba")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ses ayarları" })).toBeTruthy();
    expect(screen.getByRole("status", { name: "Dinliyor" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Fusion Talk" }).getAttribute("data-mode")).toBe("normal");
  });

  it("boyut düğmesi iki ölçü arasında gidip gelir", () => {
    const onWideChange = vi.fn();
    render(
      <VoiceMode listening={false} onClose={vi.fn()} onMinimize={vi.fn()} onWideChange={onWideChange} state="idle" wide />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Paneli küçült" }));
    expect(onWideChange).toHaveBeenCalledWith(false);
  });

  it("dalga formu yalnız dinlerken etkindir", () => {
    const { container, rerender } = render(
      <VoiceMode listening={false} onClose={vi.fn()} onMinimize={vi.fn()} state="idle" />,
    );
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("false");

    rerender(<VoiceMode listening onClose={vi.fn()} onMinimize={vi.fn()} state="listening" />);
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("true");

    rerender(<VoiceMode listening onClose={vi.fn()} onMinimize={vi.fn()} state="transcribing" />);
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("true");
  });

  it("interrupted sunumunda gosterge recognition sahipligini yansitir", () => {
    // Gösterge, dinlemenin gerçekten açık olup olmadığını söyler; `interrupted`
    // görünümünde bile sahiplik `listening` prop'undan gelir, durumdan değil.
    const { rerender } = render(
      <VoiceMode listening={false} onClose={vi.fn()} onMinimize={vi.fn()} state="interrupted" />,
    );
    expect(
      screen.getByRole("status", { name: "Dinleme hazırlanıyor" }).getAttribute("data-dinliyor"),
    ).toBe("false");

    rerender(
      <VoiceMode listening onClose={vi.fn()} onMinimize={vi.fn()} state="interrupted" />,
    );
    expect(
      screen.getByRole("status", { name: "Dinliyor" }).getAttribute("data-dinliyor"),
    ).toBe("true");
  });
});

describe("VoiceMode — onay", () => {
  const ASK = {
    acik: true,
    arac: "write_file",
    metin: "app.py dosyası yazılsın mı?",
    secenekler: [
      { deger: "evet", etiket: "Onayla" },
      { deger: "hayir", etiket: "Reddet" },
    ],
  };

  it("açık onayı panelde gösterir ve seçimi geri verir", () => {
    const onAnswer = vi.fn();
    render(
      <VoiceMode ask={ASK} listening={false} onAnswer={onAnswer} onClose={vi.fn()} onMinimize={vi.fn()} state="thinking" />,
    );
    expect(screen.getByText("app.py dosyası yazılsın mı?")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Reddet" }));
    expect(onAnswer).toHaveBeenCalledWith("hayir");
  });

  it("mini kipte de onayı erişilebilir kabul ve ret düğmeleriyle gösterir", () => {
    render(
      <VoiceMode ask={ASK} listening={false} onAnswer={vi.fn()} onClose={vi.fn()} onMinimize={vi.fn()} onWideChange={vi.fn()} state="approval" wide={false} />,
    );
    expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Onayla" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reddet" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Paneli büyüt" })).toBeTruthy();
  });

  it("onay yokken hiçbir şey çizmez", () => {
    render(<VoiceMode ask={null} listening={false} onAnswer={vi.fn()} onClose={vi.fn()} onMinimize={vi.fn()} state="idle" />);
    expect(screen.queryByRole("group", { name: "Onay" })).toBeNull();
  });
});
