import { h } from "./dom.js";
import { createDock } from "./dock.js";
import { createScreenStream } from "./screen-stream.js";

const LABELS = {
  idle: "Ekran paylaşılmıyor.", pending: "Ekran izleme başlatılıyor…", live: "Canlı",
  paused: "Sayfa arka planda; duraklatıldı.", reconnecting: "Bağlantı koptu, yeniden deneniyor…",
  ended: "Oturum bitti. Yeniden başlatabilirsin.", stopped: "Ekran paylaşımı durduruldu; hatırlanan izin kaldırıldı.", auth: "Eşleşme geçersiz.",
};

export function createScreenView({ rpc, onAuth, toast }) {
  const box = document.getElementById("ekranKutu");
  const image = document.getElementById("ekranKare");
  const status = document.getElementById("ekranDurum");
  const start = document.getElementById("ekranIste");
  const stop = document.getElementById("ekranDur");
  let opened = false;
  let busy = false;
  let generation = 0;
  let dock = null;
  const consent = h("section", { class: "screen-consent", hidden: true, "aria-label": "Ekran izleme izni" });
  const remember = h("input", { type: "checkbox" });
  remember.checked = true;
  const confirm = h("button", { class: "btn", type: "button" }, "Onayla ve izlemeyi başlat");
  const cancel = h("button", { class: "btn ghost", type: "button" }, "Vazgeç");
  consent.append(h("h3", {}, "Bilgisayar ekranını bu telefonda izle"),
    h("p", { class: "muted small" }, "Ekrandaki içerikler bu eşleşmiş cihazda görünür. Durdur düğmesi izni de kaldırır."),
    h("label", { class: "screen-consent__remember" }, remember, "Bu cihaz için izni hatırla"), confirm, cancel);
  const dockRoot = h("div", {});
  stop.parentElement.after(consent, dockRoot);
  function clearFrame() { image.removeAttribute("src"); box.style.removeProperty("aspect-ratio"); box.classList.add("empty-screen"); }
  function setState({ state, message }) {
    if (!opened) return;
    status.textContent = message || LABELS[state] || "Ekran alınamadı.";
    status.className = `chip ${state === "live" ? "ok" : ["error", "reconnecting"].includes(state) ? "bad" : ""}`;
    const watching = ["pending", "live", "paused", "reconnecting"].includes(state);
    start.hidden = watching;
    stop.hidden = !watching && state !== "error";
    if (["stopped", "ended", "auth", "idle", "error"].includes(state)) clearFrame();
    if (state === "auth") onAuth?.();
  }
  const stream = createScreenStream({ rpc, onState: setState, onFrame(data) {
    if (opened && typeof data?.jpegBase64 === "string" && /^[A-Za-z0-9+/]+=*$/.test(data.jpegBase64)) image.src = `data:image/jpeg;base64,${data.jpegBase64}`;
  } });
  const imageLoaded = () => {
    if (!opened || !image.hasAttribute("src") || !image.naturalWidth || !image.naturalHeight) return;
    box.style.aspectRatio = `${image.naturalWidth} / ${image.naturalHeight}`;
    box.classList.remove("empty-screen");
  };
  const visibility = () => stream.setVisible(!document.hidden);
  const toggleFullscreen = () => { if (!box.classList.contains("empty-screen")) document.body.classList.toggle("fullscreen"); };
  const keyboard = (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggleFullscreen(); } };
  async function begin() {
    if (busy || !opened) return;
    busy = true; start.disabled = true;
    const token = generation;
    try {
      const result = await rpc("screen.status");
      if (!opened || token !== generation) return;
      if (!result.ok) throw new Error(result.message || "Ekran durumu alınamadı.");
      if (result.data?.remembered || result.data?.state === "active") {
        consent.hidden = true;
        await stream.start({ request: true });
      } else { consent.hidden = false; confirm.focus(); }
    } catch (reason) {
      if (reason.auth) onAuth?.();
      else { setState({ state: "error", message: reason.message }); toast?.(reason.message); }
    } finally { busy = false; start.disabled = false; }
  }
  async function approve() {
    if (busy || !opened) return;
    busy = true; confirm.disabled = true;
    consent.hidden = true;
    try { await stream.start({ request: true, remember: remember.checked, confirmed: true }); }
    finally { busy = false; confirm.disabled = false; }
  }
  async function end() {
    generation += 1;
    consent.hidden = true;
    remember.checked = true;
    clearFrame();
    await stream.stop();
  }
  cancel.onclick = () => { consent.hidden = true; start.focus(); };
  return {
    async open() {
      if (opened) return;
      opened = true; generation += 1;
      start.onclick = begin; stop.onclick = end; confirm.onclick = approve;
      box.addEventListener("click", toggleFullscreen); box.addEventListener("keydown", keyboard);
      image.addEventListener("load", imageLoaded);
      document.addEventListener("visibilitychange", visibility);
      stream.setVisible(!document.hidden);
      dock = createDock({ rpc, root: dockRoot, toast });
      void dock.refresh();
      const token = generation;
      try {
        const initial = await rpc("screen.status");
        if (!opened || token !== generation) return;
        if (initial.ok && initial.data?.state === "pending" && !initial.data?.remembered) {
          setState({ state: "idle", message: "Ekran izlemeyi başlatmak için bu telefonda onay ver." });
          return;
        }
        await stream.start({ request: false });
      } catch (reason) {
        if (!opened || token !== generation) return;
        if (reason.auth) onAuth?.();
        else setState({ state: "error", message: reason.message || "Ekran durumu alınamadı." });
      }
    },
    close() {
      opened = false; generation += 1;
      stream.detach(); dock?.close(); dock = null;
      consent.hidden = true; busy = false; start.disabled = false; confirm.disabled = false;
      start.onclick = null; stop.onclick = null; confirm.onclick = null;
      box.removeEventListener("click", toggleFullscreen); box.removeEventListener("keydown", keyboard);
      image.removeEventListener("load", imageLoaded); document.removeEventListener("visibilitychange", visibility);
      document.body.classList.remove("fullscreen"); clearFrame();
    },
  };
}
