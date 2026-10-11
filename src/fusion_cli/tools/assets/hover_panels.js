([mode, key, scope]) => {
  // Başlık menüsünde üzerine gelince açılan paneller (mega menü) ve iç alt paneller.
  // 'triggers': adayları `data-kopya-ac` ile işaretle, konumlarını ver (scope verilirse
  //   yalnız o panelin içinde, ok/aria-haspopup taşıyan öğeler);
  // 'snapshot': görünür kümeyi sakla;
  // 'diff': üzerine gelince görünür olanları `data-kopya-panel=key` ile işaretle;
  // 'restore': üzerine gelince YARATILIP ayrılınca silinen paneli DOM'a geri koy
  //   (kopyada CSS gizler/gösterir; betik yok).
  const shown = (node) => {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden'
      && style.display !== 'none' && Number(style.opacity) > 0;
  };
  if (mode === 'triggers') {
    const out = [];
    const root = scope ? document.querySelector(`[data-kopya-panel="${scope}"]`) : document;
    if (!root) return out;
    const selector = scope
      ? 'a, button, li, [role=menuitem]'
      : 'header a, header button, nav a, [role=banner] a';
    const seen = new Set();
    for (const node of root.querySelectorAll(selector)) {
      const rect = node.getBoundingClientRect();
      const text = (node.innerText || '').trim();
      if (!text || text.length > 30 || rect.width < 1 || !shown(node)) continue;
      if (!scope && rect.top > 200) continue;
      if (scope && !node.querySelector('svg') && !node.hasAttribute('aria-haspopup')) continue;
      if (node.closest('[data-kopya-ac]') || node.querySelector('[data-kopya-ac]')) continue;
      if (seen.has(text)) continue;
      seen.add(text);
      const id = scope ? `${scope}-${out.length}` : String(out.length);
      node.setAttribute('data-kopya-ac', id);
      out.push({ id, text, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 });
      if (out.length >= 12) break;
    }
    return out;
  }
  if (mode === 'snapshot') {
    window.__kopyaGorunur = new Map(Array.from(document.body.querySelectorAll('*'))
      .filter(shown).map((node) => [node, node.textContent]));
    return 0;
  }
  if (mode === 'restore') {
    let restored = 0;
    for (const item of window.__kopyaPaneller || []) {
      if (item.node.isConnected || !item.parent.isConnected) continue;
      item.parent.insertAdjacentHTML('beforeend', item.html);
      restored += 1;
    }
    return restored;
  }
  const before = window.__kopyaGorunur || new Map();
  const visible = Array.from(document.body.querySelectorAll('*')).filter(shown);
  const fresh = new Set(visible.filter((node) => !before.has(node)));
  // Açık kalan kutunun yalnız içeriği değişmiş olabilir (alt panel her satırda yeniden
  // dolar): içeriği değişen ve yeni çocuk taşıyan kutu da panel adayıdır.
  // Yeni çocuk kendisi bir kutuysa (panel) değişen o çocuktur, kapsayan üst değil.
  const boxy = (node) => node.querySelectorAll('*').length >= 3;
  const changed = visible.filter((node) => {
    if (!before.has(node) || before.get(node) === node.textContent) return false;
    const added = Array.from(node.children).filter((child) => fresh.has(child));
    return added.length > 0 && !added.some(boxy);
  });
  const freshSet = new Set([...fresh, ...changed]);
  // Kendiliğinden ilerleyen kaydırıcı slaytları panel sayılmasın: panel başlığın içinde
  // ya da sabit/mutlak konumlu olur ve en az birkaç öğe taşır.
  // Bütün ekranı kaplayan karartma katmanı panel değildir. Panel tetikleyicisinin
  // hizasında ya da hemen altında başlar; uzaktaki değişim (kendiliğinden dönen hero
  // slaytının yazısı) sayılmaz.
  const anchor = document.querySelector(`[data-kopya-ac="${key}"]`);
  const near = (rect) => {
    if (!anchor) return true;
    const own = anchor.getBoundingClientRect();
    return rect.top <= own.bottom + 40 && rect.bottom >= own.top;
  };
  const panelLike = (node) => boxy(node)
    && node.getBoundingClientRect().width < window.innerWidth * 0.9
    && near(node.getBoundingClientRect())
    && (node.closest('header, [role=banner], nav') !== null
      || ['absolute', 'fixed'].includes(getComputedStyle(node).position));
  const roots = [...freshSet].filter((node) => !freshSet.has(node.parentElement)
    && !node.closest('[data-kopya-ac]') && panelLike(node));
  return roots.map((node) => {
    const style = getComputedStyle(node);
    // Aynı kutu her öğede içeriği değiştirerek yeniden kullanılıyorsa (tek alt panel),
    // bu öğenin içeriği gizli bir kopya olarak dondurulur; kopyayı CSS gösterir.
    let target = node;
    if (node.hasAttribute('data-kopya-panel')) {
      target = node.cloneNode(true);
      target.style.visibility = 'hidden';
      target.style.pointerEvents = 'none';
      target.querySelectorAll('[data-kopya-ac], [data-kopya-panel]').forEach((inner) => {
        inner.removeAttribute('data-kopya-ac');
        inner.removeAttribute('data-kopya-panel');
      });
      node.parentElement.appendChild(target);
    }
    target.setAttribute('data-kopya-panel', key);
    if (scope) target.setAttribute('data-kopya-ust', scope);
    else target.removeAttribute('data-kopya-ust');
    window.__kopyaPaneller = window.__kopyaPaneller || [];
    window.__kopyaPaneller.push({ node: target, parent: node.parentElement, html: target.outerHTML });
    // Konumu betik veriyorsa (alt panel üst satırın yanına yerleşir) kopyada kaybolur;
    // konumlu kutunun ölçülen yeri görünür kurala yazılır.
    // Alt panel akıştaysa (flex öğesi) kopyada başka yere düşebilir: üst panele göre
    // ölçülen yeri mutlak konum olarak verilir.
    const placed = ['absolute', 'fixed'].includes(style.position);
    const pinned = !placed && Boolean(scope) && target.offsetParent !== null;
    return {
      position: pinned ? 'absolute' : '',
      left: placed ? style.left : (pinned ? `${node.offsetLeft}px` : ''),
      top: placed ? style.top : (pinned ? `${node.offsetTop}px` : ''),
      width: placed || pinned ? `${node.getBoundingClientRect().width}px` : '',
      display: style.display,
      opacity: style.opacity,
      transform: style.transform,
    };
  });
}
