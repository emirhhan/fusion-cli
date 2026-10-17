import { importKey, sign } from "./signing.js";

const $ = (id) => document.getElementById(id);
const DB = "fusion-uzak";
let device = null; // { deviceId, key }
let lastSeq = 0;
let polling = null;

// ---- kalıcı depo: IndexedDB (CryptoKey doğrudan saklanabilir, dışa aktarılamaz) ----
function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("kv");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function kv(mode, key, value) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const store = db.transaction("kv", mode === "get" ? "readonly" : "readwrite").objectStore("kv");
    const op = mode === "get" ? store.get(key) : mode === "put" ? store.put(value, key) : store.delete(key);
    op.onsuccess = () => resolve(op.result);
    op.onerror = () => reject(op.error);
  });
}

function say(text, cls = "") {
  const el = $("durum");
  el.textContent = text;
  el.className = `mut ${cls}`;
}

async function postJson(path, payload) {
  const response = await fetch(path, { method: "POST", body: JSON.stringify(payload) });
  return { status: response.status, body: await response.json() };
}

async function rpc(method, params = {}) {
  lastSeq = Math.max(lastSeq + 1, Date.now());
  const body = new TextEncoder().encode(JSON.stringify({ method, params }));
  const timestamp = Math.floor(Date.now() / 1000);
  const nonce = crypto.randomUUID();
  const signature = await sign(device.key, "POST", "/v1/rpc", timestamp, nonce, lastSeq, body);
  const response = await fetch("/v1/rpc", {
    method: "POST",
    body,
    headers: {
      "x-fusion-device": device.deviceId,
      "x-fusion-ts": String(timestamp),
      "x-fusion-nonce": nonce,
      "x-fusion-seq": String(lastSeq),
      "x-fusion-sig": signature,
    },
  });
  if (response.status === 401) throw Object.assign(new Error("Eşleşme geçersiz"), { auth: true });
  if (response.status === 429) throw new Error("Çok fazla deneme; biraz bekle.");
  return response.json();
}

// ---- eşleştirme ----
async function pair() {
  const code = $("kod").value.trim().toUpperCase();
  if (!code) return;
  const submitted = await postJson("/v1/pair/submit", { code, deviceName: $("cihazAdi").value });
  if (submitted.status !== 200) return say(submitted.body.message || "Kod kabul edilmedi.", "err");
  say("Masaüstünde onayla…");
  for (let i = 0; i < 60; i += 1) {
    await new Promise((r) => setTimeout(r, 2000));
    const claimed = await postJson("/v1/pair/claim", { code });
    if (claimed.status !== 200) return say(claimed.body.message || "Eşleştirme başarısız.", "err");
    if (claimed.body.state === "onaylandi") {
      const key = await importKey(claimed.body.secret);
      await kv("put", "device", { deviceId: claimed.body.deviceId, key });
      device = { deviceId: claimed.body.deviceId, key };
      return start();
    }
  }
  say("Onay zaman aşımına uğradı.", "err");
}

// ---- görünüm (yalnız textContent: HTML enjeksiyonu yok) ----
function line(parent, text, cls = "") {
  const p = document.createElement("p");
  p.textContent = text;
  if (cls) p.className = cls;
  parent.appendChild(p);
  return p;
}

async function refresh() {
  const status = await rpc("service.status");
  $("uyari").textContent = status.data?.notice ?? "";
  const list = await rpc("tasks.list");
  const box = $("gorevler");
  box.replaceChildren();
  const approvals = $("onaylar");
  approvals.replaceChildren();
  for (const task of list.data?.tasks ?? []) {
    const card = document.createElement("div");
    card.className = "card";
    line(card, task.summary);
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = task.state;
    card.appendChild(pill);
    if (["queued", "running", "waiting_approval"].includes(task.state)) {
      const cancel = document.createElement("button");
      cancel.className = "sec";
      cancel.textContent = "İptal";
      cancel.onclick = async () => { await rpc("tasks.cancel", { runId: task.runId }); refresh(); };
      card.appendChild(cancel);
    }
    box.appendChild(card);
    if (task.state === "waiting_approval") await showApprovals(task.runId, approvals);
  }
  if (!approvals.hasChildNodes()) line(approvals, "Bekleyen onay yok.", "mut");
}

