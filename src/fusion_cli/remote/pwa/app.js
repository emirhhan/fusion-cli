import { approvalCard, pendingFromEvents } from "./approvals.js";
import { createApi, postJson } from "./api.js";
import { createChat, newChatId } from "./chat.js";
import { h, icon } from "./dom.js";
import { createScreenStream } from "./screen-stream.js";
import { importKey } from "./signing.js";
import { kv } from "./store.js";
import { renderChats } from "./views-chats.js";
import { renderSettings } from "./views-settings.js";
import { renderTasks } from "./views-tasks.js";

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
const ctx = {
  tasks: [], chats: [], projects: [], chatProjects: {}, schedules: [], kits: [], scopes: [],
  tiers: [], tiersEditable: false, activeTier: "", tier: localStorage.getItem("fusion.tier") ?? "",
  filter: "all", notice: "",
};
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
    if (claimed.body.state === "onaylandi") return finishPairing(claimed.body);
  }
  say("Onay zaman aşımına uğradı.", "danger");
}

async function finishPairing(body) {
  const key = await importKey(body.secret);
  await kv("put", "device", { deviceId: body.deviceId, key });
  device = { deviceId: body.deviceId, key };
  return start();
}

async function accountLogin() {
  const identifier = $("hesapKimlik").value.trim();
  const password = $("hesapParola").value;
  if (!identifier || !password) return say("Kullanıcı adı ve parola gerekli.", "danger");
  say("Giriş yapılıyor…");
  try {
    const result = await postJson("/v1/auth/login", { identifier, password, deviceName: $("cihazAdi").value });
    $("hesapParola").value = "";
    if (result.status !== 200) return say(result.body.message || "Giriş başarısız.", "danger");
    return await finishPairing(result.body);
  } catch {
    say("Bilgisayara ulaşılamıyor.", "danger");
  }
}

async function loadAuthOptions() {
  try {
    const result = await postJson("/v1/auth/options", {});
    $("hesapGiris").hidden = !result.body.accountLogin;
  } catch {
    $("hesapGiris").hidden = true;
  }
}

// ---- sekmeler ----
function buildTabs() {
  const bar = $("sekmeler");
  bar.replaceChildren();
  for (const tab of TABS) {
    if (tab.scope && !ctx.scopes.includes(tab.scope)) continue;
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

function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 3500);
}

function openChat(row) {
  const isNew = !row;
  chat.show(isNew
    ? { chatId: newChatId(), root: undefined, projectId: ctx.filter.startsWith("p_") ? ctx.filter : null, title: "Yeni sohbet", isNew: true }
    : { chatId: row.chatId, root: row.root, projectId: row.projectId, title: row.title, run: row.task && ["queued", "running", "waiting_approval", "paused"].includes(row.task.state) ? row.task : null });
  for (const view of document.querySelectorAll("[data-view]")) view.hidden = true;
  $("sohbet").hidden = false;
  document.body.classList.add("in-chat");
}

// ---- listeler ----
const call = async (method, params) => {
  const result = await rpc(method, params);
  if (!result.ok) toast(result.message || "İşlem yapılamadı.");
  return result;
};

function render() {
  renderChats(ctx, $("liste-sohbetler"), {
    open: openChat,
    onProjectCreate: async (name) => {
      const result = await call("projects.create", { name });
      if (result.ok) { await loadProjects(); render(); }
      return result.ok;
    },
  });
  renderTasks(ctx, $("liste-gorevler"), {
    open: (task) => openChat({ chatId: task.chatId, root: undefined, projectId: ctx.chatProjects[task.chatId] ?? null, title: task.summary, task }),
    cancel: async (task) => { await call("tasks.cancel", { runId: task.runId }); refresh(); },
    toggleSchedule: async (item) => { await call("schedules.enable", { id: item.id, enabled: !item.enabled }); await loadSchedules(); render(); },
    runSchedule: async (item) => {
      const result = await call("schedules.run", { id: item.id, idempotencyKey: crypto.randomUUID() });
      if (result.ok) { toast("Görev başlatıldı."); await refresh(); show("sohbetler"); }
    },
    runKit: async (kit) => { const r = await call("kits.run", { slug: kit.slug, idempotencyKey: crypto.randomUUID() }); if (r.ok) { toast("Kit başlatıldı."); refresh(); } },
  });
  renderSettings(ctx, $("liste-ayarlar"), {
    selectTier: async (name) => {
      ctx.tier = name;
      localStorage.setItem("fusion.tier", name);
      const result = await call("models.select", { name });
      if (result.ok) toast("Model seçildi.");
      chat?.refreshSelects();
    },
    renameProject: async (project) => {
      const name = prompt("Proje adı", project.name);
      if (name === null) return;
      if ((await call("projects.rename", { projectId: project.id, name })).ok) { await loadProjects(); render(); }
    },
    deleteProject: async (project) => {
      if (!confirm(`“${project.name}” silinsin mi? Sohbetler silinmez, projesiz kalır.`)) return;
      if ((await call("projects.delete", { projectId: project.id })).ok) { await loadProjects(); render(); }
    },
    unpair: async () => {
      try { await rpc("devices.revoke", {}); } catch { /* sunucu zaten reddetmiş olabilir */ }
      await forget();
    },
  });
  if (current === "onaylar" || ctx.tasks.some((t) => t.state === "waiting_approval")) void renderApprovals().catch(() => {});
}

