/* Web oturumu akışları: kendi aboneliğine ait tarayıcı tabanlı sağlayıcılar ve
 * kullanıcının kendi OpenAI-uyumlu ucu. Çekirdek panel panel.js'tedir.
 */

let activeWebProvider = null, activeWebModel = null;

const WEB_INFO = {
  chatgpt_web: {name:"ChatGPT Web (Plus/Pro)", site:"https://chatgpt.com", hint:"chatgpt.com üzerindeki oturum açmış bir isteğin tam Cookie başlığı",
    steps:["Tarayıcıyla giriş yönteminde Fusion'ın açtığı izole Chrome penceresinde hesabına giriş yap ve pencereyi kapat.",
           "Manuel yöntemde chatgpt.com → Geliştirici Araçları → Network bölümünde bir isteği seç; Request Headers içindeki Cookie değerinin tamamını kopyala. Cookie: önekini ekleme.",
           "Kaydet ve bağlantıyı kontrol et. Oturum süresi dolarsa aynı işlemi yenile."]},
  claude_web: {name:"Claude Web (Pro/Max)", site:"https://claude.ai", hint:"claude.ai Cookie başlığı (sessionKey dahil)",
    steps:["Önerilen yöntem: Fusion'ın açtığı izole tarayıcıda claude.ai hesabına giriş yap.",
           "Manuel yöntemde claude.ai üzerindeki bir Network isteğinin tam Cookie başlığını kopyala; yalnız sessionKey değil, istekteki tüm Cookie değeri daha dayanıklıdır.",
           "Kaydet, ardından gerçek küçük istekle bağlantıyı doğrula."]},
  gemini_web: {name:"Gemini Web (Google AI Pro/Ultra)", site:"https://gemini.google.com/app", hint:"Google birden çok cookie kullandığı için tarayıcıyla giriş önerilir",
    steps:["Google oturumu birden çok alan/cookie kullandığından en güvenilir yöntem Tarayıcıyla giriş yap düğmesidir.",
           "Açılan izole profilde Gemini'ye giriş yap, gerekli hesap doğrulamasını kendin tamamla ve pencereyi kapat.",
           "Manuel Cookie kullanacaksan gemini.google.com isteğinin Cookie başlığının tamamını ekle."]},
  copilot_web: {name:"Microsoft Copilot Web", site:"https://copilot.microsoft.com", hint:"Microsoft oturumu için tarayıcıyla giriş önerilir",
    steps:["Tarayıcıyla giriş yap düğmesiyle açılan izole profilde Microsoft hesabına giriş yap.",
           "Manuel yöntemde copilot.microsoft.com isteğinin tam Cookie başlığını ekle.",
           "Kaydettikten sonra bağlantı testini çalıştır; giriş yönlendirmesi görülürse tarayıcı oturumunu yenile."]}
};

// Giriş penceresi yoklama aralığı ve üst sınırı.
const LOGIN_POLL_MS = 2000;
const LOGIN_POLL_LIMIT_MS = 15 * 60 * 1000;

function closeModal(id) { $(id).classList.remove("open"); }

function openWebProvider(id, model) {
  activeWebProvider = id; activeWebModel = model || null;
  const info = WEB_INFO[id]; if (!info) return;
  const remember = localStorage.getItem("fusion-web-warning-" + id) === "1";
  if (remember) return showWebSetup(id, model);
  $("warnProviderName").textContent = info.name;
  $("webWarnRemember").checked = false;
  $("webWarningModal").classList.add("open");
}

function acceptWebWarning() {
  if ($("webWarnRemember").checked) localStorage.setItem("fusion-web-warning-" + activeWebProvider, "1");
  closeModal("webWarningModal"); showWebSetup(activeWebProvider, activeWebModel);
}

function showWebSetup(id, model) {
  activeWebProvider = id; activeWebModel = model || null;
  const info = WEB_INFO[id]; if (!info) return;
  const existing = (STATE.web_sessions || []).find((w) => w.model === model || (w.provider === id && w.account === "main"));
  const account = existing ? existing.account : "main";
  $("webSetupTitle").textContent = info.name;
  $("nativeWebAccount").value = account;
  $("nativeWebCookie").value = "";
  $("nativeWebHeadless").checked = existing ? existing.headless : true;
  $("nativeWebTimeout").value = existing ? existing.timeout_s : 180;
  $("webGuide").innerHTML = `<h3>Oturum bilgisi nasıl alınır?</h3><div>${info.hint}</div><ol>${info.steps.map((x) => `<li>${x}</li>`).join("")}</ol><div style="margin-top:var(--space-3);color:var(--warn-ink)">Cookie'yi bir şifre gibi koru; paylaşma ve ekran görüntüsüne alma.</div>`;
  updateNativeModel();
  $("nativeWebStatus").textContent = existing
    ? (existing.connected ? "Kayıt bulundu · oturum/profil mevcut" : "Kayıt bulundu · yeniden giriş gerekli olabilir")
    : "Henüz kaydedilmedi";
  $("webSetupModal").classList.add("open");
}

