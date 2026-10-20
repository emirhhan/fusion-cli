import { expect, it } from "vitest";
import { errorMessage, operationResult } from "./result";
it("başka realm hata nesnesinin gerçek nedenini korur", () => {
  expect(errorMessage({ name: "SecurityError", message: "Depo erişimi yok" })).toBe("Depo erişimi yok");
  expect(errorMessage(new DOMException("Depo erişimi yok", "SecurityError"))).toBe("Depo erişimi yok");
});
it("çözülmüş başarısız işlem legacy seçilse de başarı sayılmaz", () => {
  expect(operationResult({ ok: false, metin: "Bağlantı reddedildi" }, "Hata", true)).toEqual({ ok: false, message: "Bağlantı reddedildi" });
  expect(operationResult(undefined, "Hata")).toEqual({ ok: false, message: "Hata" });
  expect(operationResult(undefined, "Hata", true)).toEqual({ ok: true });
});
