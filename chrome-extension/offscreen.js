// Fusion ile uzun yoklama bağlantısı. Chrome API'lerini doğrudan kullanamaz;
// komutları arka plan hizmetine iletir, sonucu Fusion'a geri yollar.
import { handleRecord } from "./recorder.js";
import { PROGRESS_REQUEST_TIMEOUT_MS } from "./permissionWait.js";
import { TASK_SCOPE_VERSION } from "./taskScope.js";

const RETRY_MS = 5000;
let connection = null;
/** Bu tarayıcının köprüdeki kimliği (#432); her komut isteğiyle gider. */
let device = null;
/** İnsan izni yalnız şu anda yürüyen komuta ait olabilir. */
let activeCommandId = null;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function report(status) {
  try { await chrome.runtime.sendMessage({ type: "fusion.status", status }); } catch { /* yok say */ }
}

async function request(path, data) {
  const response = await fetch(`http://127.0.0.1:${connection.port}${path}`, {
    method: path === "/status" ? "GET" : "POST",
    signal: path === "/progress" ? AbortSignal.timeout(PROGRESS_REQUEST_TIMEOUT_MS) : undefined,
    headers: { Authorization: `Bearer ${connection.token}`, "Content-Type": "application/json" },
    body: path === "/status" ? undefined : JSON.stringify({ ...(data || {}), ...(device ? { cihaz: device } : {}) }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.hata || `Fusion yanıtı: ${response.status}`);
  return result;
}

async function pair() {
  const answer = await chrome.runtime.sendMessage({ type: "fusion.pair" });
  if (!answer?.ok) return null;
  connection = { port: answer.port, token: answer.anahtar };
  device = await chrome.runtime.sendMessage({ type: "fusion.device" }).catch(() => null);
  await request("/status");
  await report({ bagli: true, port: connection.port, token: connection.token });
  return connection;
}

/** Ekran kaydı kareleri bu belgede toplanır (hizmet çalışanı boşta durdurulur, bu belge yaşar). */
async function captureWindow(windowId) {
  const answer = await chrome.runtime.sendMessage({ type: "fusion.captureVisibleTab", windowId });
  if (!answer?.ok) throw new Error(answer?.error || "Kare alınamadı.");
  return answer.image;
}

async function recordTarget() {
  const answer = await chrome.runtime.sendMessage({ type: "fusion.exec", command: { id: activeCommandId, islem: "record_target", veri: {} } });
  if (!answer?.ok) throw new Error(answer?.hata || "Kaydedilecek sekme bulunamadı.");
  return answer.veri;
}

/** Her kareden önce: kaydedilen sekme hâlâ etkin ve izinli mi (bkz. core.js record_check). */
async function recordCheck(target) {
  const command = { id: activeCommandId, islem: "record_check", veri: { tabId: target.tabId, windowId: target.windowId } };
  const answer = await chrome.runtime.sendMessage({ type: "fusion.exec", command }).catch(() => null);
  if (!answer?.ok) return { ok: false, reason: answer?.hata || "sekme denetlenemedi" };
  return answer.veri;
}

async function run(command) {
  if (command.islem === "record" && !("taskScope" in command)) {
    try { return { ok: true, veri: await handleRecord(command.veri || {}, captureWindow, recordTarget, recordCheck) }; } catch (cause) {
      return { ok: false, hata: String(cause?.message || cause) };
    }
  }
  return chrome.runtime.sendMessage({ type: "fusion.exec", command });
}

async function loop() {
  for (;;) {
    try {
      if (!connection && !await pair()) { await report({ bagli: false }); await sleep(RETRY_MS); continue; }
      const capability = await chrome.runtime.sendMessage({type: "fusion.taskScopeCapability"}).catch(() => null);
      const command = await request("/poll", {taskScopeVersion: capability?.version === TASK_SCOPE_VERSION ? TASK_SCOPE_VERSION : null});
      if (!command.id) continue;
      activeCommandId = command.id;
      try {
        const reply = await run(command);
        await request("/result", { id: command.id, ...(reply || { ok: false, hata: "Yanıt yok." }) });
      } finally { activeCommandId = null; }
    } catch {
      // Fusion kapandı ya da yeni köprü açıldı (anahtar değişti): yeniden eşleş.
      connection = null;
      await report({ bagli: false });
      await sleep(RETRY_MS);
    }
  }
}

/** Bekleyen izin uzantıdaki aktif komutla ve sunucudaki cihazla birlikte doğrulanır. */
chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  if (message?.type !== "fusion.permissionProgress") return false;
  if (!activeCommandId || message.progress?.id !== activeCommandId) {
    reply({ok: false, aktif: false});
    return false;
  }
  request("/progress", message.progress).then(reply).catch(() => reply({ok: false, aktif: false, baglanti_hatasi: true}));
  return true;
});

/** Eklenti dosyaları diskte güncellendiyse (Fusion güncellemesi) arka plana söyle. */
const UPDATE_CHECK_MS = 60000;
async function checkUpdate() {
  try {
    const response = await fetch(chrome.runtime.getURL("manifest.json"), { cache: "no-store" });
    const onDisk = (await response.json()).version;
    if (onDisk && onDisk !== chrome.runtime.getManifest().version) {
      await chrome.runtime.sendMessage({ type: "fusion.update" });
    }
  } catch { /* Denetim bir sonraki aralıkta yinelenir. */ }
}
setInterval(() => void checkUpdate(), UPDATE_CHECK_MS);

void loop();
