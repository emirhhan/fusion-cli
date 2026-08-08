/* Panel çekirdeği: durum yükleme, gezinme, sağlayıcı/zincir/analitik render'ı.
 * Web oturumu akışları ayrı dosyadadır (web-sessions.js).
 */

const $ = (id) => document.getElementById(id);
let STATE = null, chain = [], judge = [];

// Durumun kendiliğinden tazelendiği sekmeler: yalnız canlı veri gösterenler.
const LIVE_TABS = ["genel", "analitik", "saglik"];
const REFRESH_MS = 5000;

// Kenar çubuğu gezinmesi: aktif sekmeyi değiştir ve üst bar başlığını güncelle.
// Öğeler gerçek <button>'dır; `active` sınıfı görünümü, `aria-current` ise ekran
// okuyucuya hangi sayfada olunduğunu anlatır. İkisi birlikte güncellenir.
function bindNav() {
  document.querySelectorAll(".nav-item").forEach((t) => t.onclick = () => {
    document.querySelectorAll(".nav-item").forEach((x) => {
      x.classList.remove("active");
      x.removeAttribute("aria-current");
    });
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    t.setAttribute("aria-current", "page");
    $("tab-" + t.dataset.tab).classList.add("active");
    $("pageTitle").textContent = t.dataset.title; $("pageSub").textContent = t.dataset.sub;
  });
}

function toast(msg, err) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast show" + (err ? " err" : "");
  setTimeout(() => el.className = "toast" + (err ? " err" : ""), 2200);
}

/* --------------------------------------------------------------------- */
/* Yükleniyor / boş durum yardımcıları                                    */
/* --------------------------------------------------------------------- */

// Boş durum tek yerden üretilir: her ekranda farklı bir "veri yok" cümlesi
// yazmak yerine aynı bileşen, farklı metinle.
const EMPTY_MARK = '<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.4"'
  + ' stroke-linecap="round" stroke-linejoin="round"><path d="M3 5.5h12M3 9h12M3 12.5h7"/></svg>';

function emptyState(title, hint) {
  return `<div class="empty"><span class="empty-mark">${EMPTY_MARK}</span>
    <span class="empty-title">${title}</span>
    ${hint ? `<span class="empty-hint">${hint}</span>` : ""}</div>`;
}

// Tablo gövdesinde boş durum tek hücreye yayılır; yoksa ilk sütuna sıkışıp
// tablonun hizasını bozuyordu.
function emptyRow(cols, title, hint) {
  return `<tr><td colspan="${cols}">${emptyState(title, hint)}</td></tr>`;
}

// Ağ isteği süren düğme: bir daha basılamaz ve çalıştığını gösterir. İş
// bittiğinde eski hâline HER durumda döner — hata da dönse düğme kilitli
// kalmamalı.
async function withBusy(el, work) {
  if (!el) return work();
  el.classList.add("busy");
  el.disabled = true;
  try { return await work(); }
  finally { el.classList.remove("busy"); el.disabled = false; }
}

// Olay üzerinden çağrılan işlemler için: `onclick="busyClick(event, saveRouting)"`
function busyClick(event, work) {
  return withBusy(event.currentTarget, work);
}

async function post(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((d.error && d.error.message) || "hata");
  return d;
}

// Uç noktayı panoya kopyala.
async function copyEndpoint() {
  const url = $("endpointUrl").textContent;
  try { await navigator.clipboard.writeText(url); toast("uç nokta kopyalandı"); }
  catch (e) { toast("kopyalanamadı: " + url, true); }
}

/* --------------------------------------------------------------------- */
/* Sağlayıcılar                                                           */
/* --------------------------------------------------------------------- */

// Seçili kategori ("" = hepsi). Çip tıklamasıyla değişir.
let activeCategory = "";
const CATEGORY_ORDER = ["API anahtarı", "Web oturumu", "OAuth", "Yerel", "Yakında"];

function categoryOrder(name) {
  const i = CATEGORY_ORDER.indexOf(name);
  return i === -1 ? CATEGORY_ORDER.length : i;
}

