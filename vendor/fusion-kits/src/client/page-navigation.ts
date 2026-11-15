export function openPageLink(href: string) {
  const hash = href.startsWith('/#') ? href.slice(1) : href;
  if (location.hash === hash)
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  else location.hash = hash;
}
