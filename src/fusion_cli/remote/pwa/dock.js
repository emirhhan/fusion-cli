import { h } from "./dom.js";

function targetOf(item) {
  if (!Number.isInteger(item?.id) || item.id <= 0) return null;
  if (item.kind === "tab") return { kind: "tab", id: item.id };
  if (item.kind === "window" && Number.isInteger(item.pid) && item.pid > 0) return { kind: "window", id: item.id, pid: item.pid };
  return null;
}

export function createDock({ rpc, root, toast }) {
  let closed = false;
  let pending = null;
  const list = h("nav", { class: "mini-dock__items", "aria-label": "Pencereler ve Chrome sekmeleri" });
  const error = h("p", { class: "mini-dock__error danger small", role: "status", hidden: true });
  root.classList.add("mini-dock");
  const refreshButton = h("button", { class: "btn ghost small", type: "button", "aria-label": "Pencere ve sekme listesini yenile", onclick: () => refresh() }, "Yenile");
  root.replaceChildren(list, refreshButton, error);
  function failure(message) { error.textContent = message; error.hidden = false; }
  async function focus(target) {
    try {
      const result = await rpc("desktop.focus", { target });
      if (!closed && !result.ok) failure(result.message || "Hedef kapanmış olabilir. Listeyi yenile.");
    } catch (reason) {
      if (!closed) { failure(reason.message || "Hedef öne getirilemedi."); toast?.(error.textContent); }
    }
  }
  async function load() {
    try {
      const result = await rpc("desktop.targets");
      if (closed) return;
      if (!result.ok) { list.replaceChildren(); failure(result.message || "Masaüstü hedefleri alınamadı."); return; }
      const payload = result.data || {};
      const windows = Array.isArray(payload.windows) ? payload.windows : [];
      const tabs = Array.isArray(payload.tabs) ? payload.tabs : [];
      error.hidden = !(payload.native_error || payload.chrome_error);
      error.textContent = payload.native_error || payload.chrome_error || "";
      const buttons = [...windows, ...tabs].flatMap((item) => {
        const target = targetOf(item);
        if (!target) return [];
        const title = typeof item.title === "string" && item.title ? item.title : "Başlıksız";
        const label = target.kind === "window" && typeof item.app === "string" ? `${item.app}: ${title}` : title;
        const image = typeof item.icon === "string" && /^data:image\/png;base64,[A-Za-z0-9+/]+=*$/.test(item.icon)
          ? h("img", { src: item.icon, alt: "" }) : h("span", { "aria-hidden": true }, label.slice(0, 1).toLocaleUpperCase("tr"));
        return [h("button", { type: "button", class: "mini-dock__item", "data-target": `${target.kind}:${target.id}${target.kind === "window" ? `:${target.pid}` : ""}`,
          title: label, "aria-label": `${label} ${target.kind === "window" ? "penceresini" : "sekmesini"} öne getir`, onclick: () => focus(target) }, image,
        h("span", { class: "mini-dock__kind", "aria-hidden": true }, target.kind === "tab" ? "↗" : "▣"))];
      });
      list.replaceChildren(...buttons);
      if (!buttons.length && error.hidden) list.append(h("span", { class: "muted small" }, "Açık hedef yok."));
    } catch (reason) { if (!closed) { list.replaceChildren(); failure(reason.message || "Masaüstü listesi alınamadı."); } }
  }
  function refresh() {
    if (closed) return Promise.resolve();
    if (!pending) {
      refreshButton.disabled = true;
      pending = load().finally(() => { pending = null; refreshButton.disabled = false; });
    }
    return pending;
  }
  return {
    refresh,
    close() { closed = true; root.replaceChildren(); },
  };
}
