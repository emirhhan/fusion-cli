import { h } from "./dom.js";

// İki aşamalı gezinme: 1) uygulamalar şeridi  2) seçilen uygulamanın pencereleri ve (Chrome) sekmeleri.
// Odaklama API'si aynı kalır: `desktop.focus` ile {kind, id[, pid]} hedefi.

const SEARCH_THRESHOLD = 8;
const ICON = /^data:image\/(png|jpeg|webp|gif|x-icon|vnd\.microsoft\.icon);base64,[A-Za-z0-9+/]+=*$/;
const CHROME = /chrome/i;

function targetOf(item) {
  if (!Number.isInteger(item?.id) || item.id <= 0) return null;
  if (item.kind === "tab") return { kind: "tab", id: item.id };
  if (item.kind === "window" && Number.isInteger(item.pid) && item.pid > 0) return { kind: "window", id: item.id, pid: item.pid };
  return null;
}

const text = (value, fallback = "") => (typeof value === "string" && value ? value : fallback);
const safeIcon = (value) => (typeof value === "string" && ICON.test(value) ? value : null);
const initial = (label) => label.slice(0, 1).toLocaleUpperCase("tr");

function host(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}

// Pencereleri uygulamaya, Chrome sekmelerini Chrome uygulamasına toplar.
export function groupApps(windows, tabs) {
  const apps = new Map();
  const entry = (name) => {
    if (!apps.has(name)) apps.set(name, { name, icon: null, windows: [], tabs: [], active: false });
    return apps.get(name);
  };
  for (const item of windows) {
    if (!targetOf(item)) continue;
    const app = entry(text(item.app, "Uygulama"));
    app.icon ??= safeIcon(item.icon);
    app.windows.push(item);
    if (item.visible === true) app.active = true;
  }
  const validTabs = tabs.filter((item) => targetOf(item));
  if (validTabs.length) {
    const chrome = [...apps.values()].find((app) => CHROME.test(app.name)) ?? entry("Chrome");
    chrome.tabs = validTabs;
    if (validTabs.some((tab) => tab.active === true)) chrome.active = true;
  }
  return [...apps.values()].sort((a, b) => Number(b.active) - Number(a.active) || a.name.localeCompare(b.name, "tr"));
}

export function appCount(app) {
  return app.windows.length + app.tabs.length;
}

// Tek hedefi olan uygulamada ikinci aşama atlanır.
export function soleTarget(app) {
  if (appCount(app) !== 1) return null;
  return targetOf(app.windows[0] ?? app.tabs[0]);
}

