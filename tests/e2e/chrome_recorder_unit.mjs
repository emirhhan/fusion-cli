// Eklentinin ekran kaydedicisi (recorder.js) Node'da: sahte kare kaynağıyla başlat/durdur/
// parça parça çek. Tarayıcı API'si yok; OffscreenCanvas de yok, kare olduğu gibi (base64)
// döner. Kullanım: node chrome_recorder_unit.mjs
import assert from "node:assert/strict";
import { CHUNK_BYTES, MAX_FRAMES, handleRecord, resetRecorder } from "../../chrome-extension/recorder.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let captures = 0;
const capture = async () => `data:image/jpeg;base64,${"Zm90bw==".repeat(1)}${String(++captures).padStart(4, "0")}`;
const target = async () => ({ tabId: 1, windowId: 7, width: 100, height: 50, url: "https://ornek.test/" });

// Kayıt dışında 'stop'/'fetch' anlaşılır hata verir.
await assert.rejects(handleRecord({ op: "stop" }, capture, target), /önce 'start'/);

// Aralık 200 ms altına inmez (eklenti CPU/bellek koruması).
const started = await handleRecord({ op: "start", interval_ms: 50 }, capture, target);
assert.equal(started.interval_ms, 200);
assert.equal(started.recording, true);
assert.equal(started.max_frames, MAX_FRAMES);
assert.equal(started.url, "https://ornek.test/");
// İkinci başlatma reddedilir; kayıt sürerken kare çekilemez.
await assert.rejects(handleRecord({ op: "start" }, capture, target), /zaten sürüyor/);
await assert.rejects(handleRecord({ op: "fetch" }, capture, target), /önce 'stop'/);
await sleep(650);
const status = await handleRecord({ op: "status" }, capture, target);
assert.equal(status.recording, true);
assert.ok(status.frames >= 3, `en az 3 kare beklenirdi: ${status.frames}`);

const stopped = await handleRecord({ op: "stop" }, capture, target);
assert.ok(stopped.frames >= 3);
assert.ok(stopped.duration_ms >= 100);
const before = captures;
await sleep(260);
assert.equal(captures, before, "durdurulan kayıt kare almayı sürdürmemeli");

// Kareler sırayla ve zaman damgasıyla gelir; son parçada next=null ve oturum bırakılır.
const chunk = await handleRecord({ op: "fetch", from: 0 }, capture, target);
assert.equal(chunk.from, 0);
assert.equal(chunk.frames.length, stopped.frames);
assert.equal(chunk.next, null);
assert.ok(chunk.frames.every((frame, index) => typeof frame.image === "string" && (index === 0 || frame.t >= chunk.frames[index - 1].t)));
assert.ok(chunk.frames[0].t <= 20, "ilk kare başlangıç anına yakın");
// Ölçüldü (31 Ekim): son parça oturumu bırakıyordu; GIF yazımı Fusion tarafında düşerse
// (yazma alanı dışı, Pillow hatası) kareler kayboluyordu. Kareler 'release'e dek durur.
const repeat = await handleRecord({ op: "fetch", from: 0 }, capture, target);
assert.equal(repeat.frames.length, chunk.frames.length, "kareler teslimden sonra da yeniden çekilebilmeli");
assert.deepEqual(await handleRecord({ op: "release" }, capture, target), { released: true, frames: chunk.frames.length });
await assert.rejects(handleRecord({ op: "fetch", from: 0 }, capture, target), /önce 'start'/);

// Büyük kareler köprü sınırına göre parçalanır.
resetRecorder();
const big = async () => `data:image/jpeg;base64,${"A".repeat(Math.ceil(CHUNK_BYTES * 0.6))}`;
await handleRecord({ op: "start", interval_ms: 200 }, big, target);
await sleep(450);
const bigStop = await handleRecord({ op: "stop" }, big, target);
assert.ok(bigStop.frames >= 2);
const first = await handleRecord({ op: "fetch", from: 0 }, big, target);
assert.equal(first.frames.length, 1, "tek parçaya tek büyük kare sığar");
assert.equal(first.next, 1);
const second = await handleRecord({ op: "fetch", from: first.next }, big, target);
assert.ok(second.frames.length >= 1);

// Kare alınamayan kayıt başlamaz.
resetRecorder();
const broken = async () => { throw new Error("izin yok"); };
await assert.rejects(handleRecord({ op: "start" }, broken, target), /Kayıt başlatılamadı: izin yok/);
await assert.rejects(handleRecord({ op: "start" }, capture, async () => { throw new Error("sekme yok"); }), /sekme yok/);
await assert.rejects(handleRecord({ op: "zıpla" }, capture, target), /önce 'start'/);

// Kayıt sırasında etkin sekme değişirse (kullanıcı e-posta/banka sekmesine geçti) kare alınmaz;
// atlanan sayı ve sebep durdurmada döner. Ölçüldü (31 Ekim, bağımsız inceleme): captureVisibleTab
// pencerenin o anki etkin sekmesini verir, izinsiz sekme GIF'e giriyordu.
resetRecorder();
let ticks = 0;
const guard = async () => (++ticks % 2 === 0 ? { ok: false, reason: "pencerede başka sekme etkin" } : { ok: true });
const guarded = await handleRecord({ op: "start", interval_ms: 200 }, capture, target, guard);
assert.equal(guarded.recording, true);
await sleep(650);
const guardedStop = await handleRecord({ op: "stop" }, capture, target, guard);
assert.ok(guardedStop.skipped >= 1, `atlanan kare beklenirdi: ${guardedStop.skipped}`);
assert.equal(guardedStop.skip_reason, "pencerede başka sekme etkin");
assert.ok(guardedStop.frames >= 1 && guardedStop.frames + guardedStop.skipped === ticks);
await handleRecord({ op: "release" }, capture, target, guard);
// İlk kare bile alınamazsa (başka sekme etkin) kayıt başlamaz ve sebep söylenir.
await assert.rejects(
  handleRecord({ op: "start" }, capture, target, async () => ({ ok: false, reason: "sekme kapandı" })),
  /Kayıt başlatılamadı: sekme kapandı/,
);

resetRecorder();
console.log("chrome-recorder ✓");
