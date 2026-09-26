// Fusion ile uzun yoklama bağlantısı. Chrome API'lerini doğrudan kullanamaz;
// komutları arka plan hizmetine iletir, sonucu Fusion'a geri yollar.
const RETRY_MS = 5000;
let connection = null;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function report(status) {
  try { await chrome.runtime.sendMessage({ type: "fusion.status", status }); } catch { /* yok say */ }
}

async function request(path, data) {
  const response = await fetch(`http://127.0.0.1:${connection.port}${path}`, {
    method: path === "/status" ? "GET" : "POST",
    headers: { Authorization: `Bearer ${connection.token}`, "Content-Type": "application/json" },
    body: path === "/status" ? undefined : JSON.stringify(data || {}),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.hata || `Fusion yanıtı: ${response.status}`);
  return result;
}

async function pair() {
  const answer = await chrome.runtime.sendMessage({ type: "fusion.pair" });
  if (!answer?.ok) return null;
  connection = { port: answer.port, token: answer.anahtar };
  await request("/status");
  await report({ bagli: true, port: connection.port, token: connection.token });
  return connection;
}

async function loop() {
  for (;;) {
    try {
      if (!connection && !await pair()) { await report({ bagli: false }); await sleep(RETRY_MS); continue; }
      const command = await request("/poll");
      if (!command.id) continue;
      const reply = await chrome.runtime.sendMessage({ type: "fusion.exec", command });
      await request("/result", { id: command.id, ...(reply || { ok: false, hata: "Yanıt yok." }) });
    } catch {
      // Fusion kapandı ya da yeni köprü açıldı (anahtar değişti): yeniden eşleş.
      connection = null;
      await report({ bagli: false });
      await sleep(RETRY_MS);
    }
  }
}

void loop();