// Sağlayıcıları kategoriye göre gruplayıp render et; arama + kategori çipiyle süz.
function renderProviders() {
  const s = STATE; if (!s) return;
  const q = $("providerSearch").value.trim().toLowerCase();
  const providers = s.providers.filter((p) =>
    (!q || p.name.toLowerCase().includes(q)) &&
    (!activeCategory || p.category === activeCategory));

  renderCatChips(s.providers);

  // Kategoriye göre grupla, sıralı bas. "Hepsi" görünümünde grup başlıkları ekle.
  const groups = {};
  for (const p of providers) (groups[p.category] ||= []).push(p);
  const names = Object.keys(groups).sort((a, b) => categoryOrder(a) - categoryOrder(b));
  const showTitles = !activeCategory && names.length > 1;
  let html = names.map((cat) =>
    (showTitles ? `<div class="cat-group-title">${cat}</div>` : "") +
    `<div class="provider-grid">${groups[cat].map(providerCard).join("")}</div>`
  ).join("");

  // Kullanıcının kendi eklediği web uçları (varsa), kategori filtresi uygunsa göster.
  const mine = (s.web_sessions || []).filter((w) => !q || w.model.toLowerCase().includes(q));
  if (mine.length && (!activeCategory || activeCategory === "Web oturumu")) {
    html += `<div class="cat-group-title">Kendi uçların</div><div class="provider-grid">` +
      mine.map(webSessionCard).join("") + `</div>`;
  }
  $("providers").innerHTML = html || emptyState("Eşleşen sağlayıcı yok",
    "Arama kutusunu temizle ya da başka bir kategori çipi seç.");
}

// Kategori çiplerini (ad + sayı) bas; aktif olan vurgulu.
function renderCatChips(all) {
  const counts = {};
  for (const p of all) counts[p.category] = (counts[p.category] || 0) + 1;
  const cats = Object.keys(counts).sort((a, b) => categoryOrder(a) - categoryOrder(b));
  const chip = (label, key, n) =>
    `<button type="button" class="cat-chip ${activeCategory === key ? "active" : ""}"
      aria-pressed="${activeCategory === key}" onclick="setCategory('${key}')">${label} <span class="count">${n}</span></button>`;
  $("catChips").innerHTML =
    chip("Hepsi", "", all.length) + cats.map((c) => chip(c, c, counts[c])).join("");
}

function setCategory(cat) { activeCategory = cat; renderProviders(); }

function providerCard(p) {
  if (!p.implemented) return `<div class="pcard" data-name="${p.name}"><div class="pcard-head"><span class="name">${p.name}</span><span class="badge fw">adaptör yok</span></div></div>`;
  if (p.kind === "browser_backed" || p.kind === "web_session") {
    const status = p.configured ? `<span class="badge ok">kurulu</span>` : `<span class="badge web">deneysel</span>`;
    return `<div class="pcard keyed" data-name="${p.name}">
      <button type="button" class="pcard-head" onclick="openWebProvider('${p.id}')">
        <span class="name">${p.name}</span>${status}<span class="caret" aria-hidden="true">›</span>
      </button>
      <div class="meta" style="margin-top:var(--space-2)">kendi aboneliğin · native browser adapter</div></div>`;
  }
  if (p.local) return `<div class="pcard" data-name="${p.name}"><div class="pcard-head"><span class="name">${p.name}</span><span class="badge local">yerel</span></div></div>`;
  const status = p.configured ? `<span class="badge ok">kurulu${p.keys > 1 ? " · " + p.keys + " hesap" : ""}</span>` : `<span class="badge">anahtar yok</span>`;
  const del = p.configured ? `<button class="danger" onclick="delKey('${p.id}')">Sil</button>` : "";
  // Tıklanabilir tile: baş kısmına basınca gövde (anahtar girişi) açılıp kapanır.
  return `<div class="pcard keyed" id="pcard-${p.id}" data-name="${p.name}">
    <button type="button" class="pcard-head" onclick="togglePcard('${p.id}')"
      aria-expanded="false" aria-controls="pbody-${p.id}">
      <span class="name">${p.name}</span>${status}<span class="caret" aria-hidden="true">▾</span>
    </button>
    <div class="pcard-body" id="pbody-${p.id}">
      <div class="meta" style="margin-bottom:var(--space-3)">${p.kind} · ${p.status}</div>
      <div class="row"><input class="grow" type="password" id="key-${p.id}" placeholder="API anahtarını yapıştır" />
      <button onclick="setKey('${p.id}')">Kaydet</button>${del}</div>
    </div></div>`;
}

function togglePcard(id) {
  const el = $("pcard-" + id); if (!el) return;
  const willOpen = !el.classList.contains("open");
  // Aynı anda tek kart açık kalsın.
  document.querySelectorAll(".pcard.open").forEach((c) => setPcardOpen(c, false));
  if (willOpen) { setPcardOpen(el, true); const inp = $("key-" + id); if (inp) inp.focus(); }
}

