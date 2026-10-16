import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FusionAvatar, type AvatarState } from "./FusionAvatar";

const DURUMLAR: Array<{ durum: AvatarState; etiket: string }> = [
  { durum: "idle", etiket: "Fusion bekliyor" },
  { durum: "listening", etiket: "Fusion dinliyor" },
  { durum: "thinking", etiket: "Fusion düşünüyor" },
  { durum: "talking", etiket: "Fusion konuşuyor" },
  { durum: "happy", etiket: "Fusion mutlu" },
  { durum: "approval", etiket: "Fusion onay bekliyor" },
];

function hareketiAzalt(eslesiyor: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: eslesiyor }));
}

function kare(): HTMLImageElement {
  return screen.getByRole("img") as HTMLImageElement;
}

beforeEach(() => {
  vi.useFakeTimers();
  hareketiAzalt(false);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("FusionAvatar", () => {
  it.each(DURUMLAR)("$durum durumunu erişilebilir etiketiyle sunar", ({ durum, etiket }) => {
    render(<FusionAvatar state={durum} />);

    expect(screen.getByRole("img", { name: etiket }).parentElement?.getAttribute("data-state")).toBe(durum);
  });

  it("Fusion ana karakterini kullanır ve JavaScript zamanlayıcısı başlatmaz", () => {
    const view = render(<FusionAvatar state="listening" />);
    expect(kare().src).toContain("fusion-abstract.png");
    view.rerender(<FusionAvatar state="talking" />);
    act(() => vi.advanceTimersByTime(720));
    expect(kare().src).toContain("fusion-abstract.png");
    expect(vi.getTimerCount()).toBe(0);
  });
});
