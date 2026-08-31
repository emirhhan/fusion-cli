import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceMode } from "./VoiceMode";

vi.mock("./level", () => ({ startLevelMeter: vi.fn(async () => null) }));

afterEach(cleanup);

describe("VoiceMode", () => {
  it("pencere denetimlerini gerçek eylemlerine bağlar", () => {
    const onClose = vi.fn();
    const onMinimize = vi.fn();
    const onWideChange = vi.fn();
    render(
      <VoiceMode
        onClose={onClose}
        onMinimize={onMinimize}
        onToggleListen={vi.fn()}
        onWideChange={onWideChange}
        state="idle"
        wide
      />,
    );

    const header = screen.getByRole("banner");
    const controls = screen.getByLabelText("Pencere denetimleri");
    expect(header.getAttribute("data-tauri-drag-region")).toBe("true");
    expect(controls.hasAttribute("data-tauri-drag-region")).toBe(false);
    expect(screen.queryByTestId("right-side-window-actions")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Konuşma kipini kapat" }));
    fireEvent.click(screen.getByRole("button", { name: "Pencereyi simge durumuna küçült" }));
    fireEvent.click(screen.getByRole("button", { name: "Paneli küçült" }));

    expect(onClose).toHaveBeenCalledOnce();
    expect(onMinimize).toHaveBeenCalledOnce();
    expect(onWideChange).toHaveBeenCalledWith(false);
  });

  it("mini kipte aynı mikrofon eylemi görünür ve kullanılabilir", () => {
    const onToggleListen = vi.fn();
    render(
      <VoiceMode
        onClose={vi.fn()}
        onMinimize={vi.fn()}
        onToggleListen={onToggleListen}
        onWideChange={vi.fn()}
        state="idle"
        wide={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Konuşmaya başla" }));
    expect(onToggleListen).toHaveBeenCalledOnce();
  });

  it("dar kipte döküm ve ayarlar gizlenir", () => {
    render(
      <VoiceMode
        onClose={vi.fn()}
        onMinimize={vi.fn()}
        onPrefsChange={vi.fn()}
        onToggleListen={vi.fn()}
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
        onClose={vi.fn()}
        onMinimize={vi.fn()}
        onPrefsChange={vi.fn()}
        onToggleListen={vi.fn()}
        onTopChange={vi.fn()}
        onWideChange={vi.fn()}
        state="listening"
        transcript="merhaba"
        wide
      />,
    );
    expect(screen.getByText("merhaba")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ses ayarları" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dinlemeyi durdur" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Fusion Talk" }).getAttribute("data-mode")).toBe("normal");
  });

  it("boyut düğmesi iki ölçü arasında gidip gelir", () => {
    const onWideChange = vi.fn();
    render(
      <VoiceMode onClose={vi.fn()} onMinimize={vi.fn()} onToggleListen={vi.fn()} onWideChange={onWideChange} state="idle" wide />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Paneli küçült" }));
    expect(onWideChange).toHaveBeenCalledWith(false);
  });

  it("dalga formu yalnız dinlerken etkindir", () => {
    const { container, rerender } = render(
      <VoiceMode onClose={vi.fn()} onMinimize={vi.fn()} onToggleListen={vi.fn()} state="idle" />,
    );
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("false");

    rerender(<VoiceMode onClose={vi.fn()} onMinimize={vi.fn()} onToggleListen={vi.fn()} state="listening" />);
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("true");

    rerender(<VoiceMode onClose={vi.fn()} onMinimize={vi.fn()} onToggleListen={vi.fn()} state="transcribing" />);
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("true");
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
      <VoiceMode ask={ASK} onAnswer={onAnswer} onClose={vi.fn()} onMinimize={vi.fn()} onToggleListen={vi.fn()} state="thinking" />,
    );
    expect(screen.getByText("app.py dosyası yazılsın mı?")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Reddet" }));
    expect(onAnswer).toHaveBeenCalledWith("hayir");
  });

  it("mini kipte de onayı erişilebilir kabul ve ret düğmeleriyle gösterir", () => {
    render(
      <VoiceMode ask={ASK} onAnswer={vi.fn()} onClose={vi.fn()} onMinimize={vi.fn()} onToggleListen={vi.fn()} onWideChange={vi.fn()} state="approval" wide={false} />,
    );
    expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Onayla" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reddet" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Paneli büyüt" })).toBeTruthy();
  });

  it("onay yokken hiçbir şey çizmez", () => {
    render(<VoiceMode ask={null} onAnswer={vi.fn()} onClose={vi.fn()} onMinimize={vi.fn()} onToggleListen={vi.fn()} state="idle" />);
    expect(screen.queryByRole("group", { name: "Onay" })).toBeNull();
  });
});