// Açık/kapalı durumu iki yerde birden tutulur: sınıf görünüm için, aria-expanded
// ekran okuyucu için. Biri güncellenip diğeri unutulursa kart klavye kullanıcısına
// yalan söyler.
function setPcardOpen(card, open) {
  card.classList.toggle("open", open);
  const head = card.querySelector(".pcard-head");
  if (head) head.setAttribute("aria-expanded", String(open));
}

async function setKey(id) {
  const v = $("key-" + id).value.trim(); if (!v) return toast("anahtar boş", true);
  try { await post("/api/keys", { provider: id, value: v }); toast(id + " anahtarı kaydedildi"); await load(); } catch (e) { toast(e.message, true); }
}
async function delKey(id) { try { await post("/api/keys/delete", { provider: id }); toast(id + " anahtarı silindi"); await load(); } catch (e) { toast(e.message, true); } }

/* --------------------------------------------------------------------- */
/* Zincir, hakem, yönlendirme                                             */
/* --------------------------------------------------------------------- */

function chainRow(m, i, prefix) {
  return `<div class="chain-item"><span class="idx">${i + 1}</span>
    <span class="grow">${m}</span>
    <button class="ghost" onclick="move${prefix}(${i},-1)" aria-label="yukarı">↑</button>
    <button class="ghost" onclick="move${prefix}(${i},1)" aria-label="aşağı">↓</button>
    <button class="danger" onclick="rm${prefix}(${i})" aria-label="çıkar">✕</button></div>`;
}

function renderChain() {
  $("chain").innerHTML = chain.map((m, i) => chainRow(m, i, "Chain")).join("")
    || emptyState("Yedek zinciri boş",
         "Aşağıdan bir model ekle; ilk sıradaki baş model olur.");
}
function moveChain(i, d) { const j = i + d; if (j < 0 || j >= chain.length) return; [chain[i], chain[j]] = [chain[j], chain[i]]; renderChain(); }
function rmChain(i) { chain.splice(i, 1); renderChain(); }
function addChain() { const v = $("newModel").value.trim(); if (v) { chain.push(v); $("newModel").value = ""; renderChain(); } }
function setHead() { const v = $("agentHead").value.trim(); if (!v) return; chain = [v, ...chain.filter((m) => m !== v)]; $("agentHead").value = ""; renderChain(); toast("baş model ayarlandı — 'Zinciri Kaydet'e bas"); }

function renderJudge() {
  $("judge").innerHTML = judge.map((m, i) => chainRow(m, i, "Judge")).join("")
    || emptyState("Hakem modeli seçilmedi",
         "Fusion motoru adayları karşılaştırmak için bir hakem modeli kullanır.");
}
function moveJudge(i, d) { const j = i + d; if (j < 0 || j >= judge.length) return; [judge[i], judge[j]] = [judge[j], judge[i]]; renderJudge(); }
function rmJudge(i) { judge.splice(i, 1); renderJudge(); }
function addJudge() { const v = $("newJudge").value.trim(); if (v) { judge.push(v); $("newJudge").value = ""; renderJudge(); } }

async function saveJudge() { try { const d = await post("/api/model", { role: "judge", models: judge }); toast(d.saved ? "hakem kaydedildi" : "uygulandı (yazılamadı)"); await load(); } catch (e) { toast(e.message, true); } }
async function saveRouting() { try { const d = await post("/api/routing", { strategy: $("strategy").value }); toast("yönlendirme: " + d.strategy); await load(); } catch (e) { toast(e.message, true); } }
async function saveFallback() { try { const d = await post("/api/fallback", { models: chain, strict: $("strictModel").checked }); toast(d.saved ? "zincir kaydedildi" : "uygulandı (dosyaya yazılamadı)"); await load(); } catch (e) { toast(e.message, true); } }
async function resetHealth() { try { await post("/api/health/reset", {}); toast("sağlık sıfırlandı"); await load(); } catch (e) { toast(e.message, true); } }

/* --------------------------------------------------------------------- */
/* Model kataloğu ve playground                                           */
/* --------------------------------------------------------------------- */

let catalog = [];
function ctxLabel(n) { return n ? Math.round(n / 1000) + "k bağlam · " : ""; }

