import { expect, it } from "vitest";
import { readStorage, removeStorage, writeStorage } from "./storage";
it("depo getter reddini okuma yazma silmede sonuç olarak taşır", () => {
  const denied = (): Storage => { throw new DOMException("Depo erişimi yok", "SecurityError"); };
  expect(readStorage(denied, "test")).toEqual({ ok: false, message: "Depo erişimi yok" });
  expect(writeStorage(denied, "test", "value").ok).toBe(false);
  expect(removeStorage(denied, "test").ok).toBe(false);
});
