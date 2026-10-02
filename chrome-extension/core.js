// Fusion Browser ortak çekirdeği: sayfa eylemleri ve sekme yönetimi.
// Hem arka plan hizmeti (otomatik bağlantı) hem yan panel (elle bağlantı) kullanır.

const TAB_KEY = "fusionTab";
const LOAD_TIMEOUT_MS = 20000;

export function pageAction(operation, args) {
  // Sayfanın İÇİNDE çalışır (chrome.scripting ile enjekte edilir); dış kapsam yoktur.
  const INTERACTIVE = "button, a[href], input, textarea, select, summary, [role='button'], " +
    "[role='link'], [role='tab'], [role='menuitem'], [role='option'], [role='checkbox'], " +
    "[role='switch'], [role='combobox'], [role='textbox'], [contenteditable='true'], [tabindex='0']";
  const MAX_ELEMENTS = 400;
  const MAX_TEXT = 20000;
  const visibleBox = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && !el.closest("[aria-hidden='true']") &&
      getComputedStyle(el).visibility !== "hidden";
  };
  const safe = (el) => {
    const type = (el.getAttribute("type") || "").toLowerCase();
    const hint = [
      el.getAttribute("name"), el.getAttribute("id"), el.getAttribute("autocomplete"),
      el.getAttribute("aria-label"), el.getAttribute("placeholder"),
    ].filter(Boolean).join(" ").toLowerCase();
    return type !== "password" && !/(password|passwd|otp|one.time|credit.card|cc.number|cvv|cvc)/.test(hint);
  };
  // Erişilebilir ad: yalnız simgesi olan düğmelerin adı etikette, ipucunda ya da simgenin
  // kendisindedir (ölçüldü: Google Ads'te adsız düğme izin kartında "e13" diye göründü).
  const labelledBy = (el) => (el.getAttribute("aria-labelledby") || "").split(/\s+/)
    .map((id) => id && document.getElementById(id)?.textContent).filter(Boolean).join(" ");
  const iconName = (el) => el.querySelector?.("[aria-label]")?.getAttribute("aria-label") ||
    el.querySelector?.("img[alt]")?.getAttribute("alt") || el.querySelector?.("svg title")?.textContent || "";
  const nameOf = (el) => (el.getAttribute("aria-label") || labelledBy(el) || el.innerText || el.textContent ||
    el.value || el.getAttribute("placeholder") || el.getAttribute("title") || el.getAttribute("data-tooltip") ||
    el.getAttribute("mattooltip") || iconName(el) || el.getAttribute("name") || "")
    .replace(/\s+/g, " ").trim().slice(0, 120);
  const refs = globalThis.__fusionRefs || (globalThis.__fusionRefs = []);
  const refOf = (el) => {
    let index = refs.indexOf(el);
    if (index === -1) { refs.push(el); index = refs.length - 1; }
    return `e${index}`;
  };
  // Sayfanın TAMAMI: açık shadow root'lar (web bileşenleri) ve aynı kaynaktan
  // iframe'ler de taranır. Ölçüldü: shadow DOM'daki düğmeler snapshot'ta hiç
  // görünmüyordu ve model "düğme yok" deyip işi bırakıyordu.
  const deepAll = (selector) => {
    const found = [];
    const visit = (root, depth) => {
      if (!root || depth > 6) return;
      found.push(...root.querySelectorAll(selector));
      for (const host of root.querySelectorAll("*")) {
        if (host.shadowRoot) visit(host.shadowRoot, depth + 1);
        if (host.tagName === "IFRAME") {
          let inner = null;
          try { inner = host.contentDocument; } catch { inner = null; }
          if (inner) visit(inner, depth + 1);
        }
      }
    };
    visit(document, 0);
    return found;
  };
  const describe = (el) => {
    const rect = el.getBoundingClientRect();
    const item = {
      ref: refOf(el), tag: el.tagName.toLowerCase(), role: el.getAttribute("role") || "",
      name: nameOf(el), disabled: el.disabled || el.getAttribute("aria-disabled") === "true",
      writable: safe(el) && el.matches("input, textarea, select, [contenteditable='true'], [role='textbox']"),
      in_view: rect.bottom > 0 && rect.top < innerHeight,
    };
    if (el.matches("input[type='checkbox'], input[type='radio'], [role='checkbox'], [role='switch']")) {
      item.checked = el.checked ?? el.getAttribute("aria-checked") === "true";
    }
    if (el.matches("select") && el.selectedOptions?.[0]) item.value = el.selectedOptions[0].text;
    return item;
  };
  const target = () => {
    const match = /^e(\d+)$/.exec(args.ref || "");
    const element = match ? refs[Number(match[1])] : null;
    if (!element || !element.isConnected || !safe(element)) {
      throw new Error("Öğe artık bulunamadı veya hassas alan. Sayfayı yeniden okuyun (chrome_page/chrome_find).");
    }
    return element;
  };
  // Yalnız GÖRÜNEN metin. `innerText` saydam, ekran dışına itilmiş ya da aria-hidden
  // şablonları da verir (ölçüldü: Google Ads'in gizli "ad blocker" uyarısı modeli yanılttı).
  const BLOCK = /^(block|flex|grid|table|table-row|list-item|flow-root)$/;
  const visibleText = (limit = MAX_TEXT) => {
    const shown = new Map();
    const isShown = (el) => {
      if (!el || el === document.body) return true;
      if (shown.has(el)) return shown.get(el);
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      // aria-hidden GÖRSEL gizleme değildir: açılır pencere açıkken Google Ads ana içeriği
      // (kampanya tablosu, bakiye uyarısı) ekran okuyucudan gizler ama ekranda gösterir.
      const collapsed = (rect.width === 0 || rect.height === 0) &&
        /hidden|clip/.test(`${style.overflow} ${style.overflowX} ${style.overflowY}`);
      const ok = style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) !== 0 &&
        !collapsed && !(rect.right <= 0 && rect.width > 0) && isShown(el.parentElement);
      shown.set(el, ok);
      return ok;
    };
    const parts = [];
    let length = 0;
    const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node && length < limit; node = walker.nextNode()) {
      const text = node.nodeValue.replace(/\s+/g, " ").trim();
      const parent = node.parentElement;
      if (!text || !parent || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(parent.tagName) || !isShown(parent)) continue;
      parts.push(BLOCK.test(getComputedStyle(parent).display) ? `\n${text}` : ` ${text}`);
      length += text.length + 1;
    }
    return parts.join("").replace(/\n\s*\n+/g, "\n").trim().slice(0, limit);
  };
  if (operation === "snapshot") {
    globalThis.__fusionRefs = [];
    const all = deepAll(INTERACTIVE).filter((el) => visibleBox(el) && safe(el));
    // Görünür alandakiler önce: uzun sayfada model önce ekranda olanı görmeli.
    all.sort((a, b) => Number(b.getBoundingClientRect().top >= 0 && b.getBoundingClientRect().top < innerHeight) -
      Number(a.getBoundingClientRect().top >= 0 && a.getBoundingClientRect().top < innerHeight));
    return {
      title: document.title, url: location.href,
      scroll: { y: Math.round(scrollY), height: document.documentElement.scrollHeight, viewport: innerHeight },
      text: visibleText(),
      elements: all.slice(0, MAX_ELEMENTS).map(describe),
      truncated: all.length > MAX_ELEMENTS,
    };
  }
  if (operation === "find") {
    const query = String(args.query || "").toLocaleLowerCase("tr").trim();
    if (!query) throw new Error("Aranacak metni verin.");
    // Modeller "campaigns, kampanyalar" gibi birden çok terimle arıyor; her biri ayrı
    // aranır, biri tutarsa yeter (ölçüldü: tek öbek sanılıp hep 0 sonuç dönüyordu).
    const terms = query.split(/[,|]/).map((term) => term.trim()).filter(Boolean);
    const hits = deepAll(INTERACTIVE + ", label, h1, h2, h3, td, li, span, p, div")
      .filter((el) => safe(el) && visibleBox(el))
      .filter((el) => { const name = nameOf(el).toLocaleLowerCase("tr"); return terms.some((term) => name.includes(term)); })
      // En içteki eşleşme: "div > span > button" zincirinde düğmeyi döndür.
      .filter((el, _, list) => !list.some((other) => other !== el && el.contains(other)))
      .slice(0, 20);
    const result = { query, matches: hits.map(describe) };
    if (!hits.length) {
      result.ipucu = "Eşleşme yok. Sayfada ne olduğunu görmek için chrome_page'i query olmadan çağır; " +
        "sayfadaki gerçek yazıyı ara ya da adresi biliyorsan doğrudan git.";
    }
    return result;
  }
  if (operation === "describe") {
    // Fusion tıklamadan ÖNCE sorar: "Gönder/Sil/Satın al" gibi düğmeler onay ister.
    const element = target();
    const type = (element.getAttribute("type") || "").toLowerCase();
    // Gerçek bir adrese giden bağlantı yalnız gezinir ("#" ve javascript: iş yapabilir).
    const link = element.closest("a[href]");
    const href = link ? link.getAttribute("href").trim().toLowerCase() : "";
    return {
      name: nameOf(element), tag: element.tagName.toLowerCase(), type, role: element.getAttribute("role") || "",
      submit: type === "submit" || (element.tagName === "BUTTON" && !type && Boolean(element.form)),
      link: Boolean(href) && !href.startsWith("#") && !href.startsWith("javascript:"),
    };
  }
  if (operation === "describe_key") {
    // Fusion Enter'a basmadan ÖNCE sorar: arama kutusunda Enter gezinmedir, mesaj
    // kutusunda ya da "Gönder/Satın al" düğmeli formda göndermedir.
    const element = args.ref ? target() : (document.activeElement || document.body);
    const form = element.form || element.closest?.("form") || null;
    const submit = form?.querySelector("button[type='submit'], input[type='submit'], button:not([type])");
    const type = (element.getAttribute("type") || "").toLowerCase();
    const role = element.getAttribute("role") || "";
    const hint = ["placeholder", "name", "aria-label", "title"].map((a) => element.getAttribute(a) || "").join(" ");
    return {
      tag: element.tagName.toLowerCase(), type, role, name: nameOf(element), hint,
      search: type === "search" || role === "searchbox" || role === "combobox" ||
        Boolean(element.closest?.("[role='search']")) || /\b(ara|arama|search|bul|filtre|filter)\b/i.test(hint) ||
        /search|arama/i.test(form?.getAttribute("action") || ""),
      editable: Boolean(element.matches?.("textarea, [contenteditable='true'], [contenteditable=''], [role='textbox']")),
      in_form: Boolean(form),
      submit_name: submit ? nameOf(submit) : "",
    };
  }
  if (operation === "text_page") {
    // Uzun sayfanın TAMAMI parça parça (Claude'un get_page_text'i gibi).
    const PAGE = MAX_TEXT;
    const page = Math.max(1, Number(args.page) || 1);
    const full = visibleText(PAGE * page + 1);
    return { page, text: full.slice(PAGE * (page - 1), PAGE * page), has_more: full.length > PAGE * page };
  }
  if (operation === "hover") {
    const element = target();
    element.scrollIntoView({ block: "center" });
    const rect = element.getBoundingClientRect();
    const point = { bubbles: true, composed: true, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
    for (const type of ["pointerover", "pointerenter", "mouseover", "mouseenter", "mousemove"]) {
      element.dispatchEvent(new (type.startsWith("pointer") && globalThis.PointerEvent ? PointerEvent : MouseEvent)(type, point));
    }
    return { hovered: args.ref, name: nameOf(element) };
  }
  if (operation === "describe_at" || operation === "click_at") {
    // Ekran görüntüsündeki koordinat (CSS piksel): Claude'un computer tıklaması gibi.
    const x = Number(args.x);
    const y = Number(args.y);
    const element = Number.isFinite(x) && Number.isFinite(y) ? document.elementFromPoint(x, y) : null;
    if (!element || !safe(element)) throw new Error("Bu noktada tıklanabilir öğe yok ya da hassas alan.");
    if (operation === "describe_at") {
      const link = element.closest("a[href]");
      const href = link ? link.getAttribute("href").trim().toLowerCase() : "";
      const type = (element.getAttribute("type") || "").toLowerCase();
      return {
        name: nameOf(element), tag: element.tagName.toLowerCase(), type, role: element.getAttribute("role") || "",
        submit: type === "submit" || (element.tagName === "BUTTON" && !type && Boolean(element.form)),
        link: Boolean(href) && !href.startsWith("#") && !href.startsWith("javascript:"),
      };
    }
    const point = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, button: 0 };
    for (const type of ["pointerover", "pointerdown", "mousedown", "pointerup", "mouseup"]) {
      element.dispatchEvent(new (type.startsWith("pointer") && globalThis.PointerEvent ? PointerEvent : MouseEvent)(type, point));
    }
    element.click();
    return { clicked_at: [x, y], name: nameOf(element), url: location.href };
  }
  if (operation === "click") {
    const element = target();
    element.scrollIntoView({ block: "center", inline: "center" });
    const rect = element.getBoundingClientRect();
    const point = { bubbles: true, cancelable: true, composed: true, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2, button: 0 };
    for (const type of ["pointerover", "pointerdown", "mousedown", "pointerup", "mouseup"]) {
      element.dispatchEvent(new (type.startsWith("pointer") && globalThis.PointerEvent ? PointerEvent : MouseEvent)(type, point));
    }
    element.click();
    return { clicked: args.ref, name: nameOf(element), url: location.href };
  }
  if (operation === "type") {
    const element = target();
    if (!element.matches("input, textarea, select, [contenteditable='true'], [role='textbox']")) {
      throw new Error("Bu öğeye metin yazılamaz.");
    }
    if (element.matches("select")) throw new Error("Seçim kutusu için chrome_select kullanın.");
    element.scrollIntoView({ block: "center" });
    element.focus();
    if (element.isContentEditable || element.getAttribute("role") === "textbox") {
      document.execCommand("selectAll", false);
      if (!document.execCommand("insertText", false, args.text)) element.textContent = args.text;
    } else {
      // React kontrollü alanlar değeri kendi ayarlayıcısından okur; doğrudan
      // `value =` atamasını görmez ve metni bir sonraki çizimde siler.
      const proto = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(element, args.text);
    }
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    // Yazılanı GERİ OKU: bazı editörler (maskeli alan, zengin metin) ilk yöntemi
    // sessizce yutar. Tutmadıysa tuş tuş yazma denenir; yazma tekrarlanabilir bir
    // işlemdir (değeri ayarlar), ikinci deneme yan etki çoğaltmaz.
    const current = () => (element.isContentEditable || element.getAttribute("role") === "textbox"
      ? element.innerText : element.value) ?? "";
    let verified = current().replace(/\s+/g, " ").trim() === String(args.text).replace(/\s+/g, " ").trim();
    if (!verified) {
      element.focus();
      if (element.isContentEditable) {
        element.textContent = "";
      } else {
        const proto = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(element, "");
      }
      for (const char of String(args.text)) {
        element.dispatchEvent(new KeyboardEvent("keydown", { key: char, bubbles: true }));
        if (!document.execCommand("insertText", false, char)) {
          if (element.isContentEditable) element.textContent += char;
          else element.value += char;
        }
        element.dispatchEvent(new InputEvent("input", { bubbles: true, data: char, inputType: "insertText" }));
        element.dispatchEvent(new KeyboardEvent("keyup", { key: char, bubbles: true }));
      }
      element.dispatchEvent(new Event("change", { bubbles: true }));
      verified = current().replace(/\s+/g, " ").trim() === String(args.text).replace(/\s+/g, " ").trim();
    }
    return { typed: args.ref, length: args.text.length, verified, value: verified ? undefined : current().slice(0, 200) };
  }
  if (operation === "select") {
    const element = target();
    if (!element.matches("select")) throw new Error("Bu öğe bir seçim kutusu değil.");
    const wanted = String(args.value || "").toLocaleLowerCase("tr");
    const option = [...element.options].find((opt) =>
      opt.value.toLocaleLowerCase("tr") === wanted || opt.text.toLocaleLowerCase("tr").includes(wanted));
    if (!option) throw new Error(`Seçenek bulunamadı: ${args.value}`);
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set?.call(element, option.value);
    element.dispatchEvent(new Event("change", { bubbles: true }));
    return { selected: option.text };
  }
  if (operation === "key") {
    const allowed = ["Enter", "Escape", "Tab", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Backspace", "Space"];
    if (!allowed.includes(args.key)) throw new Error(`Desteklenmeyen tuş: ${args.key}`);
    const element = args.ref ? target() : (document.activeElement || document.body);
    const key = args.key === "Space" ? " " : args.key;
    for (const type of ["keydown", "keypress", "keyup"]) {
      element.dispatchEvent(new KeyboardEvent(type, { key, code: args.key, bubbles: true, cancelable: true }));
    }
    if (args.key === "Enter" && element.form && element.matches("input")) element.form.requestSubmit?.();
    return { key: args.key };
  }
  if (operation === "scroll") {
    if (args.ref) {
      target().scrollIntoView({ block: "center" });
    } else {
      const amount = Math.round(innerHeight * 0.8) * (args.direction === "up" ? -1 : 1);
      scrollBy({ top: amount, behavior: "instant" });
    }
    return { y: Math.round(scrollY), height: document.documentElement.scrollHeight };
  }
  if (operation === "signature") {
    // Tıklamanın sayfada bir şey değiştirip değiştirmediğini anlamak için küçük imza.
    const active = document.activeElement;
    return {
      url: location.href,
      title: document.title,
      text: (document.body?.innerText || "").length,
      nodes: document.getElementsByTagName("*").length,
      active: active ? `${active.tagName}:${nameOf(active)}` : "",
      dialogs: deepAll("dialog[open], [role='dialog'], [role='alertdialog'], [aria-modal='true']").filter(visibleBox).length,
      expanded: deepAll("[aria-expanded='true']").length,
      checked: deepAll("input:checked, [aria-checked='true'], [aria-selected='true'], [aria-pressed='true']").length,
    };
  }
  if (operation === "upload") {
    const element = target();
    if (!element.matches("input[type='file']")) throw new Error("Bu öğe bir dosya seçme alanı değil.");
    const files = (args.files || []).map((file) => {
      const bytes = Uint8Array.from(atob(file.data), (char) => char.charCodeAt(0));
      return new File([bytes], file.name, { type: file.mime || "application/octet-stream" });
    });
    if (!files.length) throw new Error("Yüklenecek dosya yok.");
    if (files.length > 1 && !element.multiple) throw new Error("Bu alan tek dosya kabul ediyor.");
    const transfer = new DataTransfer();
    files.forEach((file) => transfer.items.add(file));
    element.files = transfer.files;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    return { uploaded: files.map((file) => file.name), count: element.files.length };
  }
  if (operation === "assets") {
    // Sayfanın görsel varlıkları: gerçek ölçüleriyle görseller, CSS arka plan
    // görselleri, paylaşım görseli ve sitenin renk/yazı tipi paleti. Fusion
    // bunları "bu siteye benzeyen bir site yap" ya da görsel toplama işinde kullanır.
    const absolute = (value) => { try { return new URL(value, location.href).href; } catch { return ""; } };
    const images = [...document.images]
      .filter((img) => (img.currentSrc || img.src) && !(img.currentSrc || img.src).startsWith("data:"))
      .map((img) => ({
        src: absolute(img.currentSrc || img.src), alt: (img.alt || "").slice(0, 160),
        width: img.naturalWidth, height: img.naturalHeight, visible: visibleBox(img),
      }))
      .filter((item) => item.width >= 48 && item.height >= 48);
    const backgrounds = [];
    for (const el of document.querySelectorAll("body *")) {
      if (backgrounds.length >= 60) break;
      const value = getComputedStyle(el).backgroundImage;
      const match = value && value !== "none" ? /url\(["']?([^"')]+)["']?\)/.exec(value) : null;
      if (match && !match[1].startsWith("data:")) backgrounds.push(absolute(match[1]));
    }
    const meta = (name) => document.querySelector(`meta[property='${name}'], meta[name='${name}']`)?.content || "";
    const icon = document.querySelector("link[rel~='icon']")?.href || "";
    const style = (selector) => {
      const el = document.querySelector(selector);
      if (!el) return null;
      const css = getComputedStyle(el);
      return { color: css.color, background: css.backgroundColor, font: css.fontFamily.split(",")[0].trim(), size: css.fontSize };
    };
    const unique = (list) => [...new Set(list.filter(Boolean))];
    return {
      url: location.href,
      title: document.title,
      images: unique(images.map((item) => item.src)).map((src) => images.find((item) => item.src === src)).slice(0, 150),
      backgrounds: unique(backgrounds),
      og_image: absolute(meta("og:image")),
      icon,
      palette: { body: style("body"), heading: style("h1, h2"), link: style("a"), button: style("button, .btn, [role='button']") },
    };
  }
  if (operation === "text") {
    return { found: (document.body?.innerText || "").includes(String(args.text || "")), url: location.href };
  }
  throw new Error("Desteklenmeyen sayfa eylemi.");
}

