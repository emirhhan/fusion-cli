// Fusion yan paneli: Claude in Chrome gibi küçük bir sohbet uygulaması.
// Kullanıcı görevi yazar; Fusion sayfayı okur, kaydırır, tıklar ve her adımı
// burada canlı gösterir. İzin ve sorular panelin içinde kart olarak çıkar.

import { clearSelected, execute, selectActiveTab } from "./core.js";
import { setGlow } from "./pageGlow.js";
import { MONITOR_KEY, PERMISSION_KEY, SHORTCUTS_KEY, monitorEnabled } from "./core.js";
import { controlSummary, renderAsk, renderMessage, renderShortcuts, renderSites } from "./panelView.js";
import { handleRecord } from "./recorder.js";
import { SHORTCUT_NAME, expandShortcut as expandShortcutText } from "./shortcuts.js";

const $ = (id) => document.getElementById(id);
const THREAD_KEY = "fusionThread";
/** Panel oturumunda saklanan mesaj sayısı; eski sohbet görünümü şişirmesin. */
const MAX_MESSAGES = 60;
/** Akış koparsa yeniden deneme aralığı. */
const RETRY_MS = 2000;
const MAX_RETRY_MS = 60_000;

// Elle eşleştirme bağlantısı; otomatik bağlantı arka plandaki belgede yaşar.
let manual = null;
let polling = false;
let listening = false;
let listenFailures = 0;
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
  $("model").disabled = busy;
  renderControl();
  if (thread.soru) renderAsk($("ask"), thread.soru, answer);
  else { $("ask").hidden = true; $("ask").replaceChildren(); }
  $("thread").scrollTop = $("thread").scrollHeight;
}

/** Mod seçimine göre "güvenli mi" satırı: kullanıcı hangi işlemin sorulduğunu görür. */
/** Panelin Claude in Chrome modları (#434): Manually approve, Automatically approve, Skip all approvals. */
const PANEL_MODES = ["security", "auto", "bypass"];

const GUARD_TEXT = {
  auto: "Gönderme ve silme sana sorulur; satın alma ve hesap oluşturma hiç yapılmaz.",
  security: "Her tıklama ve yazma önce sana sorulur.",
  edits: "Yazma ve sıradan tıklamalar sorulmaz; tanınmayan işlem sorulur.",
  plan: "Yalnız okur; tıklamaz, yazmaz.",
  bypass: "Dikkat: neredeyse hiçbir şey sorulmaz (yetki verme ve hassas bilgi hariç).",
};

function renderControl() {
  const last = [...thread.mesajlar].reverse().find((message) => message.rol === "asistan");
  const summary = controlSummary(last);
  const panel = $("control");
  panel.hidden = !summary.used && !running();
  panel.dataset.running = String(running());
  for (const item of panel.querySelectorAll("[data-channel]")) {
    const id = item.dataset.channel;
    item.dataset.active = String(summary.active === id);
    item.dataset.used = String(summary.counts[id] > 0);
    item.lastElementChild.textContent = String(summary.counts[id]);
  }
  $("control-last").textContent = summary.last ? `Son: ${summary.last}` : "";
  const mode = $("mode").value || "auto";
  $("control-guard").textContent = GUARD_TEXT[mode] || GUARD_TEXT.auto;
  $("control-guard").dataset.mode = mode;
}

// --- Site izni (Claude eklentisi gibi: ilk kullanımda tek tık, geri alınabilir) ---

/** Sabit izinler (yerel köprü, tüm siteler/ekran görüntüsü) site listesinde görünmez. */
const FIXED_ORIGINS = new Set(["http://127.0.0.1/*", "<all_urls>", "https://*/*", "http://*/*"]);

async function renderPermission() {
  const pending = (await chrome.storage.session.get(PERMISSION_KEY))[PERMISSION_KEY];
  const card = $("perm");
  card.hidden = !pending;
  if (pending) {
    $("perm-title").textContent = `Fusion ${new URL(pending.origin).hostname} sitesine girmek istiyor`;
    card.dataset.origin = pending.origin;
  }
}

async function renderSiteList() {
  const all = (await chrome.permissions.getAll?.())?.origins || [];
  renderSites($("sites"), $("sites-empty"), all.filter((origin) => !FIXED_ORIGINS.has(origin)), async (origin) => {
    await chrome.permissions.remove({ origins: [origin] });
    await renderSiteList();
    await renderTab();
  });
}

