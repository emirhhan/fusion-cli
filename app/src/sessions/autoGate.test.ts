import { afterEach, describe, expect, it, vi } from "vitest";
import { autoPolicyDisabled, onAutoGateChange, readAutoGate, setAutoGateSession, setAutoPolicyDisabled } from "./autoGate";
import { modlariOku } from "./useSessionModes";

afterEach(() => {
  setAutoGateSession(null);
  setAutoPolicyDisabled(false);
});

describe("autoGate — disableAutoMode oturum başına (#85)", () => {
  it("her oturum kendi auto_kapali değerini taşır; etkin oturumunki geçerlidir", () => {
    setAutoGateSession("A");
    readAutoGate({ auto_kapali: true }, "A");
    expect(autoPolicyDisabled()).toBe(true);
    setAutoGateSession("B");
    readAutoGate({ auto_kapali: false }, "B");
    expect(autoPolicyDisabled()).toBe(false);
    setAutoGateSession("A");
    expect(autoPolicyDisabled()).toBe(true);
  });

  it("başka oturumdan geç gelen yanıt etkin oturumun kapısını değiştirmez", () => {
    setAutoGateSession("B");
    readAutoGate({ auto_kapali: false }, "B");
    modlariOku({ mod: "security", auto_kapali: true }, "A");
    expect(autoPolicyDisabled()).toBe(false);
    setAutoGateSession("A");
    expect(autoPolicyDisabled()).toBe(true);
  });

  it("henüz durumu okunmamış oturumda auto açık sayılır (çekirdek yine reddeder)", () => {
    setAutoGateSession("A");
    readAutoGate({ auto_kapali: true }, "A");
    setAutoGateSession("C");
    expect(autoPolicyDisabled()).toBe(false);
  });

  it("etkin oturum değişip kapı değişince dinleyici uyarılır", () => {
    const listener = vi.fn();
    const off = onAutoGateChange(listener);
    setAutoGateSession("A");
    readAutoGate({ auto_kapali: true }, "A");
    setAutoGateSession("B");
    off();
    expect(listener).toHaveBeenCalledTimes(2);
  });
});