// Kullanıcının KENDİ oturumları (gemini_web/…, chatgpt_web/…) ve profiller,
// uzak katalogda BULUNMAZ. Eskiden model seçicileri yalnızca katalogdan
// dolduruluyordu; panelden bir web oturumu eklenip giriş yapılsa bile o oturum
// hiçbir seçicide görünmüyor, yalnızca Playground'a düşüyordu. Kullanıcı onu
// baş model ya da yedek yapamıyordu — kimliği ezbere yazmak dışında yolu yoktu.
function localModelOptions() {
  const models = (STATE && STATE.models) || [];
  const web = new Set(((STATE && STATE.web_sessions) || []).map((s) => s.model));
  return models.map((id) => ({
    id,
    // Kendi aboneliğin en üstte ve etiketli durur: seçicide aranan ilk şey odur.
    label: web.has(id) ? "kendi oturumun · web" : "profil / yapılandırılmış",
    local: true,
    web: web.has(id),
  }));
}

function renderCatalog() {
  const onlyFree = $("catalogFree").checked;
  const items = catalog.filter((m) => !onlyFree || m.free);
  const yerel = localModelOptions();
  const gorulen = new Set(yerel.map((m) => m.id));

  // Yerel seçenekler ÖNCE listelenir; datalist sırayı korur.
  const secenekler = [
    ...yerel.map((m) => `<option value="${m.id}">${m.label}</option>`),
    ...items
      .filter((m) => !gorulen.has(m.id))
      .map((m) => `<option value="${m.id}">${m.free ? "ücretsiz · " : ""}${ctxLabel(m.context_length)}${m.provider}</option>`),
  ];
  $("catalogList").innerHTML = secenekler.join("");

  const webSayisi = yerel.filter((m) => m.web).length;
  $("catalogCount").textContent =
    catalog.length + " model" +
    (onlyFree ? " (" + items.length + " ücretsiz)" : "") +
    (webSayisi ? " + " + webSayisi + " kendi oturumun" : "");

  // Playground listesini profiller + katalogla birleştir (tekilleştirilmiş).
  const base = (STATE && STATE.models) || [];
  const merged = [...new Set([...base, ...items.map((m) => m.id)])];
  const cur = $("chatModel").value;
  $("chatModel").innerHTML = merged.map((m) => `<option ${m === cur ? "selected" : ""}>${m}</option>`).join("");
}

async function loadCatalog(refresh, el) {
  if (el) return withBusy(el, () => loadCatalog(refresh));
  try {
    const d = await fetch("/api/models/catalog" + (refresh ? "?refresh=1" : "")).then((r) => r.json());
    catalog = d.models || []; renderCatalog();
    if (refresh) toast(catalog.length + " model bulundu");
  } catch (e) { /* katalog bir iyileştirmedir; sessizce geç */ }
}

async function sendChat() {
  const model = $("chatModel").value, msg = $("chatMsg").value.trim();
  if (!msg) return; $("chatOut").textContent = "…"; $("chatMeta").textContent = "";
  try {
    const r = await fetch("/v1/chat/completions", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ model, messages: [{ role: "user", content: msg }] }) });
    const d = await r.json();
    const route = r.headers.get("x-fusion-route") || "";
    $("chatOut").textContent = (d.choices && d.choices[0] && d.choices[0].message.content) || JSON.stringify(d, null, 2);
    $("chatMeta").textContent = (d.model ? "model: " + d.model : "") + (route ? " · " + route : "");
  } catch (e) { $("chatOut").textContent = "hata: " + e.message; }
}

/* --------------------------------------------------------------------- */
/* Render ve açılış                                                       */
/* --------------------------------------------------------------------- */

