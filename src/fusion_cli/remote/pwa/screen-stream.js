// Canlı ekran akışı: kopmaya dayanıklı, tek istek uçuşta, sayfa görünürlüğüne duyarlı.
// Tarayıcıya bağımlı hiçbir şey import etmez; rpc/sleep dışarıdan verilir (Node'da test edilir).

export const FRAME_MS = 600;
export const PENDING_POLL_MS = 2000;
export const BACKOFF_START_MS = 1000;
export const BACKOFF_MAX_MS = 15000;
export const BUSY_RETRY_MS = 5000;

const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function createScreenStream({
  rpc,
  onFrame,
  onState,
  sleep = defaultSleep,
  frameMs = FRAME_MS,
}) {
  let generation = 0;
  let visible = true;
  let wake = null;

  const emit = (state, detail = {}) => onState({ state, ...detail });
  const alive = (token) => token === generation;

  async function waitVisible(token) {
    while (alive(token) && !visible) {
      emit("paused");
      await new Promise((resolve) => { wake = resolve; });
    }
  }

  async function nap(ms, token) {
    await sleep(ms);
    await waitVisible(token);
  }

  async function step(token) {
    const frame = await rpc("screen.frame");
    if (!alive(token)) return 0;
    if (frame.ok) {
      onFrame(frame.data);
      emit("live");
      return frameMs;
    }
    if (frame.error === "cok_sik") return frameMs;
    if (frame.error === "ekran_onay_yok") {
      const status = await rpc("screen.status");
      if (!alive(token)) return 0;
      const state = status.data?.state ?? "none";
      if (state === "pending") { emit("pending"); return PENDING_POLL_MS; }
      if (state === "active") return frameMs;
      emit("ended");
      return -1;
    }
    emit("error", { message: frame.message || "Ekran alınamadı." });
    return BUSY_RETRY_MS;
  }

  async function loop(token) {
    let backoff = BACKOFF_START_MS;
    while (alive(token)) {
      await waitVisible(token);
      if (!alive(token)) return;
      let delay;
      try {
        delay = await step(token);
        backoff = BACKOFF_START_MS;
      } catch (error) {
        if (!alive(token)) return;
        if (error?.auth) { emit("auth"); return; }
        emit("reconnecting", { retryMs: backoff });
        delay = backoff;
        backoff = Math.min(backoff * 2, BACKOFF_MAX_MS);
      }
      if (delay < 0) return;
      if (delay > 0) await nap(delay, token);
    }
  }

  return {
    // İzleme başlar: etkin oturum varsa sürdürür, yoksa izin ister.
    async start({ request = true, remember = false, confirmed = false } = {}) {
      generation += 1;
      const token = generation;
      try {
        const status = await rpc("screen.status");
        if (!alive(token)) return;
        if (!status.ok) { emit("error", { message: status.message || "Ekran durumu alınamadı." }); return; }
        const state = status.data?.state ?? "none";
        if (state === "none" || (state === "pending" && request && confirmed)) {
          if (!request) { emit("idle"); return; }
          const asked = await rpc("screen.request", { remember, confirmed });
          if (!alive(token)) return;
          if (!asked.ok) { emit("error", { message: asked.message || "İstek reddedildi." }); return; }
        }
      } catch (error) {
        if (!alive(token)) return;
        if (error?.auth) { emit("auth"); return; }
        emit("reconnecting", { retryMs: BACKOFF_START_MS });
      }
      if (!alive(token)) return;
      emit("pending");
      void loop(token);
    },
    // Kullanıcı durdurdu: sunucuya bildirilir, kendiliğinden yenileme yapılmaz.
    async stop() {
      generation += 1;
      if (wake) { const resolve = wake; wake = null; resolve(); }
      try {
        const result = await rpc("screen.stop");
        if (!result.ok) { emit("error", { message: result.message || "İzin kaldırılamadı. Bağlantını kontrol edip tekrar durdur." }); return; }
        emit("stopped");
      } catch (error) {
        emit(error?.auth ? "auth" : "error", { message: "İzin kaldırılamadı. Bağlantını kontrol edip tekrar durdur." });
      }
    },
    // Akış yerel olarak bırakılır (sekme değişti); sunucu oturumu açık kalır ve sürdürülebilir.
    detach() { generation += 1; if (wake) { const resolve = wake; wake = null; resolve(); } },
    setVisible(value) {
      visible = value;
      if (value && wake) { const resolve = wake; wake = null; resolve(); }
    },
  };
}