export function createDock({ rpc, root, toast }) {
  let closed = false;
  let pending = null;
  let apps = [];
  let current = null; // açık uygulama adı (2. aşama) ya da null
  let query = "";
  let loadError = "";
  const body = h("div", { class: "mini-dock__body" });
  const error = h("p", { class: "mini-dock__error danger small", role: "status", hidden: true });
  const refreshButton = h("button", { class: "btn ghost small", type: "button", "aria-label": "Uygulama, pencere ve sekme listesini yenile", onclick: () => refresh() }, "Yenile");
  root.classList.add("mini-dock");
  root.replaceChildren(body, refreshButton, error);

  function failure(message) { error.textContent = message; error.hidden = !message; }

  async function focus(target) {
    try {
      const result = await rpc("desktop.focus", { target });
      if (closed) return;
      if (!result.ok) failure(result.message || "Hedef kapanmış olabilir. Listeyi yenile.");
      else failure(loadError);
    } catch (reason) {
      if (!closed) { failure(reason.message || "Hedef öne getirilemedi. Bağlantını kontrol et."); toast?.(error.textContent); }
    }
  }

  function icon(app) {
    return app.icon ? h("img", { src: app.icon, alt: "" }) : h("span", { class: "mini-dock__letter", "aria-hidden": "true" }, initial(app.name));
  }

  function renderApps() {
    if (!apps.length) {
      body.replaceChildren(h("p", { class: "muted small" }, loadError ? "Uygulamalar şu an alınamadı." : "Açık uygulama yok."));
      return;
    }
    const tiles = apps.map((app) => {
      const count = appCount(app);
      const sole = soleTarget(app);
      const label = sole ? `${app.name} uygulamasını öne getir` : `${app.name} uygulaması, ${count} öğe`;
      return h("button", {
        type: "button", class: `mini-dock__app${app.active ? " is-active" : ""}`, "data-app": app.name, "aria-label": label,
        "aria-current": app.active ? "true" : undefined,
        onclick: () => (sole ? focus(sole) : open(app.name)),
      }, h("span", { class: "mini-dock__tile" }, icon(app), count > 1 ? h("span", { class: "mini-dock__badge", "aria-hidden": "true" }, String(count)) : null),
      h("span", { class: "mini-dock__name" }, app.name));
    });
    body.replaceChildren(h("nav", { class: "mini-dock__apps", "aria-label": "Uygulamalar" }, tiles));
  }

  function row(item, app) {
    const target = targetOf(item);
    const title = text(item.title, "Başlıksız");
    const isTab = target.kind === "tab";
    const sub = isTab ? host(item.url) : "";
    const iconSrc = safeIcon(item.icon);
    return h("button", {
      type: "button", class: `mini-dock__row${item.active === true ? " is-active" : ""}`,
      "data-target": `${target.kind}:${target.id}${target.kind === "window" ? `:${target.pid}` : ""}`,
      "aria-label": `${isTab ? title : `${app.name}: ${title}`} ${isTab ? "sekmesini" : "penceresini"} öne getir`,
      onclick: () => focus(target),
    }, iconSrc ? h("img", { src: iconSrc, alt: "" }) : h("span", { class: "mini-dock__letter", "aria-hidden": "true" }, initial(title)),
    h("span", { class: "mini-dock__text" }, h("span", { class: "mini-dock__title" }, title), sub ? h("span", { class: "mini-dock__sub" }, sub) : null),
    item.active === true ? h("span", { class: "mini-dock__mark" }, "Etkin") : null);
  }

  function renderApp(app) {
    const needle = query.trim().toLocaleLowerCase("tr");
    const match = (item) => !needle || `${text(item.title)} ${text(item.url)} ${text(item.app)}`.toLocaleLowerCase("tr").includes(needle);
    const windows = app.windows.filter(match);
    const tabs = app.tabs.filter(match);
    const back = h("button", { type: "button", class: "mini-dock__back", "aria-label": "Uygulamalara dön", onclick: () => { current = null; query = ""; render(); } }, "‹ Uygulamalar");
    const header = h("div", { class: "mini-dock__head" }, back, h("strong", {}, app.name), h("span", { class: "muted small" }, `${appCount(app)} öğe`));
    const parts = [header];
    if (appCount(app) > SEARCH_THRESHOLD) {
      const search = h("input", { type: "search", class: "mini-dock__search", placeholder: "Ara…", "aria-label": `${app.name} içinde ara`, value: query });
      search.addEventListener("input", () => { query = search.value; renderApp(app); const next = body.querySelector(".mini-dock__search"); next?.focus(); next?.setSelectionRange(query.length, query.length); });
      parts.push(search);
    }
    const list = h("div", { class: "mini-dock__list" });
    if (windows.length) {
      list.append(h("h3", { class: "mini-dock__group" }, `Pencereler (${windows.length})`), ...windows.map((item) => row(item, app)));
    }
    const byWindow = new Map();
    for (const tab of tabs) {
      const key = Number.isInteger(tab.windowId) ? tab.windowId : 0;
      byWindow.set(key, [...(byWindow.get(key) ?? []), tab]);
    }
    let index = 0;
    for (const [, group] of byWindow) {
      index += 1;
      list.append(h("h3", { class: "mini-dock__group" }, `Pencere ${index} · ${group.length} sekme`), ...group.map((item) => row(item, app)));
    }
    if (!windows.length && !tabs.length) list.append(h("p", { class: "muted small" }, needle ? "Aramayla eşleşen yok." : "Bu uygulamada açık pencere yok."));
    parts.push(list);
    body.replaceChildren(...parts);
  }

  function render() {
    const app = current ? apps.find((item) => item.name === current) : null;
    if (current && !app) current = null; // uygulama kapandı: uygulamalara dön
    if (app) renderApp(app); else renderApps();
  }

  function open(name) { current = name; query = ""; render(); body.querySelector(".mini-dock__back")?.focus(); }

  async function load() {
    try {
      const result = await rpc("desktop.targets");
      if (closed) return;
      if (!result.ok) { apps = []; loadError = result.message || "Masaüstü hedefleri alınamadı."; failure(loadError); render(); return; }
      const payload = result.data || {};
      apps = groupApps(Array.isArray(payload.windows) ? payload.windows : [], Array.isArray(payload.tabs) ? payload.tabs : []);
      loadError = payload.native_error || payload.chrome_error || "";
      failure(loadError);
      render();
    } catch (reason) {
      if (closed) return;
      apps = [];
      loadError = reason.message || "Masaüstü listesi alınamadı. Bağlantını kontrol et.";
      failure(loadError);
      render();
    }
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
