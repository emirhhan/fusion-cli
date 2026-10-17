import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readPairingScopes, REMOTE_SCOPES_KEY, savePairingScopes } from "./remotePreferences";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

it("kapatılan kapsamı sonraki okumalardan kaldırır", () => {
  savePairingScopes(["desktop.control"]);
  expect(readPairingScopes()).toEqual(["desktop.control"]);
  savePairingScopes([]);
  expect(readPairingScopes()).toEqual([]);
});

it("yazarken de bilinmeyen ve tekrar eden kapsamları temizler", () => {
  savePairingScopes(["desktop.observe", "unknown", "desktop.observe"]);
  expect(JSON.parse(window.localStorage.getItem(REMOTE_SCOPES_KEY)!)).toEqual({ version: 1, scopes: ["desktop.observe"] });
});

it("depo erişilemiyorsa kapalı başlar ve kaydetme uygulamayı durdurmaz", () => {
  vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new DOMException("Depo kapalı", "SecurityError"); });
  expect(readPairingScopes()).toEqual([]);
  expect(() => savePairingScopes(["desktop.control"])).not.toThrow();
});