function updateNativeModel() {
  const account = ($("nativeWebAccount").value || "main").trim().replace(/[^a-zA-Z0-9_.-]+/g, "-");
  $("nativeWebModel").value = `${activeWebProvider}/${account || "main"}/auto`;
}

async function saveNativeWeb(showToast = true) {
  const account = ($("nativeWebAccount").value || "main").trim();
  const model = $("nativeWebModel").value;
  const cookie = $("nativeWebCookie").value.trim();
  const timeout_s = Number($("nativeWebTimeout").value || 180);
  const headless = $("nativeWebHeadless").checked;
  $("nativeWebStatus").textContent = "Kaydediliyor…";
  try {
    await post("/api/web_sessions", {provider: activeWebProvider, account, model, cookie, timeout_s, headless, tool_support: "emulated"});
    $("nativeWebCookie").value = ""; await load();
    $("nativeWebStatus").textContent = "Kaydedildi · Yönlendirme sekmesinde model olarak seçilebilir";
    if (showToast) toast("Web sağlayıcısı kaydedildi");
    return true;
  } catch (e) { $("nativeWebStatus").textContent = e.message; toast(e.message, true); return false; }
}

async function launchWebLogin() {
  const account = ($("nativeWebAccount").value || "main").trim();
  // Oturum ÖNCE kaydedilir: pencere kapandığında doğrulamanın çalışabilmesi için
  // yapılandırmada bir kayıt bulunmalı.
  if (!(await saveNativeWeb(false))) return;
  try {
    const res = await post("/api/web_sessions/login", {provider: activeWebProvider, account});
    $("nativeWebStatus").textContent = "İzole tarayıcı açıldı. Giriş yap, sonra pencereyi kapat — gerisi otomatik.";
    toast("Giriş tarayıcısı açıldı");
    if (res && res.pid) awaitLoginThenValidate(res.pid);
  } catch (e) { $("nativeWebStatus").textContent = e.message; toast(e.message, true); }
}

// Araç yeteneği ölçümü: web modelinin dosya değiştirmesine izin veren TEK kapı.
// Gerçek istek gönderir, bu yüzden yalnızca kullanıcı açıkça isteyince çalışır.
async function runWebEval() {
  if (!(await saveNativeWeb(false))) return;
  const model = $("nativeWebModel").value;
  $("nativeWebStatus").textContent = "Araç yeteneği ölçülüyor (5 gerçek istek, birkaç dakika sürebilir)…";
  try {
    const r = await post("/api/web_sessions/eval", {model});
    // Ölçülemeyen metrik "%100" DEĞİL "ölçülmedi" yazar: payda sıfırken oran
    // 1.0 döner ve ölçülmemiş bir şey mükemmel sanılırdı.
    const metrik = (ad, anahtar) => {
      const n = (r.measured || {})[anahtar];
      if (!n) return `${ad} ölçülmedi`;
      return `${ad} ${Math.round(r.scores[anahtar] * 100)}% (${n})`;
    };
    const ozet = [metrik("araç seçimi", "tool_selection"), metrik("şema", "schema_validity"),
                  metrik("argüman", "argument_preservation"), metrik("sahte çağrı yok", "no_false_calls")].join(" · ");
    $("nativeWebStatus").textContent = r.passed
      ? `Geçti · dosya değiştirme izni açıldı — ${ozet}`
      : `Geçemedi · model okuyup planlayabilir ama dosya değiştiremez — ${ozet}`;
    renderEvalSamples(r.samples || []);
    toast(r.passed ? "Araç yeteneği doğrulandı" : "Ölçüm eşiği geçilemedi", !r.passed);
    await load();
  } catch (e) { $("nativeWebStatus").textContent = e.message; toast(e.message, true); }
}

