import { afterEach, expect, it, vi } from "vitest";
import { playHum, stopHum } from "./cues";

afterEach(() => {
  stopHum();
  vi.unstubAllGlobals();
});

it("düşünme sesi gerçek bir kısa kaydı çalar, ikinci kez üst üste başlatmaz ve kesilebilir", () => {
  const play = vi.fn(async () => undefined);
  const pause = vi.fn();
  const open = vi.fn();
  vi.stubGlobal("Audio", class {
    currentTime = 1;
    volume = 1;
    constructor(url: string) { open(url); }
    play = play;
    pause = pause;
  });

  playHum();
  playHum();
  expect(open).toHaveBeenCalledWith(expect.stringContaining("thinking-hm.mp3"));
  expect(play).toHaveBeenCalledOnce();
  stopHum();
  expect(pause).toHaveBeenCalledOnce();
  playHum();
  expect(play).toHaveBeenCalledTimes(2);
});
