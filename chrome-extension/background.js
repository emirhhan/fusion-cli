// Araç çubuğu eylemi activeTab iznini verir; paneli aynı eylemden açıyoruz.
chrome.action.onClicked.addListener(async (tab) => {
  if (tab.id === undefined) return;
  await chrome.sidePanel.open({ tabId: tab.id });
});

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  if (message?.type !== "fusion.captureVisibleTab") return;
  chrome.tabs.captureVisibleTab(message.windowId, { format: "jpeg", quality: 65 })
    .then((image) => reply({ ok: true, image }))
    .catch((cause) => reply({ ok: false, error: String(cause?.message || cause) }));
  return true;
});
