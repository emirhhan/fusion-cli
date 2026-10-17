import { approvalCard, pendingFromEvents } from "./approvals.js";
import { createApi, postJson } from "./api.js";
import { createChat } from "./chat.js";
import { ACTIVE_STATES, STATE_LABEL, h, icon, timeAgo } from "./dom.js";
import { createScreenStream } from "./screen-stream.js";
import { importKey } from "./signing.js";
import { kv } from "./store.js";

const $ = (id) => document.getElementById(id);
const POLL_MS = 4000;
const TABS = [
  { id: "sohbetler", label: "Sohbetler", icon: "chat" },
  { id: "gorevler", label: "Görevler", icon: "tasks" },
  { id: "onaylar", label: "Onaylar", icon: "approve" },
  { id: "ekran", label: "Ekran", icon: "screen", scope: "desktop.observe" },
  { id: "ayarlar", label: "Ayarlar", icon: "settings" },
];

let device = null;
let rpc = null;
let tasks = [];
let scopes = [];
let current = "sohbetler";
let pollTimer = null;
let chat = null;
let stream = null;
let rendered = false;

function say(text, cls = "") {
  const el = $("durum");
  el.textContent = text;
  el.className = `muted ${cls}`;
}

function setConnection(ok, text) {
  $("nokta").className = `dot ${ok ? "ok" : "bad"}`;
  $("nokta").title = text;
  $("baglanti").textContent = ok ? "" : text;
}

// ---- eşleştirme ----
async function pair() {
  const code = $("kod").value.trim().toUpperCase();
  if (!code) return;
  const submitted = await postJson("/v1/pair/submit", { code, deviceName: $("cihazAdi").value });
  if (submitted.status !== 200) return say(submitted.body.message || "Kod kabul edilmedi.", "danger");
  say("Masaüstünde onayla…");
  for (let i = 0; i < 60; i += 1) {
    await new Promise((r) => setTimeout(r, 2000));
    const claimed = await postJson("/v1/pair/claim", { code });
    if (claimed.status !== 200) return say(claimed.body.message || "Eşleştirme başarısız.", "danger");
    if (claimed.body.state === "onaylandi") {
      const key = await importKey(claimed.body.secret);
      await kv("put", "device", { deviceId: claimed.body.deviceId, key });
      device = { deviceId: claimed.body.deviceId, key };
      return start();
    }
  }
  say("Onay zaman aşımına uğradı.", "danger");
}

// ---- sekmeler ----
function buildTabs() {
  const bar = $("sekmeler");
  bar.replaceChildren();
  for (const tab of TABS) {
    if (tab.scope && !scopes.includes(tab.scope)) continue;
    const badge = h("span", { class: "badge", id: `rozet-${tab.id}`, hidden: true });
    bar.append(
      h("button", { class: "tab", type: "button", role: "tab", "data-tab": tab.id, "aria-label": tab.label, onclick: () => show(tab.id) },
        h("span", { class: "tab-ico" }, icon(tab.icon), badge),
        h("span", { class: "tab-label" }, tab.label)),
    );
  }
}

function show(id) {
  if (current === "ekran" && id !== "ekran") stream?.detach();
  current = id;
  document.body.classList.remove("fullscreen");
  $("sohbet").hidden = true;
  document.body.classList.remove("in-chat");
  for (const view of document.querySelectorAll("[data-view]")) view.hidden = view.dataset.view !== id;
  for (const tab of document.querySelectorAll(".tab")) {
    const on = tab.dataset.tab === id;
    tab.classList.toggle("on", on);
    tab.setAttribute("aria-selected", String(on));
  }
  $("baslik").textContent = TABS.find((t) => t.id === id)?.label ?? "";
  $("yeni").hidden = id !== "sohbetler";
  if (id === "ekran") screenOpen();
  render();
}

function openChat(task) {
  chat.show(task);
  for (const view of document.querySelectorAll("[data-view]")) view.hidden = true;
  $("sohbet").hidden = false;
  document.body.classList.add("in-chat");
}

// ---- listeler ----
function taskRow(task) {
  const active = ACTIVE_STATES.includes(task.state);
  return h("button", { class: "row-item", type: "button", onclick: () => openChat(task) },
    h("span", { class: `avatar ${active ? "live" : ""}` }, icon("chat")),
    h("span", { class: "row-main" },
      h("span", { class: "row-title" }, task.summary || "(boş)"),
      h("span", { class: "row-sub" }, STATE_LABEL[task.state] ?? task.state)),
    h("span", { class: "row-time muted" }, timeAgo(task.createdAt)));
}

function renderTasks() {
  const chats = $("liste-sohbetler");
  chats.replaceChildren(...(tasks.length ? tasks.map(taskRow) : [h("p", { class: "empty" }, "Henüz sohbet yok. Sağ üstteki + ile başla.")]));
  const box = $("liste-gorevler");
  box.replaceChildren();
  const running = tasks.filter((t) => ACTIVE_STATES.includes(t.state));
  const finished = tasks.filter((t) => !ACTIVE_STATES.includes(t.state));
  const group = (name, items, cancellable) => {
    if (!items.length) return;
    box.append(h("h2", { class: "group" }, name));
    for (const task of items) {
      box.append(h("div", { class: "task" }, taskRow(task),
        cancellable ? h("button", { class: "btn ghost small", type: "button", onclick: async () => { await rpc("tasks.cancel", { runId: task.runId }); refresh(); } }, "İptal") : null));
    }
  };
  group("Çalışan", running, true);
  group("Biten", finished, false);
  if (!tasks.length) box.append(h("p", { class: "empty" }, "Görev yok."));
}

