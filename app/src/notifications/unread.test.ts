import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearUnread, getUnread, markUnread, resetUnread, subscribeUnread } from "./unread";

describe("okunmamış kümesi ve Dock rozeti", () => {
  const rozet = vi.fn(async () => undefined);
  beforeEach(() => {
    rozet.mockClear();
    resetUnread(rozet);
  });

  it("işaretleme kümeyi büyütür, rozete sayı yazar ve aboneye haber verir", () => {
    const dinleyici = vi.fn();
    subscribeUnread(dinleyici);
    markUnread(["a", "b"]);
    expect([...getUnread()]).toEqual(["a", "b"]);
    expect(rozet).toHaveBeenLastCalledWith(2);
    expect(dinleyici).toHaveBeenCalledOnce();
  });

  it("zaten işaretli kimlik yeniden duyurulmaz", () => {
    markUnread(["a"]);
    const dinleyici = vi.fn();
    subscribeUnread(dinleyici);
    markUnread(["a"]);
    expect(dinleyici).not.toHaveBeenCalled();
    expect(rozet).toHaveBeenCalledTimes(1);
  });

  it("temizleme son okunmamışı düşürünce rozet sıfırlanır", () => {
    markUnread(["a"]);
    clearUnread("a");
    expect(getUnread().size).toBe(0);
    expect(rozet).toHaveBeenLastCalledWith(0);
    clearUnread("a");
    expect(rozet).toHaveBeenCalledTimes(2);
  });

  it("rozet hatası kümeyi bozmaz", async () => {
    resetUnread(vi.fn(async () => { throw new Error("rozet yok"); }));
    const uyari = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    markUnread(["a"]);
    await Promise.resolve();
    expect(getUnread().has("a")).toBe(true);
    uyari.mockRestore();
  });
});
