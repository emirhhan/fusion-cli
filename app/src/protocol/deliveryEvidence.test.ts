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

// U5-09 — Ölçüldü (29 Ekim): `sorunlar > 10` / `degisen > 50` TÜM kanıtı geçersiz yapıp
// blocking:false, falseClaim:false döndürüyordu; en kötü durum en zararsız görünüyordu.
it("tavanı aşan listeler kesilir, engelliyor/yanlış iddia korunur", () => {
  const sorunlar = Array.from({length: 15}, (_, i) => `sorun ${i}`);
  const degisen = Array.from({length: 80}, (_, i) => `d${i}.py`);
  const kanit = decodeDeliveryEvidence({...payload, engelliyor: true, yanlis_iddia: true,
    sorunlar, degisen, degisen_sayisi: 80});
  expect(kanit).toMatchObject({kind: "supported", blocking: true, falseClaim: true, changedTotal: 80});
  expect(kanit?.problems).toHaveLength(10);
  expect(kanit?.changed).toHaveLength(50);
});
it("geçersiz kanıt fail-closed: engelliyor varsayılır, okunabilen yanlış iddia korunur", () => {
  const kanit = decodeDeliveryEvidence({...payload, degisen: ["a.py", 2], yanlis_iddia: true});
  expect(kanit).toMatchObject({kind: "invalid", blocking: true, falseClaim: true, verified: null});
  expect(decodeDeliveryEvidence({...payload, engelliyor: "false"})).toMatchObject({kind: "invalid", blocking: true});
});
it("desteklenmeyen sürüm engelliyor varsaymaz", () => {
  expect(decodeDeliveryEvidence({...payload, schema_version: 999})).toMatchObject({kind: "unsupported", blocking: false});
});
