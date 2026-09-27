// Fusion yan paneli: Claude in Chrome gibi küçük bir sohbet uygulaması.
// Kullanıcı görevi yazar; Fusion sayfayı okur, kaydırır, tıklar ve her adımı
// burada canlı gösterir. İzin ve sorular panelin içinde kart olarak çıkar.

import { clearSelected, execute, selectActiveTab } from "./core.js";
import { setGlow } from "./pageGlow.js";
import { renderAsk, renderMessage } from "./panelView.js";

const $ = (id) => document.getElementById(id);
const THREAD_KEY = "fusionThread";
/** Panel oturumunda saklanan mesaj sayısı; eski sohbet görünümü şişirmesin. */
const MAX_MESSAGES = 60;
/** Akış koparsa yeniden deneme aralığı. */
const RETRY_MS = 2000;

// Elle eşleştirme bağlantısı; otomatik bağlantı arka plandaki belgede yaşar.
let manual = null;
let polling = false;
let listening = false;
/** Bu panelin kendi gönderdiği ve cevabını beklediği tur var mı? */
let inflight = false;
let thread = { mesajlar: [], seq: null, soru: null };

function error(message = "") { $("error").textContent = message; }

async function autoStatus() {
  return (await chrome.storage.session.get("fusionAuto")).fusionAuto || { bagli: false };
}

async function connection() {
  if (manual) return manual;
  const auto = await autoStatus();
  return auto.bagli ? { port: auto.port, token: auto.token } : null;
}

async function request(path, data = {}) {
  const conn = await connection();
  if (!conn) throw new Error("Fusion bağlantısı yok. Fusion masaüstü uygulamasını aç.");
  const response = await fetch(`http://127.0.0.1:${conn.port}${path}`, {
    method: path === "/status" ? "GET" : "POST",
    headers: { Authorization: `Bearer ${conn.token}`, "Content-Type": "application/json" },
    body: path === "/status" ? undefined : JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.hata || `Fusion yanıtı: ${response.status}`);
  return result;
}

// --- Sohbet durumu -----------------------------------------------------------

async function loadThread() {
  const stored = (await chrome.storage.session.get(THREAD_KEY))[THREAD_KEY];
  if (stored && Array.isArray(stored.mesajlar)) thread = { ...thread, ...stored };
}

async function saveThread(next) {
  thread = { ...next, mesajlar: next.mesajlar.slice(-MAX_MESSAGES) };
  await chrome.storage.session.set({ [THREAD_KEY]: thread });
  renderThread();
}

const running = () => thread.mesajlar.at(-1)?.durum === "calisiyor";

/** Son asistan mesajını değiştir (yenisini kurarak; eskisi yerinde değişmez). */
function withLastAssistant(update) {
  const last = thread.mesajlar.at(-1);
  if (!last || last.rol !== "asistan") return thread;
  return { ...thread, mesajlar: [...thread.mesajlar.slice(0, -1), { ...last, ...update(last) }] };
}

// --- Çizim --------------------------------------------------------------------

function renderThread() {
  const list = $("messages");
  list.replaceChildren(...thread.mesajlar.map(renderMessage));
  $("empty").hidden = thread.mesajlar.length > 0;
  const busy = running();
  $("send").hidden = busy;
  $("cancel").hidden = !busy;
  $("new-chat").disabled = busy;
  if (thread.soru) renderAsk($("ask"), thread.soru, answer);
  else { $("ask").hidden = true; $("ask").replaceChildren(); }
  $("thread").scrollTop = $("thread").scrollHeight;
}

async function renderStatus() {
  const auto = await autoStatus();
  const bagli = Boolean(manual) || auto.bagli;
  $("status").dataset.state = bagli ? "online" : "offline";
  $("status").lastChild.textContent = bagli ? "Bağlı" : "Bağlı değil";
  $("pairing").hidden = auto.bagli && !manual;
  if (bagli) void listen();
}

async function renderTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const url = tab?.url ? new URL(tab.url) : null;
  const web = url && ["http:", "https:"].includes(url.protocol);
  $("tab-label").textContent = web ? url.hostname.replace(/^www\./, "") : "Bu sayfada çalışamaz";
  $("tab-icon").hidden = !tab?.favIconUrl;
  if (tab?.favIconUrl) $("tab-icon").src = tab.favIconUrl;
  const allowed = web && await chrome.permissions.contains({ origins: [`${url.origin}/*`] });
  $("select-tab").hidden = !web || allowed;
}

// --- Canlı akış ---------------------------------------------------------------

