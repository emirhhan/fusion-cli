// Fusion Browser ekran kaydı (P-044): bağlı sekmenin ardışık `captureVisibleTab`
// kareleri. `tabCapture`/`desktopCapture` izni İSTENMEZ; ekran görüntüsüyle aynı izin
// (tüm siteler) yeter. Kareler uzun yaşayan belgede (arka plandaki offscreen belge ya da
// elle bağlantıda yan panel) tutulur: hizmet çalışanı 30 sn boşta kalınca durdurulur ve
// orada tutulan kareler kaybolurdu. GIF'i Fusion (Python, Pillow) birleştirir; kareler
// köprü sınırına (4 MB) sığacak parçalar hâlinde çekilir.

export const FRAME_INTERVAL_MS = 500;
/** En fazla kare: 120 × 500 ms = 60 sn. */
export const MAX_FRAMES = 120;
export const MAX_FRAME_WIDTH = 960;
/** Tek `fetch` yanıtındaki base64 kare verisinin üst sınırı (köprü 4 MB kabul eder). */
export const CHUNK_BYTES = 2_500_000;
const JPEG_QUALITY = 0.55;

let session = null;

function toBase64(bytes) {
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary);
}

/** Kareyi en çok MAX_FRAME_WIDTH genişliğe küçült ve düşük kaliteli JPEG olarak kodla. */
async function shrink(dataUrl) {
  if (typeof createImageBitmap !== "function" || typeof OffscreenCanvas !== "function") {
    return { image: dataUrl.split(",")[1] || "", width: 0, height: 0 };
  }
  const blob = await (await fetch(dataUrl)).blob();
  const bitmap = await createImageBitmap(blob);
  const scale = Math.min(1, MAX_FRAME_WIDTH / bitmap.width);
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = new OffscreenCanvas(width, height);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const encoded = await canvas.convertToBlob({ type: "image/jpeg", quality: JPEG_QUALITY });
  return { image: toBase64(new Uint8Array(await encoded.arrayBuffer())), width, height };
}

/**
 * `record` komutu: `op: start | stop | fetch | status`.
 * `capture(windowId)` kareyi JPEG data URL olarak verir; `resolveTarget()` arka plandaki
 * `record_target` işlemiyle bağlı sekmeyi (izin denetimiyle) bulur.
 */
export async function handleRecord(veri, capture, resolveTarget) {
  const op = String(veri.op || "");
  if (op === "start") {
    if (session && session.timer) throw new Error("Kayıt zaten sürüyor; önce 'stop' ile bitir.");
    const target = await resolveTarget();
    const interval = Math.max(200, Math.min(2000, Number(veri.interval_ms) || FRAME_INTERVAL_MS));
    const current = { frames: [], started: Date.now(), target, width: 0, height: 0, timer: null, busy: false, error: "" };
    session = current;
    const tick = async () => {
      if (session !== current || current.busy) return;
      if (current.frames.length >= MAX_FRAMES) { clearInterval(current.timer); current.timer = null; return; }
      current.busy = true;
      try {
        const frame = await shrink(await capture(target.windowId));
        current.frames.push({ t: Date.now() - current.started, image: frame.image });
        if (frame.width) { current.width = frame.width; current.height = frame.height; }
      } catch (cause) {
        current.error = String((cause && cause.message) || cause);
      } finally {
        current.busy = false;
      }
    };
    current.timer = setInterval(() => void tick(), interval);
    await tick();
    if (!current.frames.length) {
      clearInterval(current.timer);
      session = null;
      throw new Error(`Kayıt başlatılamadı: ${current.error || "kare alınamadı"}`);
    }
    return { recording: true, interval_ms: interval, max_frames: MAX_FRAMES, url: target.url };
  }
  if (!session) throw new Error("Süren ya da bekleyen kayıt yok; önce 'start'.");
  if (op === "status") {
    return { recording: Boolean(session.timer), frames: session.frames.length, error: session.error };
  }
  if (op === "stop") {
    if (session.timer) clearInterval(session.timer);
    session.timer = null;
    return {
      frames: session.frames.length, width: session.width, height: session.height,
      duration_ms: session.frames.at(-1)?.t ?? 0, url: session.target.url, error: session.error,
    };
  }
  if (op === "fetch") {
    if (session.timer) throw new Error("Kayıt sürüyor; kareleri almak için önce 'stop'.");
    const from = Math.max(0, Number(veri.from) || 0);
    const frames = [];
    let bytes = 0;
    let index = from;
    for (; index < session.frames.length; index += 1) {
      const frame = session.frames[index];
      if (frames.length && bytes + frame.image.length > CHUNK_BYTES) break;
      frames.push(frame);
      bytes += frame.image.length;
    }
    const next = index < session.frames.length ? index : null;
    if (next === null) session = null; // kareler teslim edildi; bellek bırakılır
    return { from, frames, next };
  }
  throw new Error("record için op: start, stop, fetch ya da status olmalı.");
}

/** Testler ve yeni kayıt için oturumu sıfırlar. */
export function resetRecorder() {
  if (session?.timer) clearInterval(session.timer);
  session = null;
}
