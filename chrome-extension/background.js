import { execute } from "./core.js";

const HOST = "com.fusion.browser";

// Araç çubuğu eylemi activeTab iznini verir; paneli aynı eylemden açıyoruz.
chrome.action.onClicked.addListener(async (tab) => {
  if (tab.id === undefined) return;
  await chrome.sidePanel.open({ tabId: tab.id });
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
    execute(message.command)
      .then((veri) => reply({ ok: true, veri }))
      .catch((cause) => reply({ ok: false, hata: String(cause?.message || cause) }));
    return true;
  }
  if (message?.type === "fusion.pair") {
    // Fusion'ı yerel mesajlaşmayla bul (bkz. fusion_cli/appserver/chrome_host.py).
    chrome.runtime.sendNativeMessage(HOST, { type: "pair" })
      .then((answer) => reply(answer || { ok: false }))
      .catch((cause) => reply({ ok: false, hata: String(cause?.message || cause) }));
    return true;
  }
  if (message?.type === "fusion.status") {
    chrome.storage.session.set({ fusionAuto: message.status }).then(() => reply({ ok: true }));
    return true;
  }
  return false;
});

chrome.runtime.onStartup.addListener(() => void ensureOffscreen());
chrome.runtime.onInstalled.addListener(() => void ensureOffscreen());
void ensureOffscreen();