async function renderStatus() {
  const auto = await autoStatus();
  const bagli = Boolean(manual) || auto.bagli;
  $("status").dataset.state = bagli ? "online" : "offline";
  $("status").lastChild.textContent = bagli ? "Bağlı" : "Bağlı değil";
  $("pairing").hidden = auto.bagli && !manual;
  if (bagli) {
    void listen();
    loadSettings().catch(() => undefined);
  }
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
      : { arac: item.arac, metin: item.metin, durum: item.durum, hata: item.hata, kanal: item.kanal, ayrinti: item.ayrinti };
    return withLastAssistant((last) => ({ adimlar: [...(last.adimlar || []), step], etiket: step.metin || "Çalışıyor…" }));
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
      listenFailures = 0; // bağlantı döndü: bekleme ve hata metni sıfırlanır
      let next = thread;
      for (const item of result.olaylar || []) {
        thread = next;
        next = { ...(await applyItem(item)), seq: item.seq };
      }
      await saveThread({ ...next, seq: result.son ?? next.seq });
    }
  } catch (cause) {
    // Kopuk bağlantıda her 2 sn'de hata yazıp sonsuz denemek yerine üstel bekleme (en çok 1 dk);
    // hata metni yalnız ilk kopuşta yazılır.
    if (listenFailures === 0) error(`Fusion bağlantısı koptu: ${cause.message || cause}`);
    const wait = Math.min(RETRY_MS * 2 ** listenFailures, MAX_RETRY_MS);
    listenFailures += 1;
    await new Promise((resolve) => setTimeout(resolve, wait));
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
  // Fonksiyon şimdi yakalanır: zamanlayıcı çalıştığında sayfa kapanıyor olabilir.
  const reload = chrome.runtime.reload.bind(chrome.runtime);
  setTimeout(reload, AUTO_UPDATE_DELAY_MS);
}

// --- Model ve izin kipi (Claude'daki model seçici ve izin kipleri) ----------------

function renderSettings(settings) {
  if (!settings?.ok) return;
  // Eski kayıtlı kipler (edits/plan) üç moddan birine gösterilir; Manuel en sıkı karşılıktır (#434).
  const mode = PANEL_MODES.includes(settings.mod) ? settings.mod : settings.mod ? "security" : "auto";
  const chip = $("mode");
  chip.value = mode;
  chip.dataset.mode = mode;
  chip.title = chip.selectedOptions[0]?.title || mode;
  renderControl();
  const select = $("model");
  const rows = settings.modeller || [];
  select.replaceChildren(...rows.map((row) => {
    const option = document.createElement("option");
    option.value = `${row.kaynak}|${row.model}`;
    option.textContent = row.etiket || row.model;
    option.selected = row.model === settings.model;
    return option;
  }));
  if (!rows.some((row) => row.model === settings.model)) {
    const current = document.createElement("option");
    current.value = "";
    current.textContent = String(settings.model || "Model").split("/").pop();
    current.selected = true;
    select.prepend(current);
  }
}

async function loadSettings(change = {}) {
  const settings = await request("/settings", change);
  if (settings.ok === false) throw new Error(settings.metin || "Ayar değiştirilemedi.");
  renderSettings(settings);
}

// --- Eylemler -----------------------------------------------------------------

