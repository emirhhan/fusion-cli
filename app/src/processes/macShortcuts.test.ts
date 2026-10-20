import { describe, expect, it } from "vitest";
import { macTerminalShortcut } from "./macShortcuts";

const tus = (key: string, mods: Partial<{ metaKey: boolean; altKey: boolean; ctrlKey: boolean; shiftKey: boolean }> = {}) => ({
  key, metaKey: false, altKey: false, ctrlKey: false, shiftKey: false, ...mods,
});

describe("macTerminalShortcut", () => {
  it("⌘ kısayollarını satır düzenleme dizilerine çevirir", () => {
    expect(macTerminalShortcut(tus("Backspace", { metaKey: true }))).toBe("\x15");
    expect(macTerminalShortcut(tus("ArrowLeft", { metaKey: true }))).toBe("\x01");
    expect(macTerminalShortcut(tus("ArrowRight", { metaKey: true }))).toBe("\x05");
    expect(macTerminalShortcut(tus("k", { metaKey: true }))).toBe("temizle");
  });

  it("⌥ kısayollarını kelime düzenlemeye çevirir", () => {
    expect(macTerminalShortcut(tus("Backspace", { altKey: true }))).toBe("\x1b\x7f");
    expect(macTerminalShortcut(tus("ArrowLeft", { altKey: true }))).toBe("\x1bb");
    expect(macTerminalShortcut(tus("ArrowRight", { altKey: true }))).toBe("\x1bf");
  });

  it("⌘C/⌘V ve sıradan tuşlara dokunmaz", () => {
    expect(macTerminalShortcut(tus("c", { metaKey: true }))).toBeNull();
    expect(macTerminalShortcut(tus("v", { metaKey: true }))).toBeNull();
    expect(macTerminalShortcut(tus("a"))).toBeNull();
    expect(macTerminalShortcut(tus("Backspace"))).toBeNull();
    expect(macTerminalShortcut(tus("ArrowLeft", { metaKey: true, shiftKey: true }))).toBeNull();
  });
});