async function renderApprovals() {
  const box = $("liste-onaylar");
  const cards = [];
  for (const task of ctx.tasks.filter((t) => t.state === "waiting_approval")) {
    const events = await rpc("tasks.events", { runId: task.runId });
    for (const [, question] of pendingFromEvents(events.data?.events ?? [])) {
      cards.push(h("div", { class: "approval-wrap" }, h("div", { class: "muted small" }, task.summary), approvalCard(question, rpc, refresh)));
    }
  }
  box.replaceChildren(...(cards.length ? cards : [h("p", { class: "empty" }, "Bekleyen onay yok.")]));
  const badge = $("rozet-onaylar");
  if (badge) { badge.textContent = String(cards.length); badge.hidden = cards.length === 0; }
}

async function loadProjects() {
  const result = await rpc("projects.list");
  if (result.ok) { ctx.projects = result.data.projects; ctx.chatProjects = result.data.chatProjects; }
}
async function loadChats() {
  const result = await rpc("chats.list");
  if (result.ok) ctx.chats = result.data.chats; // "mesgul" ise son liste korunur
}
async function loadSchedules() {
  const result = await rpc("schedules.list");
  ctx.schedules = result.ok ? result.data.schedules : null;
}
async function loadModels() {
  const result = await rpc("models.list");
  if (!result.ok) return;
  ctx.tiers = result.data.tiers;
  ctx.activeTier = result.data.active ?? "";
  ctx.tiersEditable = result.data.editable;
  if (!ctx.tiers.some((t) => t.name === ctx.tier)) ctx.tier = "";
}
async function loadKits() {
  if (!ctx.scopes.includes("kits.list")) return;
  const result = await rpc("kits.list");
  ctx.kits = result.ok ? result.data.kits : [];
}

let lastSlow = 0;
async function refresh(authOnly = false) {
  if (authOnly === true) return forget();
  try {
    const status = await rpc("service.status");
    const list = await rpc("tasks.list");
    const next = list.data?.tasks ?? [];
    const changed = JSON.stringify(next) !== JSON.stringify(ctx.tasks) || !rendered;
    ctx.tasks = next;
    ctx.notice = status.data?.notice ?? "";
    const slow = Date.now() - lastSlow > 20000;
    if (changed || slow) {
      lastSlow = Date.now();
      await Promise.all([loadChats(), loadProjects(), loadSchedules()]);
    }
    rendered = true;
    setConnection(true, "");
    if (changed || slow) render(); // aynı veriyle yeniden çizilmez: dokunuş/seçim ortasında düğüm kaybolmasın
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
    ctx,
    toast,
    onBack: () => show("sohbetler"),
    onChange: (authFailed) => (authFailed === true ? forget() : refresh()),
  });
  try {
    const status = await rpc("service.status");
    ctx.scopes = status.data?.scopes ?? [];
  } catch (error) {
    if (error.auth) return forget();
    setConnection(false, "Bilgisayara ulaşılamıyor; yeniden deneniyor…");
  }
  buildTabs();
  await Promise.all([loadModels(), loadKits()]);
  $("yeni").onclick = () => openChat(null);
  $("ekranIste").onclick = () => stream.start({ request: true });
  $("ekranDur").onclick = () => stream.stop();
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
  $("hesapDugme").onclick = accountLogin;
  // Cihaz anahtarı tarayıcı baskısıyla silinmesin (özellikle ana ekran uygulaması): kalıcı depo iste.
  navigator.storage?.persist?.().catch(() => {});
  device = (await kv("get", "device").catch(() => null)) ?? null;
  if (device) return start();
  $("eslestir").hidden = false;
  void loadAuthOptions();
  say("Eşleştirilmedi");
}
main();
