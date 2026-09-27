// Fusion bir sekmede çalışırken sayfanın kenarında ışık ve altta "Durdur" hapı
// gösterir (Claude in Chrome'daki çerçevenin karşılığı). Yalnız görseldir: sayfa
// olaylarını yakalamaz, tıklamaları engellemez.

import { getSelected } from "./core.js";

/** Sayfanın İÇİNDE çalışır (chrome.scripting ile enjekte edilir); dış kapsam yoktur. */
export function showGlow() {
  const id = "fusion-agent-glow";
  if (document.getElementById(id)) return;
  const host = document.createElement("div");
  host.id = id;
  // Gölge DOM: sayfanın CSS'i ışığı bozamaz, ışık da sayfayı etkilemez.
  const root = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }
    .frame { position: fixed; inset: 0; z-index: 2147483646; pointer-events: none;
      box-shadow: inset 0 0 0 2px rgb(168 255 62 / 75%), inset 0 0 28px 4px rgb(168 255 62 / 28%);
      animation: breathe 2.4s ease-in-out infinite; }
    .pill { position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 2147483647;
      display: flex; align-items: center; gap: 10px; padding: 7px 8px 7px 14px; border-radius: 999px;
      background: #0b0a0d; color: #f3f5f6; font: 500 13px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      box-shadow: 0 10px 30px rgb(0 0 0 / 35%), 0 0 0 1px rgb(255 255 255 / 10%); pointer-events: auto; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #a8ff3e; box-shadow: 0 0 0 4px rgb(168 255 62 / 20%);
      animation: breathe 1.2s ease-in-out infinite; }
    button { all: unset; cursor: pointer; padding: 5px 12px; border-radius: 999px; background: #f3f5f6; color: #0b0a0d;
      font: 600 12px/1.2 -apple-system, BlinkMacSystemFont, sans-serif; }
    button:hover { background: #fff; }
    button:focus-visible { outline: 2px solid #a8ff3e; outline-offset: 2px; }
    @keyframes breathe { 50% { opacity: .55; } }
    @media (prefers-reduced-motion: reduce) { .frame, .dot { animation: none; } }`;
  const frame = document.createElement("div");
  frame.className = "frame";
  const pill = document.createElement("div");
  pill.className = "pill";
  const dot = document.createElement("span");
  dot.className = "dot";
  const label = document.createElement("span");
  label.textContent = "Fusion bu sekmede çalışıyor";
  const stop = document.createElement("button");
  stop.type = "button";
  stop.textContent = "Durdur";
  stop.addEventListener("click", () => chrome.runtime.sendMessage({ type: "fusion.stop" }));
  pill.append(dot, label, stop);
  root.append(style, frame, pill);
  document.documentElement.append(host);
}

/** Sayfanın İÇİNDE çalışır. */
export function hideGlow() {
  document.getElementById("fusion-agent-glow")?.remove();
}

/** Fusion'ın çalıştığı sekme: bağlı sekme, yoksa etkin sekme. */
async function workingTabId() {
  const selected = await getSelected();
  if (selected?.id) return selected.id;
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab?.id;
}

/**
 * Işığı Fusion'ın çalıştığı sekmede aç/kapat. Chrome'un kendi sayfaları (chrome://) ve izin
 * verilmemiş siteler betik kabul etmez; ışık yalnız görsel olduğu için o
 * durumda sessizce atlanır — görevin kendisi bundan etkilenmez.
 */
export async function setGlow(visible) {
  const tabId = await workingTabId();
  if (tabId === undefined) return;
  try {
    await chrome.scripting.executeScript({ target: { tabId }, func: visible ? showGlow : hideGlow });
  } catch {
    // Görsel yardımcı: betik kabul etmeyen sekmede ışık yok, görev sürer.
  }
}