async function sendPrompt(text) {
  const typed = (text ?? $("prompt").value).trim();
  if (!typed || running()) return;
  const prompt = await expandShortcut(typed);
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
      try { reply = { id: command.id, ok: true, veri: await runManual(command) }; } catch (cause) {
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

/** Elle bağlantıda ekran kaydı kareleri panelde toplanır (bkz. recorder.js). */
function runManual(command) {
  if (command.islem !== "record") return execute(command);
  return handleRecord(
    command.veri || {},
    (windowId) => chrome.tabs.captureVisibleTab(windowId, { format: "jpeg", quality: 65 }),
    () => execute({ islem: "record_target", veri: {} }),
    (target) => execute({ islem: "record_check", veri: { tabId: target.tabId, windowId: target.windowId } })
      .catch((cause) => ({ ok: false, reason: String(cause?.message || cause) })),
  );
}

// --- Kısayollar (Claude in Chrome shortcuts gibi: kayıtlı görev, "/ad" ile çağrılır) ---

async function loadShortcuts() {
  const stored = (await chrome.storage.local.get(SHORTCUTS_KEY))[SHORTCUTS_KEY];
  return Array.isArray(stored) ? stored.filter((item) => item && item.ad && item.metin) : [];
}

async function saveShortcuts(list) {
  await chrome.storage.local.set({ [SHORTCUTS_KEY]: list });
  await renderShortcutList();
}

async function renderShortcutList() {
  const list = await loadShortcuts();
  renderShortcuts($("shortcuts"), $("shortcuts-empty"), list, async (ad) => {
    await saveShortcuts(list.filter((item) => item.ad !== ad));
  });
}

/** `/ad kalan metin` → kayıtlı görev (+ kalan metin); kısayol değilse metin olduğu gibi gider
 * (bkz. shortcuts.js). Yalnız "/ad" yazılmış ve o ad yoksa yazım hatası olabilir: sorulur. */
async function expandShortcut(prompt) {
  if (!prompt.startsWith("/")) return prompt;
  const list = await loadShortcuts();
  const result = expandShortcutText(prompt, list);
  if (result.unknown) {
    const names = list.map((item) => `/${item.ad}`).join(", ");
    throw new Error(`“/${result.unknown}” adlı kısayol yok. Kısayollar: ${names}. Metni göndermek için başına boşluk koy.`);
  }
  return result.prompt;
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
const BYPASS_CONFIRM_TEXT =
  "\"İzinleri atla\" kipinde Fusion gönderme ve silmeyi sormaz. Satın alma, hesap " +
  "oluşturma ve CAPTCHA her kipte yasaktır; yetki verme ve hassas bilgi girme yine sorulur. " +
  "Açılsın mı?";
$("mode").addEventListener("change", guard(async () => {
  const mod = $("mode").value;
  if (mod !== "bypass") return loadSettings({ mod });
  // Sormadan çalışan kip yanlışlıkla açılmasın: onay verilmezse seçim eski kipe döner.
  if (window.confirm(BYPASS_CONFIRM_TEXT)) return loadSettings({ mod, bypass_onay: true });
  return loadSettings();
}));
$("model").addEventListener("change", guard(async () => {
  const [kaynak, model] = $("model").value.split("|");
  if (kaynak && model) await loadSettings({ kaynak, model });
}));
$("new-chat").addEventListener("click", guard(async () => {
  error();
  // Fusion'daki panel konuşmasını da sıfırla (uygulamanın sohbetleri etkilenmez).
  if (await connection()) await request("/settings", { yeni: true });
  await saveThread({ ...thread, mesajlar: [], soru: null });
}));
$("open-settings").addEventListener("click", () => {
  void renderSiteList();
  void renderShortcutList();
  void monitorEnabled().then((enabled) => { $("monitor-toggle").checked = enabled; });
  // Son görev kısayol adayıdır: alan boşsa onunla doldurulur.
  const lastPrompt = [...thread.mesajlar].reverse().find((message) => message.rol === "kullanici")?.metin;
  if (lastPrompt && !$("shortcut-text").value) $("shortcut-text").value = lastPrompt;
  const sheet = $("settings");
  if (typeof sheet.showModal === "function") sheet.showModal();
  else sheet.setAttribute("open", "");
});
$("connect").addEventListener("click", guard(connect));
$("reload-extension").addEventListener("click", () => chrome.runtime.reload());
$("perm-allow").addEventListener("click", guard(async () => {
  const origin = $("perm").dataset.origin;
  // Tıklama kullanıcı hareketidir: Chrome izin penceresini ancak böyle açar.
  if (origin && await chrome.permissions.request({ origins: [`${origin}/*`] })) {
    await chrome.storage.session.remove(PERMISSION_KEY);
  }
  await renderPermission();
  await renderTab();
}));
$("perm-all").addEventListener("click", guard(async () => {
  // Ekran görüntüsü izniyle aynı kapsam: tüm siteler. Riskli adımlar yine onay ister.
  if (await chrome.permissions.request({ origins: ["<all_urls>"] })) {
    await chrome.storage.session.remove(PERMISSION_KEY);
  }
  await renderPermission();
  await renderTab();
}));
$("perm-deny").addEventListener("click", guard(async () => {
  await chrome.storage.session.remove(PERMISSION_KEY);
  await renderPermission();
}));
chrome.storage.onChanged?.addListener((changes, area) => {
  if (area === "session" && PERMISSION_KEY in changes) void renderPermission();
});

$("select-tab").addEventListener("click", guard(async () => { await selectActiveTab(); error(); await renderTab(); }));
$("grant-capture").addEventListener("click", guard(async () => {
  const allowed = await chrome.permissions.request({ origins: ["<all_urls>"] });
  if (!allowed) throw new Error("Chrome izni verilmedi.");
  error();
}));
$("monitor-toggle").addEventListener("change", guard(async () => {
  await chrome.storage.local.set({ [MONITOR_KEY]: $("monitor-toggle").checked });
}));
$("shortcut-form").addEventListener("submit", guard(async () => {
  const ad = $("shortcut-name").value.trim().replace(/^\//, "");
  const metin = $("shortcut-text").value.trim();
  if (!SHORTCUT_NAME.test(ad)) throw new Error("Kısayol adı boşluksuz, en çok 40 karakter olmalı (ör. ozet).");
  if (!metin) throw new Error("Kısayolun görev metnini yaz.");
  const others = (await loadShortcuts()).filter((item) => item.ad.toLocaleLowerCase("tr") !== ad.toLocaleLowerCase("tr"));
  await saveShortcuts([...others, { ad, metin }]);
  $("shortcut-name").value = "";
  $("shortcut-text").value = "";
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
await renderPermission().catch(() => undefined);

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
