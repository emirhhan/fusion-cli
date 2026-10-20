// Küçük DOM yardımcıları. Metin yalnız textContent ile yazılır: HTML enjeksiyonu yok.
const SVG = "http://www.w3.org/2000/svg";

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

const ICONS = {
  chat: "M4 5h16v11H9l-5 4z",
  tasks: "M5 6h14M5 12h14M5 18h9",
  approve: "M12 3l8 3v6c0 5-3.5 8-8 9-4.500-1-8-4-8-9V6z M9 12l2 2 4-4",
  screen: "M3 5h18v11H3z M8 20h8 M12 16v4",
  settings: "M4 7h10M18 7h2M4 17h2M10 17h10 M16 5v4 M8 15v4",
  back: "M15 5l-7 7 7 7",
  plus: "M12 5v14M5 12h14",
  send: "M12 19V5M6 11l6-6 6 6",
  expand: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  close: "M6 6l12 12M18 6L6 18",
  stop: "M7 7h10v10H7z",
  mic: "M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z M6 11a6 6 0 0 0 12 0 M12 17v4",
  folder: "M3 7h6l2 2h10v10H3z",
  clock: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z M12 8v4l3 2",
  bolt: "M13 3L5 14h6l-1 7 8-11h-6z",
};

export function icon(name) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "ico");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", ICONS[name]);
  svg.append(path);
  return svg;
}

export function timeAgo(seconds, nowSeconds = Date.now() / 1000) {
  const diff = Math.max(0, Math.round(nowSeconds - seconds));
  if (diff < 45) return "şimdi";
  if (diff < 3600) return `${Math.round(diff / 60)} dk`;
  if (diff < 86400) return `${Math.round(diff / 3600)} sa`;
  return `${Math.round(diff / 86400)} g`;
}

export const STATE_LABEL = {
  queued: "Sırada",
  running: "Çalışıyor",
  waiting_approval: "Onay bekliyor",
  paused: "Duraklatıldı",
  done: "Bitti",
  failed: "Hata",
  cancelled: "İptal",
};
export const ACTIVE_STATES = ["queued", "running", "waiting_approval", "paused"];
