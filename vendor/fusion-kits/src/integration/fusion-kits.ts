/** Fusion'ın ana menüsü host'a aittir; Kits kendi uzman/belge menüsünü yönetir. */
export const fusionNavigation = [
  { id: 'home', label: 'Home', icon: 'house' },
  { id: 'scheduled', label: 'Zamanlananlar', icon: 'clock' },
  { id: 'library', label: 'Kitaplık', icon: 'library' },
  { id: 'media', label: 'Görsel ve video üretimi', icon: 'images' },
  { id: 'kits', label: 'Kits', icon: 'sparkles' },
] as const;

export function kitsModuleUrl(serviceUrl: string) {
  const url = new URL(serviceUrl);
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password
  )
    throw new Error(
      'Kits adresi kimlik bilgisi içermeyen HTTP(S) adresi olmalı.',
    );
  if (url.search || url.hash)
    throw new Error(
      'Kits servis adresinde sorgu, token veya fragment olmamalı.',
    );
  url.searchParams.set('surface', 'kits');
  return url.toString();
}

/** Yalnız Kits seçilince mount edin; host Home ekranı ve ana menüsü değişmez. */
export function mountFusionKits(container: HTMLElement, serviceUrl: string) {
  const iframe = container.ownerDocument.createElement('iframe');
  iframe.title = 'Fusion Kits';
  iframe.src = kitsModuleUrl(serviceUrl);
  iframe.allow = 'microphone; autoplay; fullscreen';
  iframe.referrerPolicy = 'no-referrer';
  iframe.style.cssText = 'width:100%;height:100%;border:0;display:block;';
  container.append(iframe);
  return {
    element: iframe,
    // Menü geçişinde node'u saklayarak sohbeti koruyabilirsiniz; dispose gerçek kapanıştır.
    dispose() {
      iframe.remove();
    },
  };
}
