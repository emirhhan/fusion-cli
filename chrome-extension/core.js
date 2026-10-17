// Fusion Browser ortak çekirdeği: sayfa eylemleri ve sekme yönetimi.
// Hem arka plan hizmeti (otomatik bağlantı) hem yan panel (elle bağlantı) kullanır.

const TAB_KEY = "fusionTab";
const LOAD_TIMEOUT_MS = 20000;

export function pageAction(operation, args) {
  const calistir = () => {
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
  const refElement = (ref) => {
    const match = /^e(\d+)$/.exec(ref || "");
    const element = match ? refs[Number(match[1])] : null;
    if (!element || !element.isConnected || !safe(element)) {
      throw new Error("Öğe artık bulunamadı veya hassas alan. Sayfayı chrome_page ile yeniden oku ve güncel ref kullan.");
    }
    return element;
  };
  const MouseKind = (type) => (type.startsWith("pointer") && globalThis.PointerEvent ? PointerEvent : MouseEvent);
  // Tıklama türleri: tek (varsayılan), çift ve sağ. Sağ tık yalnız bağlam menüsü olayını
  // gönderir; `click()` ÇAĞRILMAZ (sağ tık bağlantıya/düğmeye basmış olmamalı).
  const pressAt = (element, x, y, kind) => {
    const right = kind === "right";
    const base = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y,
      button: right ? 2 : 0, buttons: right ? 2 : 1 };
    const rounds = kind === "triple" ? 3 : kind === "double" ? 2 : 1;
    for (let detail = 1; detail <= rounds; detail += 1) {
      for (const type of ["pointerover", "pointerdown", "mousedown", "pointerup", "mouseup"]) {
        element.dispatchEvent(new (MouseKind(type))(type, { ...base, detail }));
      }
      if (!right) element.dispatchEvent(new MouseEvent("click", { ...base, detail }));
    }
    if (kind === "double") element.dispatchEvent(new MouseEvent("dblclick", { ...base, detail: 2 }));
    if (right) element.dispatchEvent(new MouseEvent("contextmenu", base));
    if (kind === "triple") {
      // Üç tık satırı/paragrafı seçer: alan ise içeriğini, değilse öğenin metnini.
      if (typeof element.select === "function") element.select();
      else getSelection()?.selectAllChildren(element);
    }
  };
  const target = () => {
    const match = /^e(\d+)$/.exec(args.ref || "");
    const element = match ? refs[Number(match[1])] : null;
    if (!element || !element.isConnected || !safe(element)) {
      throw new Error("Öğe artık bulunamadı veya hassas alan. Sayfayı chrome_page ile yeniden oku ve güncel ref kullan.");
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
    // Liste YERİNDE boşaltılır. Ölçüldü (4 Ekim 2026): yeni dizi atanıyordu; `refs`
    // eski diziyi tuttuğu için öğeler oraya yazıldı, sonraki tıklama boş diziye baktı
    // ve snapshot'tan hemen sonraki her ref tıklaması "bulunamadı" dedi.
    refs.length = 0;
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
    pressAt(element, x, y, args.kind);
    return { clicked_at: [x, y], kind: args.kind || "single", name: nameOf(element), url: location.href };
  }
  if (operation === "click") {
    const element = target();
    element.scrollIntoView({ block: "center", inline: "center" });
    const rect = element.getBoundingClientRect();
    pressAt(element, rect.left + rect.width / 2, rect.top + rect.height / 2, args.kind);
    return { clicked: args.ref, kind: args.kind || "single", name: nameOf(element), url: location.href };
  }
  if (operation === "type") {
    // `find` etiketi (label) de bulur; modelin yazmak istediği, etiketin bağlı olduğu alandır.
    // `ref` yoksa odaktaki alana yazılır (Claude'un computer type'ı gibi).
    const labelled = args.ref ? target() : document.activeElement;
    if (!labelled || labelled === document.body || !safe(labelled)) {
      throw new Error("Odakta yazılabilir alan yok. Önce alana tıkla ya da ref ver.");
    }
    const element = labelled.tagName === "LABEL" && labelled.control ? labelled.control : labelled;
    if (!element.matches("input, textarea, select, [contenteditable='true'], [role='textbox']")) {
      throw new Error("Bu öğeye metin yazılamaz.");
    }
    // Seçim kutusuna "yazmak" seçenek seçmektir (Playwright aracıyla aynı davranış).
    // Eskiden var olmayan bir araca yönlendiriyordu ve model boşa tur harcıyordu.
    if (element.matches("select")) return pageAction("select", { ref: args.ref, value: args.text });
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
    const labelled = target();
    const element = labelled.tagName === "LABEL" && labelled.control ? labelled.control : labelled;
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
    // "Enter", "ctrl+a", "Shift+Tab", "Meta+Enter" gibi. Olaylar sayfa içinde üretilir:
    // gerçek işletim sistemi kısayolu (kopyala, yapıştır) DEĞİLDİR; tümünü seç ve Tab/ok
    // gezinmesi çalışır.
    const NAMED = ["Enter", "Escape", "Tab", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight",
      "Backspace", "Delete", "Space", "Home", "End", "PageUp", "PageDown"];
    const parts = String(args.key || "").split("+").map((p) => p.trim()).filter(Boolean);
    const main = parts.pop() || "";
    const mods = parts.map((p) => p.toLowerCase());
    if (mods.some((m) => !["ctrl", "control", "meta", "cmd", "shift", "alt"].includes(m))) {
      throw new Error(`Desteklenmeyen tuş: ${args.key}`);
    }
    const named = NAMED.find((n) => n.toLowerCase() === main.toLowerCase());
    if (!named && !(main.length === 1 && mods.length)) throw new Error(`Desteklenmeyen tuş: ${args.key}`);
    const element = args.ref ? target() : (document.activeElement || document.body);
    const key = named === "Space" ? " " : named || main;
    const init = { key, code: named || `Key${main.toUpperCase()}`, bubbles: true, cancelable: true,
      ctrlKey: mods.includes("ctrl") || mods.includes("control"), metaKey: mods.includes("meta") || mods.includes("cmd"),
      shiftKey: mods.includes("shift"), altKey: mods.includes("alt") };
    for (const type of ["keydown", "keypress", "keyup"]) element.dispatchEvent(new KeyboardEvent(type, init));
    if ((init.ctrlKey || init.metaKey) && main.toLowerCase() === "a") {
      if (typeof element.select === "function") element.select(); else document.execCommand("selectAll", false);
    }
    if (named === "Enter" && !mods.length && element.form && element.matches("input")) element.form.requestSubmit?.();
    return { key: args.key };
  }
  if (operation === "check") {
    // Onay/radyo kutusunu İSTENEN duruma getirir (tıklayıp tersine çevirme riski olmadan).
    const labelled = target();
    const element = labelled.tagName === "LABEL" && labelled.control ? labelled.control : labelled;
    if (!element.matches("input[type='checkbox'], input[type='radio'], [role='checkbox'], [role='switch']")) {
      throw new Error("Bu öğe bir onay kutusu değil.");
    }
    const wanted = args.value !== false && args.value !== "false";
    const now = element.matches("input") ? element.checked : element.getAttribute("aria-checked") === "true";
    if (now !== wanted) element.click();
    const after = element.matches("input") ? element.checked : element.getAttribute("aria-checked") === "true";
    return { checked: after, name: nameOf(element) };
  }
  if (operation === "drag") {
    // Kaynak ref'ten hedef ref'e ya da (x,y) noktasına: fare olayları ve HTML5 sürükle-bırak.
    const source = target();
    source.scrollIntoView({ block: "center", inline: "center" });
    const from = source.getBoundingClientRect();
    const sx = from.left + from.width / 2;
    const sy = from.top + from.height / 2;
    let destination;
    let dx;
    let dy;
    if (args.to_ref) {
      destination = refElement(args.to_ref);
      const to = destination.getBoundingClientRect();
      dx = to.left + to.width / 2;
      dy = to.top + to.height / 2;
    } else {
      dx = Number(args.x);
      dy = Number(args.y);
      destination = Number.isFinite(dx) && Number.isFinite(dy) ? document.elementFromPoint(dx, dy) : null;
      if (!destination || !safe(destination)) throw new Error("Bırakılacak noktada öğe yok ya da hassas alan.");
    }
    const mouse = (el, type, x, y) => el.dispatchEvent(new (MouseKind(type))(type,
      { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, button: 0, buttons: type.endsWith("up") ? 0 : 1 }));
    const transfer = globalThis.DataTransfer ? new DataTransfer() : null;
    const dnd = (el, type, x, y) => el.dispatchEvent(new DragEvent(type,
      { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, dataTransfer: transfer }));
    mouse(source, "pointerdown", sx, sy);
    mouse(source, "mousedown", sx, sy);
    if (source.draggable || source.closest("[draggable='true']")) {
      dnd(source, "dragstart", sx, sy);
      dnd(destination, "dragenter", dx, dy);
      dnd(destination, "dragover", dx, dy);
      dnd(destination, "drop", dx, dy);
      dnd(source, "dragend", dx, dy);
    }
    mouse(destination, "pointermove", dx, dy);
    mouse(destination, "mousemove", dx, dy);
    mouse(destination, "pointerup", dx, dy);
    mouse(destination, "mouseup", dx, dy);
    return { dragged: args.ref, name: nameOf(source), to: nameOf(destination), url: location.href };
  }
  if (operation === "wheel") {
    // Fare tekerleği: öğenin (ya da sayfanın) üstünde dx, dy piksel; kaydırılabilir üst öğe kayar.
    const element = args.ref ? target() : (document.scrollingElement || document.documentElement);
    const rect = element.getBoundingClientRect();
    const dy = Math.max(-5000, Math.min(5000, Number(args.dy) || 0));
    const dx = Math.max(-5000, Math.min(5000, Number(args.dx) || 0));
    const event = new WheelEvent("wheel", { bubbles: true, cancelable: true, composed: true,
      deltaX: dx, deltaY: dy, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 });
    const handled = !element.dispatchEvent(event);
    if (!handled) {
      let node = element;
      while (node && node !== document.documentElement && !(node.scrollHeight > node.clientHeight + 1 &&
        /(auto|scroll)/.test(getComputedStyle(node).overflowY))) node = node.parentElement;
      (node && node !== document.documentElement ? node : window).scrollBy({ top: dy, left: dx, behavior: "instant" });
    }
    return { wheel: [dx, dy], y: Math.round(scrollY) };
  }
  if (operation === "scroll") {
    if (args.ref) {
      target().scrollIntoView({ block: "center" });
    } else {
      const sign = args.direction === "up" || args.direction === "left" ? -1 : 1;
      const horizontal = args.direction === "left" || args.direction === "right";
      const amount = Math.max(1, Math.min(10000, Number(args.amount) || Math.round((horizontal ? innerWidth : innerHeight) * 0.8))) * sign;
      scrollBy(horizontal ? { left: amount, behavior: "instant" } : { top: amount, behavior: "instant" });
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
  // <fusion-design>
  // Sayfanın TASARIM SİSTEMİNİ ölç: yazı tipleri, renkler, tipografi ölçeği,
  // bileşenler (başlık, menü, kart, buton, fiyat), görseller ve sayfa yapısı.
  // Fusion bunu "bu siteye benzeyen bir site yap" işinde tahmin yerine ölçü olarak
  // kullanır. Tek kaynak: tools/assets/design_probe.js; core.js aynısını taşır.
  const designProbe = (limits) => {
    const MAX_COMPONENTS = limits.components || 12;
    const MAX_TEXT_BLOCKS = limits.texts || 60;
    const MAX_IMAGES = limits.images || 120;
    const MAX_SECTIONS = limits.sections || 16;
    const MAX_PRODUCTS = limits.products || 24;
    const PRICE = /(\d[\d.,]*\s?(₺|TL|TRY|\$|€|£))|((₺|\$|€|£)\s?\d)/;
    const abs = (value) => { try { return new URL(value, location.href).href; } catch { return ""; } };
    const shown = (el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none";
    };
    const textOf = (el) => (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    const count = (map, key, by = 1) => { if (key) map.set(key, (map.get(key) || 0) + by); };
    const top = (map, n) => [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n)
      .map(([value, weight]) => ({ value, weight }));
    const typo = (el) => {
      if (!el) return null;
      const cs = getComputedStyle(el);
      return {
        family: cs.fontFamily, size: cs.fontSize, weight: cs.fontWeight, line: cs.lineHeight,
        spacing: cs.letterSpacing, transform: cs.textTransform, color: cs.color,
      };
    };
    const box = (el) => {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return {
        width: Math.round(r.width), height: Math.round(r.height), background: cs.backgroundColor,
        color: cs.color, radius: cs.borderRadius, border: cs.border, shadow: cs.boxShadow,
        padding: cs.padding, gap: cs.gap, display: cs.display, font: typo(el),
      };
    };
    // Kart imzası: etiket + ilk iki KALICI sınıf. Rakamlı (post-218, product_cat-47) ve konum
    // sınıfları (first, last) karta özgüdür; ölçüldü (17. kabul koşusu): WooCommerce'in 24
    // kartı bu yüzden hiç gruplanmadı, mağaza sayfasında "0 ürün" ölçüldü.
    const VOLATILE_CLASS = /\d|^(first|last|odd|even|active|current|selected|is-.*)$/;
    const signature = (el) => `${el.tagName}.${[...el.classList]
      .filter((name) => !VOLATILE_CLASS.test(name)).slice(0, 2).join(".")}`;
    const trimHtml = (el, max) => {
      const clone = el.cloneNode(true);
      clone.querySelectorAll("script, style, svg path").forEach((n) => n.remove());
      // Kaynak sitenin satır içi olay kodu (onclick=…) örnekten çıkarılır. Ölçüldü (3 Ekim
      // 2026, 16. kabul koşusu): model örnekteki `PrimeWidgets…toggleWishlist` çağrısını
      // taklit edip sepet/favori işlemlerini kaynak sitenin canlı API'sine bağladı.
      clone.querySelectorAll("*").forEach((n) => {
        for (const attr of [...n.attributes]) {
          if (/^on/i.test(attr.name) || /^(javascript:)/i.test(attr.value)) n.removeAttribute(attr.name);
        }
      });
      return clone.outerHTML.replace(/\s+/g, " ").slice(0, max);
    };

    // Yazı tipleri: kullanım ağırlığı + @font-face kaynakları (+ Google Fonts bağlantıları).
    const families = new Map();
    const colors = new Map();
    const backgrounds = new Map();
    const all = [...document.querySelectorAll("body *")].filter(shown).slice(0, 4000);
    for (const el of all) {
      const cs = getComputedStyle(el);
      const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (ownText) {
        count(families, cs.fontFamily.split(",")[0].replace(/["']/g, "").trim(), textOf(el).length);
        count(colors, cs.color, textOf(el).length);
      }
      if (cs.backgroundColor && !/rgba\(0, 0, 0, 0\)|transparent/.test(cs.backgroundColor)) {
        const r = el.getBoundingClientRect();
        count(backgrounds, cs.backgroundColor, Math.round(r.width * r.height / 1000));
      }
    }
    const fontFaces = [];
    for (const sheet of [...document.styleSheets]) {
      let rules;
      try { rules = sheet.cssRules; } catch { continue; }
      for (const rule of [...(rules || [])]) {
        if (rule.type === CSSRule.FONT_FACE_RULE && fontFaces.length < 40) {
          const s = rule.style;
          const urls = [...(s.getPropertyValue("src").matchAll(/url\(["']?([^"')]+)["']?\)/g))]
            .map((m) => abs(m[1])).filter((u) => !u.startsWith("data:"));
          fontFaces.push({
            family: s.getPropertyValue("font-family").replace(/["']/g, "").trim(),
            weight: s.getPropertyValue("font-weight") || "400",
            style: s.getPropertyValue("font-style") || "normal", sources: urls,
          });
        }
      }
    }
    const fontLinks = [...document.querySelectorAll("link[href*='fonts.googleapis'], link[href*='use.typekit'], link[href*='fonts.bunny']")]
      .map((l) => l.href);

    // CSS değişkenleri (tasarım belirteçleri).
    const cssVars = {};
    const rootStyle = getComputedStyle(document.documentElement);
    for (const name of [...rootStyle].filter((p) => p.startsWith("--")).slice(0, 120)) {
      cssVars[name] = rootStyle.getPropertyValue(name).trim();
    }

    // Tipografi ölçeği.
    const scale = {};
    for (const tag of ["h1", "h2", "h3", "h4", "p", "a", "button", "small", "li", "input"]) {
      const el = [...document.querySelectorAll(tag)].find(shown);
      if (el) scale[tag] = typo(el);
    }
    scale.body = typo(document.body);

    // Düzen: içerik genişliği ve üst bilgi.
    const header = document.querySelector("header, [role='banner']") ||
      [...document.querySelectorAll("body > *")].find((el) => shown(el) && el.getBoundingClientRect().top < 5);
    const containerWidths = new Map();
    for (const el of all.slice(0, 1500)) {
      const cs = getComputedStyle(el);
      if (cs.maxWidth && cs.maxWidth !== "none" && cs.marginLeft === cs.marginRight && cs.marginLeft !== "0px") {
        count(containerWidths, cs.maxWidth);
      } else {
        const r = el.getBoundingClientRect();
        const centered = Math.abs(r.left - (innerWidth - r.right)) < 2 && r.left > 8;
        if (centered && r.width > innerWidth * 0.5) count(containerWidths, `${Math.round(r.width)}px`);
      }
    }
    const layout = {
      viewport: innerWidth, container: top(containerWidths, 3),
      header: header ? { ...box(header), sticky: ["sticky", "fixed"].includes(getComputedStyle(header).position) } : null,
    };

    // Gezinme: menü ve alt bilgi bağlantıları.
    const linksOf = (root) => root ? [...root.querySelectorAll("a[href]")].filter(shown)
      .map((a) => ({
        text: (textOf(a) || a.getAttribute("aria-label") || a.getAttribute("title") || "").slice(0, 60),
        href: abs(a.getAttribute("href")),
      }))
      .filter((l) => l.text).slice(0, 40) : [];
    const nav = document.querySelector("nav, [role='navigation']");
    const footer = document.querySelector("footer, [role='contentinfo']");
    // Menü dizilişi: öğeler aynı satırdaysa yatay. Madde imi görünüyorsa liste sıfırlanmamış.
    const navItems = nav ? [...nav.querySelectorAll("a[href]")].filter(shown).slice(0, 8) : [];
    const navRows = new Set(navItems.map((a) => Math.round(a.getBoundingClientRect().top / 8)));
    const navigation = {
      menu: linksOf(nav || header), header: linksOf(header), footer: linksOf(footer),
      layout: navItems.length < 2 ? "" : (navRows.size === 1 ? "yatay" : "dikey"),
      bullets: !!nav && [...nav.querySelectorAll("li")]
        .some((li) => shown(li) && getComputedStyle(li).listStyleType !== "none"),
    };

    // Bileşenler: aynı imzalı ≥3 kardeş (kart, ürün, kategori…), butonlar, fiyatlar.
    const groups = new Map();
    for (const el of all) {
      const parent = el.parentElement;
      if (!parent || !el.querySelector("img, picture, [style*='background']") || !textOf(el)) continue;
      const key = `${signature(parent)} > ${signature(el)}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(el);
    }
    // İç içe katmanlar aynı kartı birkaç kez sayar (ölçüldü: bir ürün kartı 5 katmanda).
    // Örnek öğesi seçilmiş bir grubun örneğini içeren ya da onun içinde kalan grup atlanır.
    const chosen = [];
    for (const [key, items] of [...groups.entries()].filter(([, list]) => list.length >= 3)
      .sort((a, b) => b[1].length - a[1].length)) {
      const sample = items[0];
      if (chosen.some(([, other]) => other[0].contains(sample) || sample.contains(other[0]))) continue;
      chosen.push([key, items]);
      if (chosen.length >= MAX_COMPONENTS) break;
    }
    const components = chosen
      .map(([key, items]) => {
        const sample = items[0];
        const link = sample.querySelector("a[href]") || sample.closest("a[href]");
        return {
          selector: key, count: items.length, style: box(sample),
          image: box(sample.querySelector("img, picture") || sample),
          title: typo(sample.querySelector("h1, h2, h3, h4, h5, [class*='title'], [class*='name']") || sample),
          samples: items.slice(0, 4).map((item) => textOf(item).slice(0, 140)),
          link: link ? abs(link.getAttribute("href")) : "", html: trimHtml(sample, 1500),
        };
      });
    const buttonStyles = new Map();
    for (const el of all) {
      if (!el.matches("button, a[class*='btn'], a[class*='button'], [role='button'], input[type='submit']")) continue;
      if (!textOf(el) && !el.value) continue; // simge düğmeleri bileşen stili değildir
      const b = box(el);
      const key = `${b.background}|${b.color}|${b.radius}|${b.font && b.font.size}`;
      if (!buttonStyles.has(key)) buttonStyles.set(key, { ...b, text: textOf(el).slice(0, 40), uses: 0 });
      buttonStyles.get(key).uses += 1;
    }
    const priceLeaf = (root) => [...root.querySelectorAll("*")]
      .find((el) => el.children.length === 0 && PRICE.test(textOf(el)));
    const prices = all.filter((el) => el.children.length === 0 && PRICE.test(textOf(el)))
      .slice(0, 8).map((el) => ({ text: textOf(el).slice(0, 40), style: typo(el) }));

    // Ürünler: fiyat taşıyan kart gruplarından ad, fiyat, görsel ve bağlantı.
    const products = [];
    const seenProducts = new Set();
    for (const [, items] of chosen) {
      if (!PRICE.test(textOf(items[0]))) continue;
      for (const item of items) {
        if (products.length >= MAX_PRODUCTS) break;
        const anchor = item.querySelector("a[href]") || item.closest("a[href]");
        const img = item.querySelector("img");
        const link = anchor ? abs(anchor.getAttribute("href")) : "";
        const src = img ? abs(img.currentSrc || img.src) : "";
        if (!link || !src || src.startsWith("data:") || seenProducts.has(link)) continue;
        seenProducts.add(link);
        const nameEl = item.querySelector("h1, h2, h3, h4, h5, [class*='title'], [class*='name']");
        const leaf = priceLeaf(item);
        products.push({
          name: (img.alt || (nameEl && textOf(nameEl)) || "").slice(0, 120),
          price: leaf ? textOf(leaf).slice(0, 40) : "", image: src, link,
          text: textOf(item).slice(0, 160), _w: Math.round(item.getBoundingClientRect().width),
          _x: Math.round(item.getBoundingClientRect().left),
        });
      }
    }

    // Metin blokları ve görseller.
    const texts = [...document.querySelectorAll("h1, h2, h3, h4, p, li > a, button")].filter(shown)
      .map((el) => ({ tag: el.tagName.toLowerCase(), text: textOf(el).slice(0, 200) }))
      .filter((t) => t.text).slice(0, MAX_TEXT_BLOCKS);
    const images = [...document.images].filter((img) => (img.currentSrc || img.src) && !(img.currentSrc || img.src).startsWith("data:"))
      .map((img) => {
        const r = img.getBoundingClientRect();
        return { src: abs(img.currentSrc || img.src), alt: (img.alt || "").slice(0, 160), natural: [img.naturalWidth, img.naturalHeight], shown: [Math.round(r.width), Math.round(r.height)] };
      })
      .filter((img) => img.natural[0] >= 32 && img.natural[1] >= 32).slice(0, MAX_IMAGES);
    const meta = (name) => document.querySelector(`meta[property='${name}'], meta[name='${name}']`)?.content || "";

    // Görünmeyen yazı: rengi zeminle (neredeyse) aynı olan başlık/bağlantı/düğme. Arkasında
    // görsel ya da video olan yazı ölçülmez (zemin rengi anlam taşımaz).
    const rgb = (value) => {
      const match = /rgba?\(([^)]+)\)/.exec(value || "");
      if (!match) return null;
      const parts = match[1].split(",").map(Number);
      return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
    };
    const luminance = (color) => {
      const channel = (v) => { const x = v / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
    };
    const backdrop = (el) => {
      for (let node = el; node; node = node.parentElement) {
        const cs = getComputedStyle(node);
        if (cs.backgroundImage && cs.backgroundImage !== "none") return null;
        if (node !== el && node.getBoundingClientRect().height < innerHeight * 1.5
          && (node.querySelector("video, canvas")
            || [...node.querySelectorAll("img")].some((img) => img.naturalWidth > 0))) return null;
        const color = rgb(cs.backgroundColor);
        if (color && color.a > 0.5) return color;
      }
      return { r: 255, g: 255, b: 255, a: 1 };
    };
    const invisible = [];
    for (const el of [...document.querySelectorAll("h1, h2, h3, p, a, button")].filter(shown).slice(0, 400)) {
      if (invisible.length >= 6) break;
      const text = textOf(el);
      if (!text || [...el.children].some((child) => textOf(child) === text)) continue;
      const foreground = rgb(getComputedStyle(el).color);
      const background = backdrop(el);
      if (!foreground || !background) continue;
      const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
      if ((light + 0.05) / (dark + 0.05) < 1.25) {
        invisible.push({ text: text.slice(0, 60), color: getComputedStyle(el).color });
      }
    }

    // Ürün ayrıntı sayfası: başlık + TEK "sepete ekle" düğmesi varsa galeri ve seçenekler.
    // Liste sayfasında her kartın kendi düğmesi olur; üç ve üstü düğme ayrıntı sayfası değildir.
    const buyButtons = [...document.querySelectorAll("button, [role='button'], input[type='submit'], a")]
      .filter(shown)
      .filter((el) => /sepete ekle|add to (cart|bag|basket)|satın al|buy now/i.test(textOf(el) || el.value || ""));
    const buyButton = buyButtons.length > 0 && buyButtons.length < 3 ? buyButtons[0] : null;
    const h1 = [...document.querySelectorAll("h1")].find(shown);
    const product = buyButton && h1 ? {
      name: textOf(h1).slice(0, 160), price: prices[0] ? prices[0].text : "",
      images: images.filter((img) => img.shown[0] >= 300).slice(0, 6).map((img) => img.src),
      options: [...document.querySelectorAll("button, label")].filter(shown).map(textOf)
        .filter((text) => /^(X{0,3}[SML]|\d{2}([.,]5)?|\d{2}-\d{2})$/i.test(text)).slice(0, 14),
      buyButton: { ...box(buyButton), text: textOf(buyButton).slice(0, 40) },
      description: meta("description").slice(0, 400),
    } : null;

    // Sayfa bölümleri: yukarıdan aşağı, tam genişliğe yakın bloklar (üst bilgi, kahraman,
    // ürün şeridi, görsel ızgara, alt bilgi). Model sayfayı BU SIRAYLA kurar.
    const wide = (el) => {
      if (!shown(el)) return false;
      const r = el.getBoundingClientRect();
      return r.width >= innerWidth * 0.6 && r.height >= 40;
    };
    const splitBlocks = (root, depth) => {
      const kids = [...root.children].filter(wide);
      if (!kids.length) return [root];
      if (kids.length === 1) return depth < 8 ? splitBlocks(kids[0], depth + 1) : kids;
      return kids.flatMap((kid) => (kid.getBoundingClientRect().height > innerHeight * 1.5 && depth < 8
        ? splitBlocks(kid, depth + 1) : [kid]));
    };
    const backgroundImage = (el) => {
      const match = /url\(["']?([^"')]+)["']?\)/.exec(getComputedStyle(el).backgroundImage || "");
      return match ? abs(match[1]) : "";
    };
    const describeSection = (el) => {
      const r = el.getBoundingClientRect();
      const pageTop = Math.round(r.top + scrollY);
      const pictures = [...el.querySelectorAll("img")].filter((img) => shown(img) && img.naturalWidth > 0)
        .map((img) => {
          const ir = img.getBoundingClientRect();
          return { src: abs(img.currentSrc || img.src), area: ir.width * ir.height };
        })
        .filter((img) => img.src && !img.src.startsWith("data:")).sort((a, b) => b.area - a.area);
      const video = el.querySelector("video");
      const priced = [...el.querySelectorAll("*")]
        .filter((node) => node.children.length === 0 && PRICE.test(textOf(node))).length;
      const hasMedia = !!video || pictures.length > 0 || !!backgroundImage(el);
      let kind = "metin";
      if (header && (el === header || el.contains(header)) && r.height < 220) kind = "ust-bilgi";
      else if (footer && (el === footer || footer.contains(el) || el.contains(footer))) kind = "alt-bilgi";
      else if (priced >= 3) kind = "urun-listesi";
      else if (hasMedia && r.height >= 300 && pageTop < innerHeight * 0.5) kind = "kahraman";
      else if (pictures.length >= 2) kind = "gorsel-izgara";
      else if (hasMedia) kind = "afis";
      const source = video ? (video.currentSrc || video.src || (video.querySelector("source") || {}).src || "") : "";
      return {
        kind, top: pageTop, height: Math.round(r.height),
        background: getComputedStyle(el).backgroundColor, backgroundImage: backgroundImage(el),
        headings: [...el.querySelectorAll("h1, h2, h3, h4")].filter(shown).slice(0, 3)
          .map((heading) => ({ text: textOf(heading).slice(0, 80), font: typo(heading) })),
        text: textOf(el).slice(0, 160), images: pictures.slice(0, 4).map((img) => img.src),
        imageCount: pictures.length,
        video: video ? { src: source ? abs(source) : "", poster: video.poster ? abs(video.poster) : "" } : null,
        buttons: [...el.querySelectorAll("button, a[class*='btn'], a[class*='button'], [role='button']")]
          .filter(shown).map(textOf).filter(Boolean).slice(0, 4),
        items: priced,
      };
    };
    const sections = splitBlocks(document.body, 0)
      .filter((el) => getComputedStyle(el).position !== "fixed" || el === header)
      .map(describeSection).filter((section) => section.height >= 40)
      .sort((a, b) => a.top - b.top).slice(0, MAX_SECTIONS);

    // Yerleşim sağlığı (kaynak gerekmez). Ölçüldü (3 Ekim 2026, 16. kabul koşusu): model
    // WooCommerce'in stillerini kapatıp mağaza/sepet/ödeme için stil yazmadı; mağaza tek
    // sütun 1368 px görsel, formlar tarayıcı varsayılanı oldu — hiçbir ölçüm bunu söylemedi.
    const cardWidths = products.slice(0, 8).map((item) => item._w || 0).filter(Boolean);
    const widestCard = cardWidths.length ? Math.max(...cardWidths) : 0;
    // Tek sütun = kartlar alt alta (aynı sol kenar). Ölçüldü (17. kabul koşusu): 216px dar
    // kartlar alt alta dizildi; yalnız genişliğe bakan ölçü bunu kaçırdı.
    const columns = new Set(products.slice(0, 8).map((item) => item._x)).size;
    const controls = [...document.querySelectorAll("input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea, button")]
      .filter(shown);
    const unstyled = controls.filter((el) => {
      const cs = getComputedStyle(el);
      const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
      // Tarayıcı varsayılanı: yatay iç boşluk toplamı ≤12px (düğme 6+6, alan 2+2), köşe yok.
      return pad <= 12 && parseFloat(cs.borderRadius) === 0;
    });
    const health = {
      viewport: innerWidth,
      products: products.length,
      widestCard,
      columns,
      singleColumn: products.length >= 3 && (columns === 1 || widestCard >= innerWidth * 0.8),
      controls: controls.length,
      unstyledControls: unstyled.length,
      overflowX: document.documentElement.scrollWidth > innerWidth + 2,
      bodyWords: textOf(document.body).split(" ").length,
    };

    return {
      url: location.href, title: document.title, description: meta("description"), health,
      logo: (() => {
        const img = header && header.querySelector("img, svg");
        return img ? (img.tagName === "IMG" ? abs(img.currentSrc || img.src) : trimHtml(img, 3000)) : "";
      })(),
      fonts: { used: top(families, 6), faces: fontFaces, links: fontLinks },
      colors: { text: top(colors, 8), background: top(backgrounds, 8) },
      cssVars, scale, layout, navigation, components,
      buttons: [...buttonStyles.values()].sort((a, b) => b.uses - a.uses).slice(0, 6),
      prices, texts, images, sections, products, product, invisible,
    };
  };
  // </fusion-design>
  if (operation === "design") return designProbe(args || {});
  if (operation === "text") {
    return { found: (document.body?.innerText || "").includes(String(args.text || "")), url: location.href };
  }
  throw new Error("Desteklenmeyen sayfa eylemi.");
  };
  // Arka plan `__hataDondur` ile çağırır: `executeScript` sayfadaki hatayı iletmez,
  // sonucu boş döndürür. Hata burada yakalanıp veri olarak geri verilir.
  if (!args || !args.__hataDondur) return calistir();
  try {
    return calistir();
  } catch (error) {
    return { __hata: String((error && error.message) || error) };
  }
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

/** Panelin "Bu siteye izin ver" kartını açan kayıt (panel `PERMISSION_KEY`i dinler). */
export const PERMISSION_KEY = "fusionPermission";

/** Kullanıcının izin kartına basması için komutun bekleyeceği süre (köprü zaman aşımı 30 sn). */
let permissionWaitMs = 25000;
/** Testler bekleme süresini kısaltır. */
export function setPermissionWait(ms) { permissionWaitMs = ms; }

/**
 * İzni olmayan siteye girişte: paneldeki izin kartını aç ve kullanıcının tıklamasını BEKLE;
 * izin gelince komut kaldığı yerden sürer (ajanın yeniden denemesine gerek kalmaz).
 * İzin yalnız kullanıcı tıklamasıyla verilebilir (Chrome kuralı). Süre dolarsa ya da
 * kullanıcı reddederse modele ne yapacağı söylenir.
 */
async function ensurePermission(origin, reason) {
  if (await permitted(origin)) return;
  try { await chrome.storage.session.set({ [PERMISSION_KEY]: { origin, at: Date.now() } }); } catch { /* kart açılamazsa mesaj yeter */ }
  const until = Date.now() + permissionWaitMs;
  while (Date.now() < until) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    if (await permitted(origin)) return;
    const pending = (await chrome.storage.session.get(PERMISSION_KEY).catch(() => ({})))[PERMISSION_KEY];
    if (!pending) break; // kullanıcı "Şimdi değil" dedi
  }
  if (await permitted(origin)) return;
  throw new Error(
    `${reason} ${origin} için kullanıcı izin vermedi (panelde izin kartı açıldı). ` +
    "Kullanıcıya kısaca söyle; izin gelirse aynı komutu yeniden dene, vermezse o siteye girme.");
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
      await ensurePermission(origin, "Sekme izin verilmeyen bir siteye geçti.");
    }
    await setSelected(tab);
  }
  return tab;
}

/** Sayfada çalışan işlemin sonucunu yorumla: hata yutulmaz.
 *
 * Ölçüldü (4 Ekim kabul koşusu): sayfadaki işlem hata fırlatınca `executeScript`
 * reddetmiyor, sonucu boş dönüyor; araç bunu "başarılı: null" diye iletiyordu.
 * Model seçim kutusuna yazmayı başarılı sandı, form hiç gönderilmediği hâlde
 * "gönderildi" dedi. İşlem hatayı artık `__hata` alanıyla veri olarak döndürür.
 * Boş sonuç yalnız bağlam kapandığında (tıklama sayfayı değiştirdi) görülür. */
export function injectionOutcome(injection, urlAfter) {
  const error = injection?.error;
  if (error) throw new Error(typeof error === "string" ? error : error.message || "Sayfa işlemi hata verdi.");
  const result = injection?.result;
  if (result && typeof result === "object" && typeof result.__hata === "string") throw new Error(result.__hata);
  if (result !== undefined && result !== null) return result;
  return { navigated: true, url: urlAfter ?? null };
}

async function runInTab(tab, operation, args) {
  let injection;
  try {
    [injection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: pageAction, args: [operation, { ...args, __hataDondur: true }],
    });
  } catch (error) {
    // Çerçeve işlem sırasında kapandıysa (gönderim sonrası yönlendirme) adres değişmiştir.
    const current = await chrome.tabs.get(tab.id).catch(() => null);
    if (current && current.url !== tab.url) return { navigated: true, url: current.url };
    throw error;
  }
  const current = await chrome.tabs.get(tab.id).catch(() => null);
  return injectionOutcome(injection, current?.url);
}

export async function execute(command) {
  const veri = command.veri || {};
  if (command.islem === "tabs") {
    const tabs = await chrome.tabs.query({});
    const selected = await getSelected();
    return {
      tabs: tabs.filter((t) => /^https?:/.test(t.url || "")).slice(0, 60).map((t) => ({
        id: t.id, title: (t.title || "").slice(0, 100), url: t.url, active: t.active,
        bound: t.id === selected?.id, windowId: t.windowId, icon: (t.favIconUrl || "").startsWith("data:image/") ? t.favIconUrl : "",
      })),
    };
  }
  if (command.islem === "tab_open") {
    const destination = new URL(veri.url);
    if (!await permitted(destination.origin)) {
      await ensurePermission(destination.origin, "Bu siteyi açmak için izin yok.");
    }
    const tab = await chrome.tabs.create({ url: destination.href, active: true });
    await waitForLoad(tab.id);
    const bound = await setSelected(await chrome.tabs.get(tab.id));
    return { opened: bound.id, url: destination.href };
  }
  if (command.islem === "tab_focus") {
    if (!Number.isSafeInteger(veri.id) || veri.id <= 0) throw new Error("Sekme kimliği geçersiz.");
    const tab = await chrome.tabs.get(veri.id);
    await chrome.tabs.update(tab.id, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
    return { focused: tab.id, windowId: tab.windowId };
  }
  if (command.islem === "tab_select") {
    const tab = await chrome.tabs.get(Number(veri.id));
    const origin = new URL(tab.url).origin;
    await ensurePermission(origin, "Bu sekmenin sitesi için izin yok.");
    await setSelected(tab);
    return { selected: tab.id, url: tab.url };
  }
  if (command.islem === "tab_close") {
    const closing = await chrome.tabs.get(Number(veri.id));
    await chrome.tabs.remove(closing.id);
    if ((await getSelected())?.id === closing.id) await clearSelected();
    return { closed: closing.id };
  }
  let tab;
  try {
    tab = await checkedTab();
  } catch (error) {
    // Adres açmak için bağlı sekme şart değildir: yeni sekmede açılır. Ölçüldü (4 Ekim
    // 2026): her kabul koşusunun ilk chrome_navigate çağrısı "Bağlı sekme yok" ile düştü.
    if (command.islem !== "navigate" || !veri.url) throw error;
    return execute({ ...command, islem: "tab_open" });
  }
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
      await ensurePermission(destination.origin, "Bu siteye gitmek için izin yok.");
    }
    await chrome.tabs.update(tab.id, { url: destination.href });
    await waitForLoad(tab.id);
    await setSelected(await chrome.tabs.get(tab.id));
    return { url: destination.href };
  }
  if (command.islem === "resize") {
    const width = Math.round(Number(veri.width));
    const height = Math.round(Number(veri.height));
    if (!(width >= 320 && width <= 3840 && height >= 240 && height <= 2400)) throw new Error("Boyut 320x240 ile 3840x2400 arasında olmalı.");
    await chrome.windows.update(tab.windowId, { width, height, state: "normal" });
    return { width, height };
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
  const acts = ["click", "click_at", "key", "drag"].includes(command.islem);
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