async function renderApprovals() {
  const box = $("liste-onaylar");
  const cards = [];
  for (const task of tasks.filter((t) => t.state === "waiting_approval")) {
    const events = await rpc("tasks.events", { runId: task.runId });
    for (const [, question] of pendingFromEvents(events.data?.events ?? [])) {
      cards.push(h("div", { class: "approval-wrap" }, h("div", { class: "muted small" }, task.summary), approvalCard(question, rpc, refresh)));
    }
  }
  box.replaceChildren(...(cards.length ? cards : [h("p", { class: "empty" }, "Bekleyen onay yok.")]));
  for (const id of ["onaylar"]) {
    const badge = $(`rozet-${id}`);
    if (badge) { badge.textContent = String(cards.length); badge.hidden = cards.length === 0; }
  }
}

function render() {
  renderTasks();
  if (current === "onaylar" || tasks.some((t) => t.state === "waiting_approval")) void renderApprovals().catch(() => {});
}

async function refresh(authOnly = false) {
  if (authOnly === true) return forget();
  try {
    const status = await rpc("service.status");
    const list = await rpc("tasks.list");
    const next = list.data?.tasks ?? [];
    const changed = JSON.stringify(next) !== JSON.stringify(tasks) || !rendered;
    tasks = next;
    rendered = true;
    $("uyari").textContent = status.data?.notice ?? "";
    setConnection(true, "");
    if (changed) render(); // aynı veriyle yeniden çizilmez: dokunuş ortasında düğüm kaybolmasın
  } catch (error) {
    if (error.auth) return forget();
    setConnection(false, "Bilgisayara ulaşılamıyor; yeniden deneniyor…");
  }
}

function schedule() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => { if (!document.hidden) await refresh(); schedule(); }, POLL_MS);
}

async function forget() {
  await kv("delete", "device");
  location.reload();
}

// ---- canlı ekran ----
const SCREEN_TEXT = {
  idle: "Ekran paylaşılmıyor.",
  pending: "Bilgisayarda onay bekleniyor…",
  live: "Canlı",
  paused: "Sayfa arka planda; duraklatıldı.",
  reconnecting: "Bağlantı koptu, yeniden deneniyor…",
  ended: "Oturum bitti.",
  stopped: "Ekran paylaşımı durduruldu.",
  auth: "Eşleşme geçersiz.",
};

function screenState({ state, message, renewed }) {
  const text = message || (renewed ? "Süre doldu; yeniden izin istendi, bilgisayarda onayla." : SCREEN_TEXT[state] ?? "");
  $("ekranDurum").textContent = text;
  $("ekranDurum").className = `chip ${state === "live" ? "ok" : state === "error" || state === "reconnecting" ? "bad" : ""}`;
  const watching = ["live", "pending", "paused", "reconnecting"].includes(state);
  $("ekranIste").hidden = watching;
  $("ekranDur").hidden = !watching;
  $("ekranKutu").classList.toggle("empty-screen", state !== "live" && !$("ekranKare").src);
  if (state === "auth") void forget();
}

function screenFrame(data) {
  $("ekranKare").src = `data:image/jpeg;base64,${data.jpegBase64}`;
  $("ekranKutu").classList.remove("empty-screen");
}

function screenOpen() {
  if (!stream) {
    stream = createScreenStream({ rpc, onFrame: screenFrame, onState: screenState });
    document.addEventListener("visibilitychange", () => stream.setVisible(!document.hidden));
    window.addEventListener("online", () => stream.setVisible(true));
  }
  void stream.start({ request: false });
}

// ---- açılış ----
async function start() {
  $("eslestir").hidden = true;
  $("uygulama").hidden = false;
  rpc = createApi(device);
  chat = createChat({
    rpc,
    root: $("sohbet"),
    onBack: () => show("sohbetler"),
    onCreated: (task) => { refresh(); openChat(task); },
    onChange: (authFailed) => (authFailed === true ? forget() : refresh()),
  });
  try {
    const status = await rpc("service.status");
    scopes = status.data?.scopes ?? [];
  } catch (error) {
    if (error.auth) return forget();
    setConnection(false, "Bilgisayara ulaşılamıyor; yeniden deneniyor…");
  }
  buildTabs();
  $("yeni").onclick = () => openChat(null);
  $("ekranIste").onclick = () => stream.start({ request: true });
  $("ekranDur").onclick = () => stream.stop();
  $("cikis").onclick = async () => {
    try { await rpc("devices.revoke", {}); } catch { /* sunucu zaten reddetmiş olabilir */ }
    await forget();
  };
  $("ekranKutu").onclick = () => document.body.classList.toggle("fullscreen");
  show("sohbetler");
  await refresh();
  schedule();
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  window.addEventListener("online", () => refresh());
}

async function main() {
  if (!crypto?.subtle) {
    say("Bu sayfa güvenli bağlantı (HTTPS veya localhost) ister; imza için gerekli.", "danger");
    return;
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  $("eslestirDugme").onclick = pair;
  device = (await kv("get", "device")) ?? null;
  if (device) return start();
  $("eslestir").hidden = false;
  say("Eşleştirilmedi");
}
main();
