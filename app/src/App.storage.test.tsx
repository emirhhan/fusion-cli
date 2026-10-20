import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./runtime/useRuntime", () => ({ useRuntime: () => ({ state: "hazir", version: "test" }) }));
vi.mock("./SessionApplication", () => ({
  SessionUygulama: ({ onboarding, onOnboardingComplete }: { onboarding: boolean; onOnboardingComplete: () => void }) => (
    <div><span>{onboarding ? "Kurulum açık" : "Oturum açık"}</span>
      <button onClick={onOnboardingComplete}>Kurulumu tamamla</button></div>
  ),
  CoreConnectedApp: () => null, Uygulama: () => null,
}));

const originalStorage = Object.getOwnPropertyDescriptor(window, "localStorage");
afterEach(() => {
  cleanup(); vi.restoreAllMocks();
  if (originalStorage) Object.defineProperty(window, "localStorage", originalStorage);
});

describe("App depolama erişim arızası", () => {
  it("getItem reddedilince kurulum açılmaya devam eder", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("Erişim yok", "SecurityError"); });
    expect(() => render(<App />)).not.toThrow();
    expect(screen.getByText("Kurulum açık")).toBeTruthy();
  });
  it("localStorage getter reddedilince kurulum açılmaya devam eder", () => {
    Object.defineProperty(window, "localStorage", { configurable: true, get: () => { throw new DOMException("Erişim yok", "SecurityError"); } });
    expect(() => render(<App />)).not.toThrow();
    expect(screen.getByText("Kurulum açık")).toBeTruthy();
  });
  it("tamamlama yazılamasa da o pencerede oturuma geçer", () => {
    vi.spyOn(Storage.prototype, "getItem").mockReturnValue(null);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("Kota dolu", "QuotaExceededError"); });
    render(<App />);
    const preventStorageError = (event: ErrorEvent) => event.preventDefault();
    window.addEventListener("error", preventStorageError);
    fireEvent.click(screen.getByRole("button", { name: "Kurulumu tamamla" }));
    window.removeEventListener("error", preventStorageError);
    expect(screen.getByText("Oturum açık")).toBeTruthy();
  });
});
