import {expect, it} from "vitest";
import {decodeDeliveryEvidence} from "./deliveryEvidence";
import backendFixtures from "./__fixtures__/document-delivery-v6.json";

const payload = {schema_version: 1, dogrulandi: true, engelliyor: false,
  yanlis_iddia: false, degisen: ["a.py"], sorunlar: [], degisen_sayisi: 60};
const documentPayload={...payload,degisen:["rapor.html"],degisen_sayisi:1,sunum:"document"};

it.each(backendFixtures)("gerçek backend projeksiyonu tutarlı çözülür: $name", fixture => {
  const decoded=decodeDeliveryEvidence(fixture.kanit);
  expect(decoded?.kind).toBe("supported");
  expect(decoded?.deliveryKind).toBe("code");
  expect(decoded?.presentation).toBe(fixture.compact ? "document" : undefined);
  expect(decoded?.unmeasured).toEqual(fixture.kanit.olculmeyen);
  expect(decoded?.warnings).toEqual(fixture.kanit.uyarilar);
});

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

it("doğrulanmış belgenin kalıcı teknik ayrıntılarını çözer", () => {
  expect(decodeDeliveryEvidence({...documentPayload, kontroller: ["Tarayıcıda açıldı"],
    olculmeyen: [], oneriler: ["Ana içerik işaretlenebilir"], degisiklik_ozeti: ["rapor.html: yeni dosya"],
    ayrintilar_kisaltildi: false})).toMatchObject({presentation: "document", checks: ["Tarayıcıda açıldı"],
      unmeasured: [], advisories: ["Ana içerik işaretlenebilir"], changeSummary: ["rapor.html: yeni dosya"], detailsTruncated: false});
});

it.each([{dogrulandi: false}, {engelliyor: true}, {yanlis_iddia: true}, {sorunlar: ["hata"]},
  {uyarilar: ["uyarı"]}, {olculmeyen: ["Tarayıcı koşmadı"]}, {schema_version: undefined}])(
  "belge işareti sorun veya ölçüm eksikliğini güvenli görünüme dönüştürmez: %s", change => {
    const evidence = decodeDeliveryEvidence({...documentPayload, ...change});
    expect(evidence?.presentation).toBeUndefined();
  });

it.each([{kontroller: [1]}, {oneriler: "not"}, {olculmeyen: [null]},
  {degisiklik_ozeti: [{}]}, {ayrintilar_kisaltildi: "false"}])("bozuk ek ayrıntı fail-closed kalır: %s", change => {
  expect(decodeDeliveryEvidence({...payload, ...change})).toMatchObject({kind: "invalid", blocking: true});
});

it("ayrıntıları maskeler ve Unicode metin, liste ve toplam bütçelerini sınırlar", () => {
  const evidence = decodeDeliveryEvidence({...documentPayload, kontroller: Array(20).fill("😀".repeat(900)),
    oneriler: ["Authorization: Bearer abcdefghijklmnopqrst"], degisiklik_ozeti: Array(80).fill("😀".repeat(900))});
  expect(evidence?.checks?.length).toBeLessThanOrEqual(10);
  expect(evidence?.changeSummary?.length).toBeLessThanOrEqual(50);
  expect(evidence?.advisories?.join("")).not.toContain("abcdefghijklmnopqrst");
  expect(evidence?.detailsTruncated).toBe(true);
  expect(new TextEncoder().encode(JSON.stringify(evidence)).byteLength).toBeLessThanOrEqual(32768);
  expect(JSON.stringify(evidence)).not.toMatch(/\\ud[89ab][0-9a-f]{2}(?!\\ud[cdef])/i);
});

it("kritik kanıt tek başına bütçeyi aşınca sorunları silip başarı üretmez", () => {
  const evidence=decodeDeliveryEvidence({...payload, yanlis_iddia:true,
    sorunlar:Array(10).fill("😀".repeat(500)), uyarilar:Array(10).fill("😀".repeat(500))});
  expect(evidence).toMatchObject({kind:"invalid",blocking:true,falseClaim:true,verified:null});
});

it("bilinmeyen sunum işareti eski görünümü değiştirmez", () => {
  expect(decodeDeliveryEvidence({...payload,sunum:"future"})?.presentation).toBeUndefined();
});

it("dosya yolunu başka bir dosyanın adına kırpmaz", () => {
  const path=`${"folder/".repeat(80)}report.html`;
  expect(decodeDeliveryEvidence({...payload,degisen:[path],degisen_sayisi:1})?.changed).toEqual([path]);
  const hugePath=`${"folder/".repeat(6000)}report.html`;
  const huge=decodeDeliveryEvidence({...documentPayload,degisen:[hugePath]});
  expect(huge).toMatchObject({changed:[],changedTotal:1,detailsTruncated:true});
  expect(huge?.presentation).toBeUndefined();
  expect(decodeDeliveryEvidence({...documentPayload,degisen:['dir/sk-abcdefghijklmnopqrstuvwx/report.html']}))
    .toMatchObject({changed:[],changedTotal:1,detailsTruncated:true});
});