async function applyItem(item) {
  if (item.tur === "basladi" && !running()) {
    return { ...thread, mesajlar: [...thread.mesajlar, { rol: "asistan", adimlar: [], durum: "calisiyor" }] };
  }
  if (item.tur === "dusunuyor") return withLastAssistant(() => ({ etiket: "Düşünüyor…" }));
  if (item.tur === "adim" || item.tur === "hata") {
    if (running()) void setGlow(true);
    const step = item.tur === "hata"
      ? { arac: "", metin: item.metin, durum: "failed" }
      : { arac: item.arac, metin: item.metin, durum: item.durum, hata: item.hata };
    return withLastAssistant((last) => ({ adimlar: [...(last.adimlar || []), step], etiket: "Çalışıyor…" }));
  }
  if (item.tur === "soru") return { ...thread, soru: { id: item.id, veri: item.veri } };
  if (item.tur === "soru_kapandi") return thread.soru?.id === item.id ? { ...thread, soru: null } : thread;
  if (item.tur === "bitti" && !inflight) {
    void setGlow(false);
    return { ...withLastAssistant(() => ({ metin: item.metin || "", durum: item.ok ? "bitti" : "hata" })), soru: null };
  }
  return thread;
}

/** Fusion'dan adımları uzun yoklamayla al (Claude'daki canlı adım listesi). */
async function listen() {
  if (listening) return;
  listening = true;
  try {
    if (thread.seq === null) {
      // İlk açılış: eski turları baştan oynatma, akışın ucundan başla.
      const status = await request("/status");
      await saveThread({ ...thread, seq: status.son ?? 0 });
    }
    while (await connection()) {
      const result = await request("/events", { after: thread.seq });
      let next = thread;
      for (const item of result.olaylar || []) {
        thread = next;
        next = { ...(await applyItem(item)), seq: item.seq };
      }
      await saveThread({ ...next, seq: result.son ?? next.seq });
    }
  } catch (cause) {
    error(`Fusion bağlantısı koptu: ${cause.message || cause}`);
    await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
  } finally {
    listening = false;
  }
  if (await connection()) void listen();
}

// --- Güncelleme ---------------------------------------------------------------

const AUTO_UPDATE_KEY = "fusionAutoUpdate";
/** Aynı sürüm için otomatik yenilemeyi bu süre içinde yinelemez (döngü koruması). */
const AUTO_UPDATE_RETRY_MS = 5 * 60 * 1000;
/** Kullanıcı "güncelleniyor" yazısını görebilsin diye kısa bekleme. */
const AUTO_UPDATE_DELAY_MS = 1200;

/**
 * Eklenti dosyaları diskte yenilendiyse ve çalışan görev yoksa eklentiyi kendiliğinden
 * yenile (Chrome yenilemede paneli kapatır; yeniden açılınca yeni sürüm çalışır).
 * Yenileme sürümü değiştirmediyse tekrar denemez, yalnız "Şimdi güncelle" düğmesi kalır.
 */
async function autoUpdate(version) {
  if (running() || typeof chrome.runtime.reload !== "function") return;
  const local = chrome.storage.local;
  const tried = local ? (await local.get(AUTO_UPDATE_KEY))[AUTO_UPDATE_KEY] : null;
  if (tried?.version === version && Date.now() - tried.at < AUTO_UPDATE_RETRY_MS) return;
  await local?.set({ [AUTO_UPDATE_KEY]: { version, at: Date.now() } });
  $("update").firstElementChild.textContent = "Fusion Browser güncelleniyor…";
  setTimeout(() => chrome.runtime.reload(), AUTO_UPDATE_DELAY_MS);
}

// --- Eylemler -----------------------------------------------------------------

async function sendPrompt(text) {
  const prompt = (text ?? $("prompt").value).trim();
  if (!prompt || running()) return;
  error();
  $("prompt").value = "";
  autoGrow();
  inflight = true;
  await saveThread({
    ...thread,
    mesajlar: [...thread.mesajlar, { rol: "kullanici", metin: prompt }, { rol: "asistan", adimlar: [], durum: "calisiyor" }],
  });
  void setGlow(true);
  try {
    const result = await request("/turn", { prompt });
    const durum = result.ok ? "bitti" : thread.mesajlar.at(-1)?.durum === "iptal" ? "iptal" : "hata";
    await saveThread({ ...withLastAssistant(() => ({ metin: result.metin || "", durum })), soru: null });
  } catch (cause) {
    await saveThread({ ...withLastAssistant(() => ({ metin: "", durum: "hata" })), soru: null });
    throw cause;
  } finally {
    inflight = false;
    void setGlow(false);
  }
}

async function cancel() {
  $("cancel").disabled = true;
  try {
    await request("/cancel");
    await saveThread({ ...withLastAssistant(() => ({ durum: "iptal" })), soru: null });
  } finally {
    $("cancel").disabled = false;
  }
}

async function answer(veri) {
  const soru = thread.soru;
  if (!soru) return;
  await saveThread({ ...thread, soru: null });
  try {
    await request("/answer", { id: soru.id, veri });
  } catch (cause) {
    // Cevap gitmediyse kart geri gelir; kullanıcı yeniden seçebilir.
    await saveThread({ ...thread, soru });
    throw cause;
  }
}

