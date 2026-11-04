import { execute, MONITOR_KEY, registerMonitor } from "./core.js";
import { deviceIdentity } from "./device.js";

const HOST = "com.fusion.browser";

// Araç çubuğu eylemi activeTab iznini verir; paneli aynı eylemden açıyoruz. Manifestteki
// `_execute_action` kısayolu (Ctrl/⌘+Shift+F) da aynı dinleyiciye düşer (P-073).
chrome.action.onClicked.addListener(async (tab) => {
  if (tab.id === undefined) return;
  await chrome.sidePanel.open({ tabId: tab.id });
});

// Klavye kısayolu "fusion-stop": süren turu panele durdurtur (sayfadaki Durdur hapı gibi).
chrome.commands?.onCommand.addListener((command) => {
  if (command === "fusion-stop") chrome.runtime.sendMessage({ type: "fusion.stop" }).catch(() => undefined);
});

// Konsol/ağ izleyicisi yalnız izinli sitelere kayıtlıdır; izin ya da ayar değişince yenilenir
// (core.js çağrıları sıraya koyar). Hata yutulmaz: hizmet çalışanı günlüğüne düşer.
const refreshMonitor = () => registerMonitor().catch((cause) => console.warn("Fusion izleyici kaydı:", cause));
chrome.permissions.onAdded.addListener(refreshMonitor);
chrome.permissions.onRemoved.addListener(refreshMonitor);
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && MONITOR_KEY in changes) void refreshMonitor();
});

/**
 * Fusion bağlantısını açık tutan görünmez belge. Hizmet çalışanı 30 sn boşta
 * kalınca durdurulur; uzun yoklama bu belgede yaşar, komutları buraya iletir.
 */
async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument?.()) return;
  try {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["WORKERS"],
      justification: "Fusion masaüstü uygulamasıyla yerel bağlantıyı açık tutar.",
    });
  } catch (cause) {
    if (!String(cause?.message || cause).includes("single offscreen")) throw cause;
  }
}

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  if (message?.type === "fusion.captureVisibleTab") {
    chrome.tabs.captureVisibleTab(message.windowId, { format: "jpeg", quality: 65 })
      .then((image) => reply({ ok: true, image }))
      .catch((cause) => reply({ ok: false, error: String(cause?.message || cause) }));
    return true;
  }
  if (message?.type === "fusion.exec") {
    execute(message.command, {
      onPermissionProgress: (progress) => chrome.runtime.sendMessage({type: "fusion.permissionProgress", progress}),
    })
      .then((veri) => reply({ ok: true, veri }))
      .catch((cause) => reply({ ok: false, hata: String(cause?.message || cause), neden_kodu: cause?.code || "" }));
    return true;
  }
  if (message?.type === "fusion.pair") {
    // Fusion'ı yerel mesajlaşmayla bul (bkz. fusion_cli/appserver/chrome_host.py).
    chrome.runtime.sendNativeMessage(HOST, { type: "pair" })
      .then((answer) => reply(answer || { ok: false }))
      .catch((cause) => reply({ ok: false, hata: String(cause?.message || cause) }));
    return true;
  }
  if (message?.type === "fusion.device") {
    // Offscreen belgesi chrome.storage'a erişemez; kimliği buradan alır (#432).
    deviceIdentity().then(reply).catch(() => reply(null));
    return true;
  }
  if (message?.type === "fusion.ping") {
    reply({ ok: true, surum: chrome.runtime.getManifest().version });
    return false;
  }
  if (message?.type === "fusion.update") {
    // Diskte yeni sürüm var (offscreen.js denetler). Açık paneli kesmemek için yalnız
    // panel kapalıyken yenilenir; açıksa panel "Şimdi güncelle" düğmesini gösterir.
    chrome.runtime.getContexts({ contextTypes: ["SIDE_PANEL"] })
      .then((panels) => {
        if (panels.length) { reply({ ok: false, sebep: "panel açık" }); return; }
        reply({ ok: true });
        chrome.runtime.reload();
      })
      .catch((cause) => reply({ ok: false, hata: String(cause?.message || cause) }));
    return true;
  }
  if (message?.type === "fusion.status") {
    chrome.storage.session.set({ fusionAuto: message.status }).then(() => reply({ ok: true }));
    return true;
  }
  return false;
});

chrome.runtime.onStartup.addListener(() => { void ensureOffscreen(); void refreshMonitor(); });
chrome.runtime.onInstalled.addListener(() => { void ensureOffscreen(); void refreshMonitor(); });
void ensureOffscreen();