function render() {
  const s = STATE;
  $("endpointUrl").textContent = location.origin + "/v1";
  $("s-total").textContent = s.providers.length;
  $("s-ready").textContent = s.providers.filter((p) => p.configured || p.local).length;
  $("s-models").textContent = s.models.length;
  $("s-strategy").textContent = s.routing.current;
  $("cfgpath").textContent = s.config_path || "(yalnız varsayılanlar)";
  $("activeModel").textContent = (s.fallback && s.fallback[0]) || "—";
  const recent = (s.analytics && s.analytics.recent) || [];
  $("lastServed").textContent = recent.length ? recent[0].served : "—";
  $("secretHint").textContent = s.secret_ready
    ? "Anahtarlar ŞİFRELİ saklanır ve hemen etkinleşir."
    : "Not: FUSION_SECRET_KEY ayarlı değil — anahtar yalnızca bu oturumda geçerli olur (şifreli kaydedilmez).";
  renderProviders();  // kategori + arama filtresiyle grupla

  const sel = $("strategy");
  sel.innerHTML = s.routing.options.map((o) => `<option ${o === s.routing.current ? "selected" : ""}>${o}</option>`).join("");
  chain = s.fallback.slice(); renderChain();
  $("strictModel").checked = Boolean(s.strict_model_selection);
  judge = (s.judge || []).slice(); renderJudge();
  // Model seçicileri STATE'e de bağlıdır: yeni bir web oturumu eklendiğinde
  // listenin bir sonraki durum yenilemesinde görünmesi gerekir. `loadCatalog`
  // yalnızca açılışta ve elle tazelemede çalışır; ona bırakılırsa oturum
  // panel yeniden yüklenene kadar seçilemez kalırdı.
  renderCatalog();

  const hm = s.health;
  $("health").innerHTML = hm.map((m) => `<tr><td class="model">${m.model}</td>
    <td><span class="bar"><i style="width:${Math.round(m.score * 100)}%"></i></span>${Math.round(m.score * 100)}%</td>
    <td class="phase ${m.phase}">${m.phase}</td><td>${m.avg_latency_ms || 0} ms</td><td>${m.samples}</td></tr>`).join("")
    || emptyRow(5, "Sağlık verisi yok",
         "Devre durumu ve güvenilirlik skoru, modellere istek gittikçe birikir.");

  $("chatModel").innerHTML = s.models.map((m) => `<option>${m}</option>`).join("");
  if (catalog.length) renderCatalog();  // durum yenilenince katalog eklerini koru
  renderAnalytics(s.analytics || {});
  $("brandVer").textContent = "v" + (s.version || "?");
}

function renderAnalytics(a) {
  $("a-req").textContent = a.requests ?? 0;
  $("a-tok").textContent = a.total_tokens ?? 0;
  $("a-lat").textContent = a.avg_latency_ms ?? 0;
  $("a-p95").textContent = a.p95_latency_ms ?? 0;
  $("a-cache").textContent = a.cache_hits ?? 0;
  $("a-comp").textContent = a.compression_saved_chars ?? 0;
  $("a-permodel").innerHTML = (a.per_model || []).map((m) =>
    `<tr><td class="model">${m.model}</td><td>${m.requests}</td><td>${m.tokens}</td><td>${m.avg_latency_ms} ms</td></tr>`
  ).join("") || emptyRow(4, "Model başına veri yok", "Gateway üzerinden bir istek geçtiğinde dolar.");
  $("a-recent").innerHTML = (a.recent || []).map((r) =>
    `<tr><td class="model">${r.requested}</td><td class="model">${r.served}</td><td>${r.tokens}</td><td>${r.latency_ms} ms</td><td>${r.cached ? '<span class="badge ok">önbellek</span>' : (r.ok ? "✓" : "✕")}</td></tr>`
  ).join("") || emptyRow(5, "Henüz istek yok",
    "Test sekmesinden bir istek gönder ya da uç noktayı bir araca bağla.");
}

// İlk veri gelene kadar sayı alanları iskelet olarak durur ve içerik bölgesi
// ekran okuyucuya "meşgul" der. İkisi de yalnızca İLK yüklemede anlamlıdır;
// sonraki periyodik tazelemeler ekranı iskelete geri döndürmez.
function ilkYuklemeBitti() {
  document.querySelectorAll(".skeleton").forEach((el) => el.classList.remove("skeleton"));
  document.querySelector(".content").setAttribute("aria-busy", "false");
}

async function load() {
  try {
    STATE = await fetch("/api/state").then((r) => r.json());
    render();
    ilkYuklemeBitti();
  } catch (e) { /* sunucu kapalı */ }
}

function isLiveTabActive() {
  const active = document.querySelector(".nav-item.active");
  return Boolean(active) && LIVE_TABS.includes(active.dataset.tab);
}

// Açılış tek yerden yapılır ve DOM hazır olduğunda çalışır: böylece bu dosya
// ile web-sessions.js'in yükleme sırası davranışı belirlemez.
document.addEventListener("DOMContentLoaded", () => {
  bindNav();
  bindWebSessionForm();
  load();
  loadCatalog(false);
  setInterval(() => { if (isLiveTabActive()) load(); }, REFRESH_MS);
});
