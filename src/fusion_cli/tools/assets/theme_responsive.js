(() => {
  // Kaynak uygulamanın olayları çalıştırılmaz; yalnız doğrulanmış viewport seçilir.
  const templates = Array.from(document.querySelectorAll('template[data-fusion-part="header"]'));
  if (!templates.length) return;
  const regions = templates.map((template) => ({name: template.dataset.fusionVariant,
    predicates: JSON.parse(template.dataset.fusionConditions).map((item) => ({
      media: matchMedia(item.query), matches: item.matches}))}));
  const style = document.createElement('style');
  style.dataset.fusionActiveCss = '';
  document.head.append(style);
  let active = null;

  const remember = (region) => {
    const focused = document.activeElement;
    if (!region.contains(focused)) return null;
    return {id: focused.id, tag: focused.tagName, type: focused.type,
      value: focused.value, checked: focused.checked, start: focused.selectionStart,
      end: focused.selectionEnd};
  };
  const restore = (region, saved) => {
    if (!saved) return;
    const target = saved.id ? region.querySelector(`#${CSS.escape(saved.id)}`) : null;
    if (!target || target.tagName !== saved.tag || target.type !== saved.type) {
      document.documentElement.dataset.fusionFocusLost = 'true';
      console.warn('Viewport değişiminde odak karşılığı bulunamadı; kaynak etkileşimi ayrıca doğrulanmalı.');
      return;
    }
    if (saved.value !== undefined) target.value = saved.value;
    if (saved.checked !== undefined) target.checked = saved.checked;
    target.focus({preventScroll: true});
    if (saved.start !== null && saved.start !== undefined) {
      target.setSelectionRange(saved.start, saved.end);
    }
  };
  const update = () => {
    const matching = regions.filter((region) => region.predicates.every((item) => item.media.matches === item.matches));
    if (matching.length !== 1) {
      document.documentElement.dataset.fusionUnsupportedViewport = 'true';
      console.error('Viewport tek doğrulanmış kaynak bölgesiyle eşleşmedi; tema değişimi uygulanmadı.');
      return;
    }
    const next = matching[0].name;
    if (next === active) return;
    const css = document.querySelector(`template[data-fusion-css="${next}"]`);
    if (!css) {
      console.error('Viewport için yakalanmış tema stili bulunamadı.');
      return;
    }
    const scroll = {left: scrollX, top: scrollY};
    style.textContent = css.content.querySelector('style').textContent;
    const original = document.querySelector('#kopya-css');
    if (original) original.disabled = true;
    document.documentElement.style.setProperty('--fusion-header-offset', `${css.dataset.fusionOffset}px`);
    document.querySelectorAll('[data-fusion-region]').forEach((region) => {
      if (region.dataset.fusionActive === next) return;
      const template = document.querySelector(`template[data-fusion-part="${region.dataset.fusionRegion}"][data-fusion-variant="${next}"]`);
      if (!template) return;
      const saved = remember(region);
      region.replaceChildren(template.content.cloneNode(true));
      region.dataset.fusionActive = next;
      restore(region, saved);
    });
    active = next;
    scrollTo(scroll);
  };
  regions.forEach((region) => region.predicates.forEach((item) => item.media.addEventListener('change', update)));
  update();
})();