async function connect() {
  const port = Number($("port").value);
  const token = $("token").value.trim();
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !token) {
    throw new Error("Fusion portunu ve eşleştirme anahtarını girin.");
  }
  manual = { port, token };
  try { await request("/status"); } catch (cause) { manual = null; throw cause; }
  error();
  $("settings").close?.();
  await renderStatus();
  void poll();
}

/** Elle bağlantıda sayfa komutlarını panel yürütür (otomatikte arka plan). */
async function poll() {
  if (polling) return;
  polling = true;
  while (manual) {
    try {
      const command = await request("/poll");
      if (!command.id) continue;
      let reply;
      try { reply = { id: command.id, ok: true, veri: await execute(command) }; } catch (cause) {
        reply = { id: command.id, ok: false, hata: String(cause.message || cause) };
      }
      await request("/result", reply);
    } catch (cause) {
      error(`Chrome bağlantısı: ${cause.message || cause}`);
      manual = null;
      await renderStatus();
    }
  }
  polling = false;
}

function autoGrow() {
  const box = $("prompt");
  box.style.height = "auto";
  box.style.height = `${Math.min(box.scrollHeight, 160)}px`;
}

const guard = (handler) => (event) => {
  event?.preventDefault?.();
  handler(event).catch((cause) => error(cause.message || String(cause)));
};

$("composer").addEventListener("submit", guard(() => sendPrompt()));
$("prompt").addEventListener("input", autoGrow);
// Site simgesi yüklenemezse kırık resim yerine hiç gösterme.
$("tab-icon").addEventListener("error", () => { $("tab-icon").hidden = true; });
$("prompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) guard(() => sendPrompt())(event);
});
document.querySelectorAll(".suggestion").forEach((button) =>
  button.addEventListener("click", guard(() => sendPrompt(button.dataset.prompt))));
$("cancel").addEventListener("click", guard(cancel));
$("new-chat").addEventListener("click", guard(async () => { error(); await saveThread({ ...thread, mesajlar: [], soru: null }); }));
$("open-settings").addEventListener("click", () => {
  const sheet = $("settings");
  if (typeof sheet.showModal === "function") sheet.showModal();
  else sheet.setAttribute("open", "");
});
$("connect").addEventListener("click", guard(connect));
$("reload-extension").addEventListener("click", () => chrome.runtime.reload());
$("select-tab").addEventListener("click", guard(async () => { await selectActiveTab(); error(); await renderTab(); }));
$("grant-capture").addEventListener("click", guard(async () => {
  const allowed = await chrome.permissions.request({ origins: ["<all_urls>"] });
  if (!allowed) throw new Error("Chrome izni verilmedi.");
  error();
}));
$("disconnect").addEventListener("click", guard(async () => {
  try { await request("/disconnect"); } catch { /* Fusion zaten kapalı olabilir. */ }
  manual = null;
  await clearSelected();
  await renderStatus();
}));

chrome.storage.onChanged?.addListener((changes, area) => {
  if (area === "session" && changes.fusionAuto) void renderStatus();
});
chrome.tabs.onActivated?.addListener(() => void renderTab());
chrome.tabs.onUpdated?.addListener(() => void renderTab());
// Sayfadaki "Durdur" hapı (bkz. pageGlow.js) buraya ulaşır.
chrome.runtime.onMessage?.addListener((message) => {
  if (message?.type === "fusion.stop" && running()) void cancel().catch((cause) => error(cause.message));
});

await loadThread();
renderThread();
// Claude'daki gibi panel açılınca doğrudan yazmaya başlanır.
$("prompt").focus();
await renderStatus();
await renderTab().catch(() => undefined);

// Panel her açılışta diskten yeni kodu yükler; arka plan hizmeti ve manifest ise
// ancak eklenti yenilenince güncellenir. Disk sürümü yüklü sürümden yeniyse ya da
// arka plan cevap vermiyorsa kullanıcıya tek adımı söyle.
const loaded = chrome.runtime.getManifest().version;
const onDisk = await fetch(chrome.runtime.getURL?.("manifest.json") ?? "manifest.json")
  .then((response) => response.json()).then((manifest) => manifest.version || loaded).catch(() => loaded);
const ping = chrome.runtime.sendMessage({ type: "fusion.ping" }).catch(() => null);
const cevap = await Promise.race([ping, new Promise((resolve) => setTimeout(() => resolve(null), 1500))]);
// Eklenti kendini yenileyebilir: kullanıcıyı chrome://extensions sayfasına yollamaya gerek yok.
const outdated = onDisk !== loaded || !cevap?.surum;
$("update").hidden = !outdated;
if (outdated) await autoUpdate(onDisk);
