() => {
  // Sayfanın render edilmiş halini yakala: CSSOM (çalışma anında eklenen kurallar dahil),
  // betiksiz DOM ve başlık/gövde/altlık bölmesi. Python tarafı varlıkları indirir.
  const css = [];
  const blocked = [];
  for (const sheet of document.styleSheets) {
    try {
      for (const rule of sheet.cssRules) css.push(rule.cssText);
    } catch (error) {
      if (sheet.href) blocked.push(sheet.href);
    }
  }
  const abs = (value) => {
    try { return new URL(value, location.href).href; } catch (error) { return value; }
  };
  // Çerez/izin bantları kopyada çalışmaz (düğmeleri betik ister): sabit konumlu ve
  // çerez/cookie metni taşıyan öğeler işaretlenip kopyadan çıkarılır.
  for (const node of document.body.querySelectorAll('*')) {
    const style = getComputedStyle(node);
    if ((style.position === 'fixed' || style.position === 'sticky')
        && /çerez|cerez|cookie|kvkk|consent/i.test(node.textContent || '')
        && !node.querySelector('header, nav')) {
      node.setAttribute('data-kopya-izin-bandi', '1');
    }
  }
  // Kaydırıcılar (swiper, slick…) slayt genişliğini BETİKLE verir; kopyada betik yok.
  // Ölçüldü (4 Ekim, mağaza ana sayfası): slayt 250 px'te kaldı ama içindeki kart
  // yüzde kuralıyla 62 px'e düştü, şerit de sayfayı yatayda taşırdı. Slayt, görsele
  // inen zincir ve şeridin kırpan kabı kaynakta ölçülen değerle dondurulur.
  const SLIDES = '.swiper-slide, .slick-slide, .splide__slide, .embla__slide, '
    + '.glide__slide, .keen-slider__slide, .carousel-item';
  const px = (node) => Math.round(node.getBoundingClientRect().width);
  for (const slide of document.querySelectorAll(SLIDES)) {
    const width = px(slide);
    if (width < 1) continue;
    slide.style.width = `${width}px`;
    slide.style.maxWidth = 'none';
    slide.style.flex = `0 0 ${width}px`;
    for (const media of slide.querySelectorAll('img, video, picture')) {
      for (let node = media; node && node !== slide; node = node.parentElement) {
        const inner = px(node);
        if (inner < 1) continue;
        node.style.width = `${inner}px`;
        node.style.maxWidth = 'none';
        node.style.flexBasis = 'auto';
      }
    }
    for (let box = slide.parentElement, depth = 0; box && depth < 3; box = box.parentElement, depth++) {
      const overflow = getComputedStyle(box).overflowX;
      if (overflow === 'hidden' || overflow === 'clip') {
        box.style.overflow = 'hidden';
        break;
      }
    }
  }
  const clone = document.documentElement.cloneNode(true);
  clone.querySelectorAll('[data-kopya-izin-bandi]').forEach((node) => node.remove());
  clone.querySelectorAll(
    'script, noscript, iframe, link[rel=stylesheet], link[rel=preload], link[rel=modulepreload], style'
  ).forEach((node) => node.remove());
  for (const attr of ['src', 'poster', 'href']) {
    clone.querySelectorAll(`[${attr}]`).forEach((node) => node.setAttribute(attr, abs(node.getAttribute(attr))));
  }
  clone.querySelectorAll('[srcset]').forEach((node) => {
    const parts = node.getAttribute('srcset').split(',').map((part) => {
      const [url, ...rest] = part.trim().split(/\s+/);
      return [abs(url), ...rest].join(' ');
    });
    node.setAttribute('srcset', parts.join(', '));
  });
  // Tembel yükleyiciler gerçek adresi data-* özniteliğinde tutar; JS kapalı kopyada görünmez.
  clone.querySelectorAll('img[data-src]').forEach((node) => node.setAttribute('src', abs(node.getAttribute('data-src'))));
  // Sabit/mutlak konumlu başlık içeriğin üstüne biner; tema iç sayfalarda bu kadar
  // üst boşluk bırakır (ölçüldü: mağaza başlığı menünün altında kalıyordu).
  let headerOffset = 0;
  const liveHeader = document.querySelector('header, [role=banner]');
  for (let node = liveHeader; node && node !== document.body; node = node.parentElement) {
    const position = getComputedStyle(node).position;
    if (position === 'fixed' || position === 'absolute') {
      headerOffset = Math.round(liveHeader.getBoundingClientRect().bottom);
      break;
    }
  }
  const body = clone.querySelector('body');
  const header = body.querySelector('header, [role=banner]');
  const footers = body.querySelectorAll('footer, [role=contentinfo]');
  const footer = footers.length ? footers[footers.length - 1] : null;
  const headerHtml = header ? header.outerHTML : '';
  const footerHtml = footer ? footer.outerHTML : '';
  if (header) header.remove();
  if (footer) footer.remove();
  return {
    css: css.join('\n'),
    blocked,
    title: document.title,
    lang: document.documentElement.lang || '',
    bodyClass: document.body.className || '',
    header: headerHtml,
    main: body.innerHTML,
    footer: footerHtml,
    headerOffset,
  };
}
