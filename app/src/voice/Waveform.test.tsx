import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Waveform } from "./Waveform";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

function fakeMeter(seviye: number) {
  const stop = vi.fn();
  return {
    baslat: vi.fn(async () => ({ read: () => seviye, stop })),
    stop,
  };
}

function olcek(el: Element): number {
  return Number(/scaleY\(([\d.]+)\)/.exec((el as HTMLElement).style.transform)?.[1] ?? "0");
}

describe("Waveform", () => {
  it("gerçek seviyeyi çubuklara yansıtır", async () => {
    const { baslat } = fakeMeter(1);
    const { container } = render(<Waveform active baslat={baslat} />);
    await act(async () => undefined);
    await act(async () => { vi.advanceTimersByTime(200); });

    const sonBar = container.querySelectorAll(".voice-wave__bar")[8];
    expect(olcek(sonBar)).toBeCloseTo(1, 2);
  });

  it("mikrofon açılamazsa hiçbir çubuk oynamaz", async () => {
    const baslat = vi.fn(async () => null);
    const { container } = render(<Waveform active baslat={baslat} />);
    await act(async () => undefined);
    await act(async () => { vi.advanceTimersByTime(500); });

    const barlar = [...container.querySelectorAll(".voice-wave__bar")];
    expect(barlar.every((bar) => olcek(bar) < 0.13)).toBe(true);
  });

  it("dinleme bitince ölçeri kapatır", async () => {
    const { baslat, stop } = fakeMeter(0.5);
    const { rerender } = render(<Waveform active baslat={baslat} />);
    await act(async () => undefined);
    rerender(<Waveform active={false} baslat={baslat} />);
    expect(stop).toHaveBeenCalled();
  });
});
