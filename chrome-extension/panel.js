import { clearSelected, execute, getSelected, selectActiveTab } from "./core.js";

const $ = (id) => document.getElementById(id);
// Elle eşleştirme bağlantısı; otomatik bağlantı arka plandaki belgede yaşar.
let manual = null;
let polling = false;

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
  if (!conn) throw new Error("Fusion bağlantısı yok.");
  const response = await fetch(`http://127.0.0.1:${conn.port}${path}`, {
    method: path === "/status" ? "GET" : "POST",
    headers: { Authorization: `Bearer ${conn.token}`, "Content-Type": "application/json" },
    body: path === "/status" ? undefined : JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.hata || `Fusion yanıtı: ${response.status}`);
  return result;
}

async function render() {
  const auto = await autoStatus();
  const bagli = Boolean(manual) || auto.bagli;
  $("pairing").hidden = bagli;
  $("session").hidden = !bagli;
  $("status").dataset.state = bagli ? "online" : "offline";
  $("status").lastChild.textContent = auto.bagli && !manual ? "Otomatik bağlı" : bagli ? "Bağlı" : "Bağlı değil";
  const selected = await getSelected();
  $("tab-label").textContent = selected ? `${selected.title} — ${selected.origin}`
    : "Sekme seçilmedi — Fusion izinli sitelerde sekmeyi kendisi açabilir.";
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
  await render();
  void poll();
}

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
      await render();
    }
  }
  polling = false;
}

async function sendPrompt() {
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  $("send").disabled = true;
  $("cancel").hidden = false;
  $("response").textContent = "Fusion çalışıyor…";
  try {
    const result = await request("/turn", { prompt });
    $("response").textContent = result.metin || JSON.stringify(result);
    if (result.ok) $("prompt").value = "";
  } finally {
    $("send").disabled = false;
    $("cancel").hidden = true;
  }
}

for (const [id, handler] of [
  ["connect", connect],
  ["select-tab", async () => { await selectActiveTab(); error(); await render(); }],
  ["send", sendPrompt],
  ["grant-capture", async () => {
    const allowed = await chrome.permissions.request({ origins: ["<all_urls>"] });
    if (!allowed) throw new Error("Chrome izni verilmedi.");
    $("capture-permission").open = false;
    error();
  }],
  ["cancel", async () => {
    $("cancel").disabled = true;
    try {
      const result = await request("/cancel");
      $("response").textContent = result.metin || "Görev durduruluyor…";
    } finally {
      $("cancel").disabled = false;
    }
  }],
  ["read-tab", async () => {
    const data = await execute({ islem: "snapshot", veri: {} });
    error();
    $("snapshot").hidden = false;
    $("snapshot").textContent = `${data.title}\n${data.url}\n\n${data.text}`;
  }],
  ["disconnect", async () => {
    try { await request("/disconnect"); } catch { /* Fusion zaten kapalı olabilir. */ }
    manual = null;
    await clearSelected();
    await render();
  }],
]) {
  $(id).addEventListener("click", () => handler().catch((cause) => error(cause.message || String(cause))));
}

chrome.storage.onChanged?.addListener((changes, area) => {
  if (area === "session" && (changes.fusionAuto || changes.fusionTab)) void render();
});
await render();

// Panel her açılışta diskten yeni kodu yükler, arka plan hizmeti ise ancak eklenti
// yenilenince güncellenir. Eski arka plan otomatik bağlantıyı bilmez: kullanıcıya söyle.
const ping = chrome.runtime.sendMessage({ type: "fusion.ping" }).catch(() => null);
const cevap = await Promise.race([ping, new Promise((resolve) => setTimeout(() => resolve(null), 1500))]);
if (cevap?.surum !== chrome.runtime.getManifest().version) {
  error("Otomatik bağlantı için chrome://extensions sayfasında Fusion Browser'ı yenileyin (⟳).");
}