export async function getSelected() {
  return (await chrome.storage.session.get(TAB_KEY))[TAB_KEY] || null;
}

async function setSelected(tab) {
  const origin = new URL(tab.pendingUrl || tab.url).origin;
  const value = { id: tab.id, origin, title: tab.title || origin };
  await chrome.storage.session.set({ [TAB_KEY]: value });
  return value;
}

export async function clearSelected() {
  await chrome.storage.session.remove(TAB_KEY);
}

async function permitted(origin) {
  return /^https?:/.test(origin) && chrome.permissions.contains({ origins: [`${origin}/*`] });
}

function waitForLoad(tabId, timeout = LOAD_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const done = () => { chrome.tabs.onUpdated.removeListener(listener); clearTimeout(timer); resolve(); };
    const listener = (id, info) => { if (id === tabId && info.status === "complete") done(); };
    const timer = setTimeout(done, timeout);
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId).then((tab) => { if (tab.status === "complete") done(); }).catch(done);
  });
}

/** Kullanıcının seçtiği etkin sekmeyi bağla (paneldeki "Bu sekmeye izin ver"). */
export async function selectActiveTab({ request = true } = {}) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id || !tab.url) throw new Error("Açık web sekmesi bulunamadı.");
  const url = new URL(tab.url);
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("Yalnız HTTP ve HTTPS sayfaları bağlanabilir.");
  const pattern = `${url.origin}/*`;
  const allowed = request ? await chrome.permissions.request({ origins: [pattern] })
    : await chrome.permissions.contains({ origins: [pattern] });
  if (!allowed) throw new Error("Bu site için Chrome izni verilmedi.");
  return setSelected(tab);
}

