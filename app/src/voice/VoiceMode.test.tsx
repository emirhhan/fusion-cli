import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceMode } from "./VoiceMode";

vi.mock("./level", () => ({ startLevelMeter: vi.fn(async () => null) }));

afterEach(cleanup);

describe("VoiceMode", () => {
  it("dar kipte döküm ve ayarlar gizlenir", () => {
    render(
      <VoiceMode
        onClose={vi.fn()}
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
  });

  it("geniş kipte döküm ve ayarlar görünür", () => {
    render(
      <VoiceMode
        onClose={vi.fn()}
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
    expect(screen.getByLabelText("Hız")).toBeTruthy();
  });

  it("boyut düğmesi iki ölçü arasında gidip gelir", () => {
    const onWideChange = vi.fn();
    render(
      <VoiceMode onClose={vi.fn()} onToggleListen={vi.fn()} onWideChange={onWideChange} state="idle" wide />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Paneli küçült" }));
    expect(onWideChange).toHaveBeenCalledWith(false);
  });

  it("dalga formu yalnız dinlerken etkindir", () => {
    const { container, rerender } = render(
      <VoiceMode onClose={vi.fn()} onToggleListen={vi.fn()} state="idle" />,
    );
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("false");

    rerender(<VoiceMode onClose={vi.fn()} onToggleListen={vi.fn()} state="listening" />);
    expect(container.querySelector(".voice-wave")?.getAttribute("data-active")).toBe("true");
  });
});
