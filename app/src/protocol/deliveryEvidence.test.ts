import {expect, it} from "vitest";
import {decodeDeliveryEvidence} from "./deliveryEvidence";

const payload = {schema_version: 1, dogrulandi: true, engelliyor: false,
  yanlis_iddia: false, degisen: ["a.py"], sorunlar: [], degisen_sayisi: 60};

it("sürüm ve toplam kapsamı taşır", () => {
  expect(decodeDeliveryEvidence(payload)).toMatchObject({kind: "supported", changedTotal: 60});
});
it("gelecek sürümün başarı alanlarına güvenmez", () => {
  expect(decodeDeliveryEvidence({...payload, schema_version: 999})).toMatchObject({kind: "unsupported", verified: null, changed: []});
});
it.each([{degisen: ["a.py", 2]}, {degisen_sayisi: NaN}, {degisen_sayisi: 0}, {engelliyor: "false"}])("bozuk kanıt yükseltilmez: %s", (change) => {
  expect(decodeDeliveryEvidence({...payload, ...change})?.kind).toBe("invalid");
});
it("eski kayıt sınırlı kalır", () => {
  const {schema_version: _schema, degisen_sayisi: _count, ...legacy} = payload;
  expect(decodeDeliveryEvidence(legacy)).toMatchObject({kind: "legacy", changedTotal: null});
});
it("kanıt yokluğunda kart uydurmaz", () => {
  expect(decodeDeliveryEvidence(undefined)).toBeUndefined();
});
