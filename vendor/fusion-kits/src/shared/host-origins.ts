/** Gömme yalnız açıkça tanımlanan host origin'lerine açılır; API kuralları ayrı kalır. */
export function kitsHostOrigins(raw?: string): readonly string[] {
  if (!raw?.trim()) return Object.freeze([]);
  let values: unknown;
  try {
    values = JSON.parse(raw);
  } catch {
    throw new Error('KITS_HOST_ORIGINS JSON origin dizisi olmalı.');
  }
  if (!Array.isArray(values) || values.length === 0 || values.length > 8)
    throw new Error('KITS_HOST_ORIGINS 1–8 açık origin içermeli.');
  const origins = values.map((value) => {
    if (typeof value !== 'string') throw new Error('Host origin metin olmalı.');
    const url = new URL(value);
    if (
      !['https:', 'http:', 'tauri:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.pathname !== '/' && url.pathname !== '') ||
      !url.hostname ||
      /[\s;'*]/.test(value)
    )
      throw new Error(
        'Host origin tam ve sorgusuz HTTP(S)/Tauri origin olmalı.',
      );
    if (
      url.protocol === 'http:' &&
      !['localhost', '127.0.0.1', '[::1]', 'tauri.localhost'].includes(
        url.hostname,
      )
    )
      throw new Error('Uzak host HTTPS kullanmalı.');
    if (url.protocol === 'tauri:' && url.hostname !== 'localhost')
      throw new Error('Tauri host localhost olmalı.');
    return `${url.protocol}//${url.host}`;
  });
  return Object.freeze([...new Set(origins)]);
}

export function kitsFrameAncestors(raw?: string): string {
  return kitsHostOrigins(raw).join(' ') || "'none'";
}
