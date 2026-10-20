// Kopyanın yerel etkileşimleri (kaynak betik kopyada yok).
// 1) Sekmeler: yakalamada dondurulan halleri (`data-kopya-durum="grup-sıra"`) değiştir.
// 2) Kaydırıcı okları: aynı bölümdeki taşan şeridi görünür genişlik kadar kaydır.
(() => {
  const showState = (tab) => {
    const [group, index] = tab.getAttribute('data-kopya-sekme').split('-');
    const target = document.querySelector(`[data-kopya-durum="${group}-${index}"]`);
    if (!target) return false;
    document.querySelectorAll(`[data-kopya-durum^="${group}-"]`).forEach((state) => {
      state.removeAttribute('data-kopya-acik');
    });
    if (target.hasAttribute('data-kopya-stil')) {
      target.setAttribute('style', target.getAttribute('data-kopya-stil'));
    }
    target.setAttribute('data-kopya-acik', '');
    return true;
  };
  const ARROW = /sonraki|next|ileri|önceki|onceki|prev|geri|right|left|sag|sol/i;
  const isArrow = (button) => !(button.innerText || '').trim()
    && ARROW.test(`${button.getAttribute('aria-label') || ''} ${button.className || ''}`);
  const direction = (button) => (/önceki|onceki|prev|geri|left|sol/i
    .test(`${button.getAttribute('aria-label') || ''} ${button.className || ''}`) ? -1 : 1);
  const scroller = (scope) => Array.from(scope.querySelectorAll('*')).find((node) => {
    const style = getComputedStyle(node);
    return /auto|scroll/.test(style.overflowX) && node.scrollWidth > node.clientWidth + 4;
  });
  const track = (scope) => Array.from(scope.querySelectorAll('*')).find((node) => {
    const clip = node.parentElement;
    return node.children.length >= 3 && clip && clip !== scope.parentElement
      && /hidden|clip/.test(getComputedStyle(clip).overflowX)
      && node.scrollWidth > clip.clientWidth + 4;
  });
  // Yakalanan ilk halde "geri" oku pasifti (kaynakta sınıf + pointer-events:none);
  // kopyada konuma göre yeniden açılır/kapanır.
  const ARROWS = 'button, [role=button], [aria-label], [class*="next"], [class*="prev"], [class*="arrow"]';
  const updateArrows = (scope, offset, room) => {
    scope.querySelectorAll(ARROWS).forEach((arrow) => {
      if (!isArrow(arrow)) return;
      const open = direction(arrow) < 0 ? offset < 0 : offset > -room;
      Array.from(arrow.classList).filter((name) => /disabled/i.test(name))
        .forEach((name) => arrow.classList.remove(name));
      arrow.removeAttribute('disabled');
      arrow.setAttribute('aria-disabled', String(!open));
      arrow.style.pointerEvents = 'auto';
      arrow.style.opacity = open ? '' : '0.35';
    });
  };
  const slide = (button) => {
    const step = direction(button);
    for (let scope = button.parentElement, depth = 0; scope && depth < 6;
      scope = scope.parentElement, depth += 1) {
      const box = scroller(scope);
      if (box) {
        box.scrollBy({ left: step * box.clientWidth * 0.8, behavior: 'smooth' });
        return true;
      }
      const strip = track(scope);
      if (strip) {
        const view = strip.parentElement.clientWidth;
        const room = strip.scrollWidth - view;
        // Adım bütün kart kadardır: kart yarıdan kesilmesin (kart + aralık genişliği).
        const [first, second] = strip.children;
        const card = second ? second.offsetLeft - first.offsetLeft : view;
        const jump = card > 0 ? Math.max(card, Math.floor(view / card) * card) : view;
        const now = Number(strip.dataset.kopyaKayma || 0);
        const next = Math.max(-room, Math.min(0, now - step * jump));
        strip.dataset.kopyaKayma = String(next);
        strip.style.transition = 'transform 400ms ease';
        strip.style.transform = `translate3d(${next}px, 0, 0)`;
        updateArrows(scope, next, room);
        return true;
      }
    }
    return false;
  };
  document.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-kopya-sekme]');
    if (tab && showState(tab)) {
      event.preventDefault();
      return;
    }
    // Oklar her zaman <button> değildir (ör. `div.swiper-button-next`, aria-label "Next slide").
    const button = event.target.closest(ARROWS);
    if (button && isArrow(button) && slide(button)) event.preventDefault();
  });
})();