export async function checkedTab() {
  let selected = await getSelected();
  if (!selected) {
    // Seçili sekme yoksa etkin sekme izinliyse ona bağlan (Claude in Chrome gibi).
    try { selected = await selectActiveTab({ request: false }); } catch {
      throw new Error("Bağlı sekme yok. chrome_action ile 'open' (adres) ya da 'tabs' kullan.");
    }
  }
  let tab;
  try { tab = await chrome.tabs.get(selected.id); } catch {
    await clearSelected();
    throw new Error("Bağlı sekme kapandı. 'tabs' ile listele ya da 'open' ile yeni sekme aç.");
  }
  const origin = new URL(tab.pendingUrl || tab.url).origin;
  if (origin !== selected.origin) {
    if (!await permitted(origin)) {
      await clearSelected();
      throw new Error("Sekme izin verilmeyen bir siteye geçti. Yeni site için panelden izin verin.");
    }
    await setSelected(tab);
  }
  return tab;
}

async function runInTab(tab, operation, args) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, func: pageAction, args: [operation, args],
  });
  return result;
}

export async function execute(command) {
  const veri = command.veri || {};
  if (command.islem === "tabs") {
    const tabs = await chrome.tabs.query({});
    const selected = await getSelected();
    return {
      tabs: tabs.filter((t) => /^https?:/.test(t.url || "")).slice(0, 60).map((t) => ({
        id: t.id, title: (t.title || "").slice(0, 100), url: t.url, active: t.active,
        bound: t.id === selected?.id,
      })),
    };
  }
  if (command.islem === "tab_open") {
    const destination = new URL(veri.url);
    if (!await permitted(destination.origin)) {
      throw new Error(`${destination.origin} için Chrome izni yok. Panelden "Chrome iznini iste" ile verin.`);
    }
    const tab = await chrome.tabs.create({ url: destination.href, active: true });
    await waitForLoad(tab.id);
    const bound = await setSelected(await chrome.tabs.get(tab.id));
    return { opened: bound.id, url: destination.href };
  }
  if (command.islem === "tab_select") {
    const tab = await chrome.tabs.get(Number(veri.id));
    const origin = new URL(tab.url).origin;
    if (!await permitted(origin)) throw new Error("Bu sekmenin sitesi için Chrome izni yok.");
    await setSelected(tab);
    return { selected: tab.id, url: tab.url };
  }
  if (command.islem === "tab_close") {
    const closing = await chrome.tabs.get(Number(veri.id));
    await chrome.tabs.remove(closing.id);
    if ((await getSelected())?.id === closing.id) await clearSelected();
    return { closed: closing.id };
  }
  const tab = await checkedTab();
  if (command.islem === "history") {
    if (veri.dir === "back") await chrome.tabs.goBack(tab.id);
    else if (veri.dir === "forward") await chrome.tabs.goForward(tab.id);
    else await chrome.tabs.reload(tab.id);
    await new Promise((resolve) => setTimeout(resolve, 300));
    await waitForLoad(tab.id);
    const now = await chrome.tabs.get(tab.id);
    if (now.url && /^https?:/.test(now.url)) await setSelected(now);
    return { url: now.url };
  }
  if (command.islem === "screenshot") {
    if (!await chrome.permissions.contains({ origins: ["<all_urls>"] })) {
      throw new Error("Ekran görüntüsü için paneldeki Chrome iznini verin.");
    }
    if (!tab.active) await chrome.tabs.update(tab.id, { active: true });
    const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 65 });
    if (image.length > 4_000_000) throw new Error("Ekran görüntüsü çok büyük.");
    // Sekmenin CSS piksel boyutu: Fusion görüntü koordinatını sayfa ölçeğine çevirir.
    return { image, width: tab.width, height: tab.height };
  }
  if (command.islem === "navigate") {
    const destination = new URL(veri.url);
    if (destination.origin !== new URL(tab.url).origin && !await permitted(destination.origin)) {
      throw new Error(`${destination.origin} için Chrome izni yok. Panelden izin verin.`);
    }
    await chrome.tabs.update(tab.id, { url: destination.href });
    await waitForLoad(tab.id);
    await setSelected(await chrome.tabs.get(tab.id));
    return { url: destination.href };
  }
  if (command.islem === "wait") {
    const limit = Math.min(Number(veri.timeout_ms) || 10000, 25000);
    const started = Date.now();
    while (Date.now() - started < limit) {
      if ((await runInTab(tab, "text", veri))?.found) return { found: true, waited_ms: Date.now() - started };
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    return { found: false, waited_ms: limit };
  }
  const acts = command.islem === "click" || command.islem === "click_at" || command.islem === "key";
  // Eylemden ÖNCE ve SONRA imza: eylem sayfada iz bırakmadıysa model bunu bilmeli.
  // Otomatik ikinci tıklama YAPILMAZ: sepete ekle gibi işlemler iki kez çalışabilir.
  const before = acts ? await runInTab(tab, "signature", {}).catch(() => null) : null;
  const result = await runInTab(tab, command.islem, veri);
  if (acts) {
    // Tıklama yeni sayfa açabilir; sonraki okuma yarım sayfa görmesin.
    await new Promise((resolve) => setTimeout(resolve, 300));
    await waitForLoad(tab.id, 8000);
    const after = await runInTab(tab, "signature", {}).catch(() => null);
    if (before && after && result && typeof result === "object") {
      result.changed = JSON.stringify(before) !== JSON.stringify(after);
    }
  }
  return result;
}
