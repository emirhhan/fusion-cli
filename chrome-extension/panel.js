const $ = (id) => document.getElementById(id);
let connection = null;
let selected = null;
let polling = false;

function error(message = "") { $("error").textContent = message; }
function status(message) { $("status").textContent = message; }

async function request(path, data = {}, signal) {
  if (!connection) throw new Error("Fusion bağlantısı yok.");
  const response = await fetch(`http://127.0.0.1:${connection.port}${path}`, {
    method: path === "/status" ? "GET" : "POST",
    headers: {
      "Authorization": `Bearer ${connection.token}`,
      "Content-Type": "application/json",
    },
    body: path === "/status" ? undefined : JSON.stringify(data),
    signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.hata || `Fusion yanıtı: ${response.status}`);
  return result;
}

function showConnected() {
  $("pairing").hidden = Boolean(connection);
  $("session").hidden = !connection;
  status(connection ? "Bağlı" : "Bağlı değil");
  $("status").dataset.state = connection ? "online" : "offline";
}

async function connect() {
  const port = Number($("port").value);
  const token = $("token").value.trim();
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !token) {
    throw new Error("Fusion portunu ve eşleştirme anahtarını girin.");
  }
  connection = { port, token };
  try {
    await request("/status");
  } catch (cause) {
    connection = null;
    throw cause;
  }
  await chrome.storage.session.set({ fusionConnection: connection });
  error();
  showConnected();
  poll();
}

async function selectTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) throw new Error("Açık web sekmesi bulunamadı.");
  const url = new URL(tab.url);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("Yalnız HTTP ve HTTPS sayfaları bağlanabilir.");
  }
  const pattern = `${url.origin}/*`;
  const allowed = await chrome.permissions.request({ origins: [pattern] });
  if (!allowed) throw new Error("Bu site için Chrome izni verilmedi.");
  selected = { id: tab.id, origin: url.origin };
  $("tab-label").textContent = `${tab.title || url.hostname} — ${url.origin}`;
  await chrome.storage.session.set({ fusionTab: selected });
  error();
}

async function checkedTab() {
  if (!selected) throw new Error("Önce 'Bu sekmeye izin ver' düğmesini kullanın.");
  const tab = await chrome.tabs.get(selected.id);
  if (!tab?.url || new URL(tab.url).origin !== selected.origin) {
    selected = null;
    await chrome.storage.session.remove("fusionTab");
    throw new Error("Sekme başka siteye geçti. Yeni site için tekrar izin verin.");
  }
  if (!await chrome.permissions.contains({ origins: [`${selected.origin}/*`] })) {
    throw new Error("Chrome site izni kaldırıldı.");
  }
  return tab;
}

function pageAction(operation, args) {
  const visible = [...document.querySelectorAll(
    "button, a[href], input, textarea, select, [role='button'], [contenteditable='true']"
  )].filter((el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && !el.closest("[aria-hidden='true']");
  }).slice(0, 160);
  const safe = (el) => {
    const type = (el.getAttribute("type") || "").toLowerCase();
    const hint = [
      el.getAttribute("name"), el.getAttribute("id"), el.getAttribute("autocomplete"),
      el.getAttribute("aria-label"), el.getAttribute("placeholder"),
    ]
      .filter(Boolean).join(" ").toLowerCase();
    return type !== "password" && !/(password|passwd|otp|one.time|credit.card|cc.number|cvv|cvc)/.test(hint);
  };
  if (operation === "snapshot") {
    globalThis.__fusionRefs = visible;
    return {
      title: document.title,
      url: location.href,
      text: (document.body?.innerText || "").slice(0, 12000),
      elements: visible.map((el, index) => ({
        ref: `e${index}`,
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || "",
        name: (el.getAttribute("aria-label") || el.innerText ||
          el.getAttribute("placeholder") || el.getAttribute("name") || "").trim().slice(0, 120),
        disabled: el.disabled || false,
        writable: safe(el) && (el.matches("input, textarea, select, [contenteditable='true']")),
      })).filter((item, index) => safe(visible[index])),
    };
  }
  const index = /^e(\d+)$/.exec(args.ref || "");
  const element = index ? globalThis.__fusionRefs?.[Number(index[1])] : null;
  if (!element || !element.isConnected || !safe(element)) {
    throw new Error("Öğe artık bulunamadı veya hassas alan. Sayfayı yeniden okuyun.");
  }
  if (operation === "click") {
    element.click();
    return { clicked: args.ref, url: location.href };
  }
  if (operation === "type") {
    if (!element.matches("input, textarea, select, [contenteditable='true']")) {
      throw new Error("Bu öğeye metin yazılamaz.");
    }
    if (element.matches("select")) throw new Error("Seçim kutusu için tıklama kullanın.");
    element.focus();
    if (element.isContentEditable) element.textContent = args.text;
    else element.value = args.text;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    return { typed: args.ref, length: args.text.length };
  }
  throw new Error("Desteklenmeyen sayfa eylemi.");
}

async function execute(command) {
  const tab = await checkedTab();
  if (command.islem === "screenshot") {
    const [active] = await chrome.tabs.query({ active: true, windowId: tab.windowId });
    if (active?.id !== tab.id) throw new Error("Görüntü için izinli sekmeyi öne getirin.");
    const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 65 });
    if (image.length > 4_000_000) throw new Error("Ekran görüntüsü çok büyük.");
    return { image };
  }
  if (command.islem === "navigate") {
    const destination = new URL(command.veri.url);
    if (destination.origin !== selected.origin) {
      throw new Error("Yeni site için panelden tekrar izin verin.");
    }
    await chrome.tabs.update(tab.id, { url: destination.href });
    return { url: destination.href };
  }
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: pageAction,
    args: [command.islem, command.veri],
  });
  return result;
}

async function poll() {
  if (polling) return;
  polling = true;
  while (connection) {
    try {
      const command = await request("/poll");
      if (!command.id) continue;
      let reply;
      try {
        reply = { id: command.id, ok: true, veri: await execute(command) };
      } catch (cause) {
        reply = { id: command.id, ok: false, hata: String(cause.message || cause) };
      }
      await request("/result", reply);
    } catch (cause) {
      error(`Chrome bağlantısı: ${cause.message || cause}`);
      connection = null;
      showConnected();
    }
  }
  polling = false;
}

async function sendPrompt() {
  await checkedTab();
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
  ["connect", connect], ["select-tab", selectTab], ["send", sendPrompt],
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
    connection = null;
    selected = null;
    await chrome.storage.session.clear();
    showConnected();
  }],
]) {
  $(id).addEventListener("click", () => handler().catch((cause) => error(cause.message || String(cause))));
}

const saved = await chrome.storage.session.get(["fusionConnection", "fusionTab"]);
if (saved.fusionConnection) {
  connection = saved.fusionConnection;
  $("port").value = String(connection.port);
  $("token").value = connection.token;
  selected = saved.fusionTab || null;
  if (selected) $("tab-label").textContent = `İzinli sekme: ${selected.origin}`;
  try {
    await request("/status");
    showConnected();
    poll();
  } catch {
    connection = null;
    showConnected();
  }
}