async function showApprovals(runId, container) {
  const events = await rpc("tasks.events", { runId });
  const pending = new Map();
  for (const event of events.data?.events ?? []) {
    if (event.kind === "approval_request") pending.set(event.payload.questionId, event.payload);
    if (event.kind === "approval_answered") pending.delete(event.payload.questionId);
  }
  for (const [questionId, q] of pending) {
    const card = document.createElement("div");
    card.className = "card";
    line(card, q.title || "Onay gerekiyor");
    if (q.target) line(card, q.target, "mut");
    if (q.stepUp) line(card, "Bu işlem güvenlik nedeniyle yalnız masaüstünde onaylanır.", "err");
    const row = document.createElement("div");
    row.className = "row";
    const answer = async (choice) => { await rpc("approvals.respond", { questionId, choice }); refresh(); };
    if (!q.stepUp) {
      const ok = document.createElement("button");
      ok.textContent = "Bir kez izin ver";
      ok.onclick = () => answer("once");
      row.appendChild(ok);
    }
    const no = document.createElement("button");
    no.className = "sec";
    no.textContent = "Reddet";
    no.onclick = () => answer("deny");
    row.appendChild(no);
    card.appendChild(row);
    container.appendChild(card);
  }
}

// ---- canlı ekran (JPEG kare akışı; WebRTC değil) ----
let screenLoop = null;
const SCREEN_FRAME_MS = 600;

function screenSay(text, cls = "") {
  const el = $("ekranDurum");
  el.textContent = text;
  el.className = `mut ${cls}`;
}

function screenShow(active) {
  $("ekranIste").hidden = active;
  $("ekranDur").hidden = !active;
  $("ekranKare").hidden = !active;
}

async function screenTick() {
  try {
    const status = await rpc("screen.status");
    const state = status.data?.state ?? "none";
    if (state === "pending") { screenShow(false); return screenSay("Bilgisayarda onay bekleniyor…"); }
    if (state !== "active") { screenShow(false); return screenSay("Ekran paylaşılmıyor."); }
    const frame = await rpc("screen.frame");
    if (frame.ok) {
      $("ekranKare").src = `data:image/jpeg;base64,${frame.data.jpegBase64}`;
      screenShow(true);
      screenSay(`Canlı · ${status.data.secondsLeft} sn kaldı`, "ok");
    } else if (frame.error !== "cok_sik") {
      screenShow(false);
      screenSay(frame.message || "Ekran alınamadı.", "err");
    }
  } catch (error) {
    if (error.auth) return;
    screenSay("Bilgisayara ulaşılamıyor.", "err");
  }
}

function screenStart() {
  clearInterval(screenLoop);
  screenLoop = setInterval(screenTick, SCREEN_FRAME_MS);
  void screenTick();
}

async function screenAsk() {
  const result = await rpc("screen.request");
  if (!result.ok) return screenSay(result.message || "İstek reddedildi.", "err");
  screenStart();
}

async function screenStop() {
  clearInterval(screenLoop);
  screenLoop = null;
  await rpc("screen.stop");
  screenShow(false);
  screenSay("Ekran paylaşımı durduruldu.");
}

async function send() {
  const text = $("gorev").value.trim();
  if (!text) return;
  await rpc("tasks.create", { prompt: text, idempotencyKey: crypto.randomUUID() });
  $("gorev").value = "";
  refresh();
}

async function unpair() {
  try { await rpc("devices.revoke", {}); } catch { /* sunucu zaten reddetmiş olabilir */ }
  await kv("delete", "device");
  location.reload();
}

async function start() {
  $("eslestir").hidden = true;
  $("ana").hidden = false;
  say("Bağlı", "ok");
  try { await refresh(); } catch (error) {
    if (error.auth) { await kv("delete", "device"); return location.reload(); }
    say(error.message, "err");
  }
  const status = await rpc("service.status");
  if ((status.data?.scopes ?? []).includes("desktop.observe")) {
    $("ekran").hidden = false;
    $("ekranIste").onclick = screenAsk;
    $("ekranDur").onclick = screenStop;
    screenSay("Ekran paylaşılmıyor.");
  }
  clearInterval(polling);
  polling = setInterval(() => refresh().catch(() => say("Bilgisayara ulaşılamıyor.", "err")), 4000);
}

async function main() {
  if (!crypto?.subtle) {
    say("Bu sayfa güvenli bağlantı (HTTPS veya localhost) ister; imza için gerekli.", "err");
    return;
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  $("eslestirDugme").onclick = pair;
  $("gonder").onclick = send;
  $("cikis").onclick = unpair;
  device = (await kv("get", "device")) ?? null;
  if (device) return start();
  $("eslestir").hidden = false;
  say("Eşleştirilmedi");
}
main();
