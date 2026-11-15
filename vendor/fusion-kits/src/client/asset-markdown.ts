/** Dosyanın taşınabilir kimliği Markdown'da kalır; yerel yol belgeye yazılmaz. */
import { markdownManager } from './editor/markdown';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function assetLink(id: string, label: string): string {
  if (!UUID.test(id)) throw new Error('Dosya kimliği geçersiz.');
  const name = label
    .replace(/[\r\n\0]/g, ' ')
    .slice(0, 256)
    .replace(/[\\[\]]/g, '\\$&');
  return `[${name || 'Görsel'}](fusion-asset:${id})`;
}
export function assetIds(markdown: string): string[] {
  const pending: unknown[] = [markdownManager.instance.lexer(markdown)];
  const ids = new Set<string>();
  while (pending.length) {
    const value = pending.pop();
    if (!value || typeof value !== 'object') continue;
    const item = value as Record<string, unknown>;
    if (
      item.type === 'code' ||
      item.type === 'codespan' ||
      item.type === 'html'
    )
      continue;
    if (
      item.type === 'link' &&
      typeof item.href === 'string' &&
      item.href.startsWith('fusion-asset:')
    ) {
      const id = item.href.slice('fusion-asset:'.length);
      if (UUID.test(id)) ids.add(id);
    }
    pending.push(...Object.values(item));
  }
  return [...ids];
}
