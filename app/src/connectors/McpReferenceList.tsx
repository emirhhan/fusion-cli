import { useState } from 'react';
import { Button } from '../ui/Button';

/**
 * MCP sunucusunun istemleri ve kaynakları (P-049): sohbete yazılacak biçimiyle (`/mcp__…`,
 * `@sunucu:uri`) listelenir; "Kopyala" ile metin panoya alınır ve sohbet kutusuna yapıştırılır.
 * Liste yalnız gösterimdir: istem çalıştırmaz, kaynak okumaz.
 */
export type McpPromptRow = { command: string; usage: string; description: string };
export type McpResourceRow = { mention: string; name: string; mimeType: string };

const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

/** Eski çekirdek alanı göndermezse boş liste; bozuk satır tüm listeyi geçersiz kılar. */
export function referenceRows(value: Record<string, unknown>): { prompts: McpPromptRow[]; resources: McpResourceRow[] } {
  const rows = <T,>(raw: unknown, keys: string[]): T[] => {
    if (raw === undefined) return [];
    if (!Array.isArray(raw) || raw.length > 200 || !raw.every((item) => object(item) && keys.every((key) => typeof item[key] === 'string'))) throw new Error('İstem/kaynak listesi doğrulanamadı.');
    return raw as T[];
  };
  return {
    prompts: rows<McpPromptRow>(value.prompts, ['command', 'usage', 'description']).filter((row) => row.command.startsWith('/mcp__')),
    resources: rows<McpResourceRow>(value.resources, ['mention', 'name', 'mimeType']).filter((row) => row.mention.startsWith('@')),
  };
}

function CopyButton({ text, copy }: { text: string; copy: (text: string) => Promise<void> }) {
  const [state, setState] = useState<'' | 'ok' | 'error'>('');
  return <Button aria-label={`${text} kopyala`} onClick={() => { void copy(text).then(() => setState('ok'), () => setState('error')); }}>
    {state === 'ok' ? 'Kopyalandı' : state === 'error' ? 'Kopyalanamadı' : 'Kopyala'}
  </Button>;
}

const clipboard = async (text: string) => {
  if (!navigator.clipboard) throw new Error('Pano kullanılamıyor.');
  await navigator.clipboard.writeText(text);
};

export function McpReferenceList({ prompts, resources, copy = clipboard }: { prompts: McpPromptRow[]; resources: McpResourceRow[]; copy?: (text: string) => Promise<void> }) {
  return <>
    <section aria-label='MCP istemleri' className='mcp-reference-list'>
      <h3>İstemler</h3>
      {prompts.length
        ? <ul>{prompts.map((row) => <li key={row.command}>
          <code>{`${row.command} ${row.usage}`.trim()}</code>
          <p>{row.description || 'Açıklama sağlanmadı.'}</p>
          <CopyButton text={row.command} copy={copy} />
        </li>)}</ul>
        : <p>Bu sunucu istem bildirmedi.</p>}
    </section>
    <section aria-label='MCP kaynakları' className='mcp-reference-list'>
      <h3>Kaynaklar</h3>
      {resources.length
        ? <ul>{resources.map((row) => <li key={row.mention}>
          <code>{row.mention}</code>
          <p>{row.name || 'Ad sağlanmadı.'}{row.mimeType ? ` · ${row.mimeType}` : ''}</p>
          <CopyButton text={row.mention} copy={copy} />
        </li>)}</ul>
        : <p>Bu sunucu kaynak bildirmedi.</p>}
      <p>Kaynağı sohbete eklemek için anmayı mesajına yapıştır; içerik güvenilmez dış içerik olarak bağlama girer.</p>
    </section>
  </>;
}