// Ölçüm düştüğünde SEBEBİ görünür olmalı: her senaryonun ham çıktısı, blok
// işaretinin görünüp görünmediği ve ayrıştırma hataları.
function renderEvalSamples(samples) {
  const kutu = $("webEvalSamples");
  if (!kutu) return;
  if (!samples.length) { kutu.innerHTML = ""; return; }
  kutu.innerHTML = "<h3>Ölçüm kayıtları</h3>" + samples.map((s, i) => {
    const beklenen = s.expected_tool || "(araç beklenmiyor)";
    const bulunan = s.parsed_tool || "—";
    const isaret = s.has_call_markers ? "blok işareti VAR" : "blok işareti YOK";
    const hatalar = (s.parse_errors || []).length ? `<div class="hint">ayrıştırma: ${s.parse_errors.join("; ")}</div>` : "";
    return `<details><summary class="subtle" style="cursor:pointer">${i + 1}. beklenen ${beklenen} · bulunan ${bulunan} · ${isaret}</summary>`
         + `${hatalar}<pre class="secret-area" style="white-space:pre-wrap;max-height:240px;overflow:auto">${
              (s.raw_preview || "").replace(/[&<>]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]))
            }</pre></details>`;
  }).join("");
}

// Giriş penceresi kapanana kadar yoklar, sonra bağlantıyı KENDİLİĞİNDEN test eder.
// Kullanıcının elle cookie kopyalaması ya da "şimdi doğrula" demesi gerekmez.
async function awaitLoginThenValidate(pid) {
  const bitis = Date.now() + LOGIN_POLL_LIMIT_MS;
  while (Date.now() < bitis) {
    await new Promise((r) => setTimeout(r, LOGIN_POLL_MS));
    let durum;
    try { durum = await post("/api/web_sessions/login_state", {pid}); }
    catch (e) { return; }                    // gateway kapandı: sessizce bırak
    if (durum && durum.running === false) {
      $("nativeWebStatus").textContent = "Giriş penceresi kapandı · bağlantı test ediliyor…";
      await validateNativeWeb();
      return;
    }
  }
  $("nativeWebStatus").textContent = "Giriş penceresi hâlâ açık. Kapattıktan sonra “Bağlantıyı kontrol et”e bas.";
}

async function validateNativeWeb() {
  const ok = await saveNativeWeb(false); if (!ok) return;
  const model = $("nativeWebModel").value;
  $("nativeWebStatus").textContent = "Gerçek bağlantı testi çalışıyor…";
  try {
    const d = await post("/api/web_sessions/validate", {model});
    $("nativeWebStatus").textContent = `Bağlantı başarılı · ${d.latency_ms} ms · ${d.preview || "yanıt alındı"}`;
    toast("Web AI bağlantısı başarılı");
  } catch (e) { $("nativeWebStatus").textContent = "Bağlantı başarısız: " + e.message; toast(e.message, true); }
}

/* --------------------------------------------------------------------- */
/* Kullanıcının kendi OpenAI-uyumlu ucu                                   */
/* --------------------------------------------------------------------- */

// Kullanıcının eklediği web ucunu kart olarak göster (endpoint + sil).
function webSessionCard(w) {
  const native = w.transport === "browser";
  const status = w.connected ? `<span class="badge ok">oturum kayıtlı</span>` : `<span class="badge fw">giriş gerekli</span>`;
  const edit = native ? `<button class="ghost" onclick="openWebProvider('${w.provider}','${w.model}')">Ayarla</button>` : "";
  const detail = native ? `${w.provider} · ${w.account} · ${w.headless ? "arka plan" : "görünür tarayıcı"}` : w.endpoint;
  return `<div class="pcard"><div class="pcard-head"><span class="name">${w.model}</span>${status}</div>
    <div class="meta" style="margin:var(--space-2) 0 var(--space-3);word-break:break-all">${detail}</div>
    <div class="row">${edit}<button class="danger" onclick="delWebSession('${w.model}')">Sil</button></div></div>`;
}

function toggleWebAdd() { $("webAddCard").classList.toggle("open"); }

// Panelden kendi OpenAI-uyumlu web ucunu ekle (adım adım formdan).
async function addWebSession() {
  const model = $("webModel").value.trim();
  const endpoint = $("webEndpoint").value.trim();
  const token = $("webToken").value.trim();
  const tool_support = $("webTools").checked ? "emulated" : "none";
  if (!model || !endpoint) return toast("model adı ve endpoint gerekli", true);
  try {
    await post("/api/web_sessions", { model, endpoint, token, tool_support });
    toast(model + " web ucu eklendi — Yönlendirme'den zincire ekle");
    $("webModel").value = ""; $("webEndpoint").value = ""; $("webToken").value = "";
    $("webTools").checked = false; $("webAddCard").classList.remove("open");
    await load();
  } catch (e) { toast(e.message, true); }
}

async function delWebSession(model) {
  try { await post("/api/web_sessions/delete", { model }); toast(model + " kaldırıldı"); await load(); }
  catch (e) { toast(e.message, true); }
}

// panel.js açılış sırasında çağırır; yükleme sırası davranışı belirlemesin diye
// burada top-level DOM erişimi yapılmaz.
function bindWebSessionForm() {
  $("nativeWebAccount").addEventListener("input", updateNativeModel);
}
