([mode, group, tab]) => {
  // Tıklamayla içerik değiştiren sekme grupları (ör. "Kadın / Erkek / Çocuk" ürün şeridi).
  // 'groups': kısa yazılı, tıklanabilir kardeşlerden oluşan grupları işaretle;
  // 'snapshot': görsel/metin imzalarını sakla;
  // 'diff': tıklamadan sonra değişen öğelerin ortak atasını (bölüm kökü) bul ve işaretle;
  // 'freeze': bölümün o anki halini gizli, yerleşimi korunmuş bir kopya olarak ekle
  //   (kopyalama betiği slayt genişliklerini kopyada da dondurabilsin);
  // 'finish': kopyaları ekran dışında tut, asıl bölümü açık işaretle.
  const visible = (node) => {
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(node).visibility !== 'hidden';
  };
  const excluded = (node) => {
    if (node.closest('header, nav, footer, [role=banner], [data-kopya-izin-bandi], '
      + '[data-kopya-durum]:not([data-kopya-acik])')) return true;
    for (let current = node, depth = 0; current && depth < 8; current = current.parentElement, depth += 1) {
      if (getComputedStyle(current).position === 'fixed') return true;
    }
    return false;
  };
  const navigates = (node) => {
    const link = node.closest('a[href]');
    return link !== null && !/^(#|javascript:)/.test(link.getAttribute('href') || '');
  };
  if (mode === 'groups') {
    const out = [];
    for (const parent of document.body.querySelectorAll('*')) {
      const kids = Array.from(parent.children);
      if (kids.length < 2 || kids.length > 6 || parent.hasAttribute('data-kopya-sekme-grup')) continue;
      const tabLike = kids.every((kid) => {
        const text = (kid.innerText || '').trim();
        const rect = kid.getBoundingClientRect();
        return text && text.length <= 20 && !/\d/.test(text) && visible(kid) && rect.height < 80
          && getComputedStyle(kid).cursor === 'pointer' && !navigates(kid);
      });
      if (!tabLike || excluded(parent)) continue;
      const id = String(out.length);
      parent.setAttribute('data-kopya-sekme-grup', id);
      kids.forEach((kid, index) => kid.setAttribute('data-kopya-sekme', `${id}-${index}`));
      out.push({ id, labels: kids.map((kid) => kid.innerText.trim()) });
      if (out.length >= 6) break;
    }
    return out;
  }
  const signature = (node) => (node.tagName === 'IMG'
    ? node.currentSrc || node.getAttribute('src') || ''
    : Array.from(node.childNodes).filter((child) => child.nodeType === 3)
      .map((child) => child.textContent.trim()).join(' '));
  if (mode === 'snapshot') {
    // Gizli hazır paneller (sekme yalnız görünürlüğü değiştirir) için görünürlük de saklanır.
    window.__kopyaImza = new Map(Array.from(document.body.querySelectorAll('*'))
      .filter((node) => !excluded(node))
      .map((node) => [node, `${visible(node) ? 1 : 0}|${signature(node)}`]));
    return 0;
  }
  const tabsOf = (id) => document.querySelector(`[data-kopya-sekme-grup="${id}"]`);
  const ancestors = (node) => {
    const list = [];
    for (let current = node; current; current = current.parentElement) list.push(current);
    return list;
  };
  const common = (nodes) => nodes.reduce((acc, node) => {
    const chain = new Set(ancestors(node));
    return ancestors(acc).find((candidate) => chain.has(candidate)) || document.body;
  });
  if (mode === 'diff') {
    const before = window.__kopyaImza || new Map();
    const changed = Array.from(document.body.querySelectorAll('*')).filter((node) => {
      if (excluded(node) || !visible(node)) return false;
      if (node.closest(`[data-kopya-sekme-grup="${group}"]`)) return false;
      const own = node.tagName === 'IMG' || signature(node) !== '';
      return !before.has(node) ? own
        : own && before.get(node) !== `1|${signature(node)}`;
    });
    if (!changed.length) return null;
    const tabs = tabsOf(group);
    const previous = document.querySelector(`[data-kopya-durum-kok="${group}"]`);
    const root = common([tabs, ...changed, ...(previous ? [previous] : [])]);
    if (root === document.body || root === document.documentElement) return null;
    if (previous) previous.removeAttribute('data-kopya-durum-kok');
    root.setAttribute('data-kopya-durum-kok', group);
    return changed.length;
  }
  const root = document.querySelector(`[data-kopya-durum-kok="${group}"]`);
  if (!root) return null;
  if (mode === 'freeze') {
    const copy = root.cloneNode(true);
    copy.removeAttribute('data-kopya-durum-kok');
    copy.setAttribute('data-kopya-durum', `${group}-${tab}`);
    copy.setAttribute('data-kopya-stil', root.getAttribute('style') || '');
    const width = root.getBoundingClientRect().width;
    copy.setAttribute('style', `${root.getAttribute('style') || ''};position:absolute;`
      + `left:-30000px;top:0;width:${width}px;pointer-events:none`);
    root.parentElement.insertBefore(copy, root.nextSibling);
    return 1;
  }
  // finish: asıl bölüm ilk sekmenin hali (açık); kopyalar ekran dışında bekler.
  root.setAttribute('data-kopya-durum', `${group}-0`);
  root.setAttribute('data-kopya-acik', '');
  root.removeAttribute('data-kopya-durum-kok');
  return 1;
}
