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
