import {expect, it} from "vitest";
import {decodeDeliveryEvidence} from "./deliveryEvidence";
import backendFixtures from "./__fixtures__/document-delivery-v6.json";
import countFixtures from "./__fixtures__/document-delivery-critical-counts-v6.json";

const payload = {schema_version: 1, dogrulandi: true, engelliyor: false,
  yanlis_iddia: false, degisen: ["a.py"], sorunlar: [], degisen_sayisi: 60};
const documentPayload={...payload,degisen:["rapor.html"],degisen_sayisi:1,sunum:"document"};

it("zayıflatılan test metadatası doğrulanmış teslim gibi görünmez",()=>{
  expect(decodeDeliveryEvidence({...documentPayload,supheli_test_degisikligi:{adet:1,zayiflatan:1}}))
    .toMatchObject({kind:"invalid",verified:null,blocking:true});
});
it.each([null,[],{}, {adet:"1",zayiflatan:0},{adet:1,zayiflatan:true},
  {adet:-1,zayiflatan:0},{adet:0,zayiflatan:1},{adet:Number.MAX_SAFE_INTEGER+1,zayiflatan:0},
  {adet:1,zayiflatan:0,turler:null},{adet:1,zayiflatan:0,yollar:[1]}])(
  "bozuk tanınan test metadatası başarıya dönüşmez: %s",tamper=>{
    expect(decodeDeliveryEvidence({...documentPayload,yanlis_iddia:true,supheli_test_degisikligi:tamper}))
      .toMatchObject({kind:"invalid",verified:null,blocking:true,falseClaim:true});
  });
it("şüpheli değişiklik bulgusu ölçülmüş başarı sayılmaz ve ham metadata gösterilmez",()=>{
  const evidence=decodeDeliveryEvidence({...documentPayload,
    supheli_test_degisikligi:{adet:1,zayiflatan:0,turler:["suspicious"],yollar:["private-test.ts"],future:{secret:"raw"}}});
  expect(evidence).toMatchObject({verified:null});
  expect(evidence?.presentation).toBeUndefined();
  expect(JSON.stringify(evidence)).not.toMatch(/private-test|secret|suspicious/);
});
it("sıfır bulgulu metadata kompakt belgeyi açmaz, bilinmeyen ek alan kritik sayılmaz",()=>{
  const evidence=decodeDeliveryEvidence({...documentPayload,
    supheli_test_degisikligi:{adet:0,zayiflatan:0,future:1},
    criteria_count:1,criteria_status_counts:{passed:1,failed:0,unverified:0,future:99}});
  expect(evidence).toMatchObject({kind:"supported",verified:true});
  expect(evidence?.presentation).toBeUndefined();
});
it("tanınan durum toplamı ölçüt sayısını aşıyorsa doğrulanmış sayılmaz",()=>{
  expect(decodeDeliveryEvidence({...documentPayload,criteria_count:1,
    criteria_status_counts:{passed:2,failed:0,unverified:0}}))
    .toMatchObject({kind:"invalid",verified:null,blocking:true});
});

it.each(Object.entries(countFixtures))("kritik sayaçlar backend projeksiyonuyla aynı güvenli sonucu korur: %s", (_name, fixture) => {
  const input=decodeDeliveryEvidence(fixture.input);
  const projected=decodeDeliveryEvidence(fixture.projected);
  expect(input?.verified).toBe(projected?.verified);
  expect(input?.blocking).toBe(projected?.blocking);
  expect(input?.presentation).toBe(projected?.presentation);
});

it("kısaltılmış ayrıntılar kritik toplamları ortadan kaldırmaz", () => {
  const evidence=decodeDeliveryEvidence({...documentPayload,sorun_sayisi:3,sorunlar:[],
    criteria_count:3,criteria:[{status:"passed"}],criteria_status_counts:{passed:1,failed:1,unverified:1}});
  expect(evidence).toMatchObject({verified:false,blocking:true,problemTotal:3,criteriaTotal:3,
    criteriaStatusCounts:{passed:1,failed:1,unverified:1}});
  expect(evidence?.presentation).toBeUndefined();
});

it.each(["failed","unverified"])("ayrıntı listesinde görülen %s durumu da kaybolmaz", status => {
  const evidence=decodeDeliveryEvidence({...documentPayload,criteria:[{status}],criteria_count:1});
  expect(evidence?.verified).toBe(status === "failed" ? false : null);
  expect(evidence?.blocking).toBe(status === "failed");
  expect(evidence?.presentation).toBeUndefined();
});

it("tam durum toplamları yokken gösterilmeyen ölçütleri başarılı varsaymaz", () => {
  const evidence=decodeDeliveryEvidence({...documentPayload,criteria:[{status:"passed"}],criteria_count:3});
  expect(evidence).toMatchObject({verified:null,blocking:false,criteriaTotal:3});
  expect(evidence?.presentation).toBeUndefined();
});

it("tam durum toplamlarının kapsamadığı ölçütleri başarılı varsaymaz", () => {
  expect(decodeDeliveryEvidence({...documentPayload,criteria_count:3,
    criteria_status_counts:{passed:1,failed:0,unverified:0}}))
    .toMatchObject({verified:null,blocking:false,criteriaTotal:3,
      criteriaStatusCounts:{passed:1,failed:0,unverified:0}});
});

it("ölçülmeyen toplamı mevcut başarısızlığı veya engellemeyi kaldırmaz", () => {
  expect(decodeDeliveryEvidence({...documentPayload,dogrulandi:false,engelliyor:true,
    criteria_status_counts:{passed:0,failed:0,unverified:1}}))
    .toMatchObject({verified:false,blocking:true});
});

it("ayrıntı bütçesi kritik toplamları silemez", () => {
  const evidence=decodeDeliveryEvidence({...documentPayload,sorun_sayisi:3,
    criteria_status_counts:{passed:0,failed:1,unverified:1},
    degisiklik_ozeti:Array(50).fill("😀".repeat(500))});
  expect(evidence).toMatchObject({verified:false,blocking:true,problemTotal:3,
    criteriaStatusCounts:{passed:0,failed:1,unverified:1},detailsTruncated:true});
  expect(new TextEncoder().encode(JSON.stringify(evidence)).byteLength).toBeLessThanOrEqual(32768);
});

it.each([{sorun_sayisi:"3"},{sorun_sayisi:-1},{sorun_sayisi:true},{sorun_sayisi:0,sorunlar:["hata"]},
  {criteria_count:1.5},{criteria_count:NaN},{criteria_count:Number.MAX_SAFE_INTEGER+1},
  {criteria_status_counts:{passed:Number.MAX_SAFE_INTEGER,failed:1,unverified:0}},
  {criteria_status_counts:{failed:1}},
  {criteria_status_counts:{passed:0,failed:"1",unverified:0}},
  {criteria:[{status:"future"}]},{criteria_count:0,criteria:[{status:"passed"}]}])(
  "bozuk kritik sayaç/durum verisi başarıya çevrilmez: %s", change => {
    expect(decodeDeliveryEvidence({...documentPayload,yanlis_iddia:true,...change}))
      .toMatchObject({kind:"invalid",verified:null,blocking:true,falseClaim:true});
  });

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
