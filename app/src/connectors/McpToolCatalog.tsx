import { useEffect, useState } from 'react';
import type { ProtocolClient } from '../protocol/client';
import { Button } from '../ui/Button';
import './McpToolCatalog.css';
import { ConnectorDialog } from './ConnectorDialog';
type Parameter = { name: string; type: string; required: boolean; description: string };
type Tool = { name: string; server: string; description: string; effect: string; parameters: Parameter[]; parametersTruncated: boolean };
type Catalog = { tools: Tool[]; total: number; truncated: boolean };
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
function decode(value: unknown): Catalog {
  if (!object(value) || value.ok !== true) throw new Error('Araç kataloğu okunamadı. Bağlantıyı test edip yeniden dene.');
  if (value.schemaVersion !== 1) throw new Error('Bu katalog sürümü desteklenmiyor. Uygulamayı güncelle.');
  if (!Array.isArray(value.tools) || value.tools.length > 200 || !Number.isSafeInteger(value.total) || (value.total as number) < value.tools.length || typeof value.truncated !== 'boolean') throw new Error('Katalog verisi doğrulanamadı.');
  for (const tool of value.tools) {
    if (!object(tool) || !['name', 'server', 'description', 'effect'].every((key) => typeof tool[key] === 'string') || !Array.isArray(tool.parameters) || tool.parameters.length > 40 || typeof tool.parametersTruncated !== 'boolean') throw new Error('Araç tanımı doğrulanamadı.');
    for (const p of tool.parameters) if (!object(p) || !['name', 'type', 'description'].every((key) => typeof p[key] === 'string') || typeof p.required !== 'boolean') throw new Error('Parametre tanımı doğrulanamadı.');
  }
  return value as unknown as Catalog;
}
const EFFECTS: Record<string, string> = { remote_read: 'Salt okuma', remote_interact: 'Sayfa etkileşimi', remote_write: 'Değişiklik yapabilir', remote_destructive: 'Yıkıcı işlem' };
export function McpToolCatalog({ client, server, onClose }: { client: ProtocolClient; server: string; onClose: () => void }) {
  const [attempt, retry] = useState(0);
  const [result, setResult] = useState<{ client: ProtocolClient; server: string; catalog?: Catalog; error?: string }>();
  const current = result?.client === client && result.server === server ? result : undefined;
  useEffect(() => {
    let active = true;
    setResult(undefined);
    void client.request('baglanti.araclar', { ad: server }).then((raw) => {
      const catalog = decode(raw);
      if (active) setResult({ client, server, catalog });
    }).catch((error) => {
      if (active) setResult({ client, server, error: error instanceof Error ? error.message : 'Katalog okunamadı.' });
    });
    return () => { active = false; };
  }, [client, server, attempt]);
  return <ConnectorDialog label={`${server} araç kataloğu`} onClose={onClose}><section className='mcp-tool-catalog'>
    <header><h2>{server} araçları</h2><Button onClick={onClose}>Kapat</Button></header>
    <p>Bu görünüm sunucunun araç tanımlarını gösterir; araç çalıştırmaz veya izin vermez. Açıklamalar sunucu tarafından sağlanır.</p>
    {!current && <p role='status'>Araç kataloğu yükleniyor…</p>}
    {current?.error && <p role='alert'>{current.error}</p>}
    {current?.catalog && <>
      <p>{current.catalog.total} araç{current.catalog.truncated ? ' · İlk 200 araç gösteriliyor.' : ''}</p>
      {!current.catalog.tools.length && <p>Bu sunucu araç bildirmedi.</p>}
      <ul>{current.catalog.tools.map((tool, index) => <li key={`${tool.name}-${index}`}>
        <strong>{tool.name}</strong><p>Kaynak: {tool.server} · <span>{EFFECTS[tool.effect] ?? 'Etki bilinmiyor; onay yeniden değerlendirilir'}</span></p>
        <p>{tool.description || 'Açıklama sağlanmadı.'}</p>
        <details><summary>Parametre ayrıntıları</summary>
          {tool.parameters.length ? <ul>{tool.parameters.map((p, i) => <li key={`${p.name}-${i}`}><code>{p.name}</code> · {p.type} · {p.required ? 'Zorunlu' : 'İsteğe bağlı'} {p.description}</li>)}</ul> : <p>Parametre tanımı sağlanmadı.</p>}
          {tool.parametersTruncated && <p>İlk 40 parametre gösteriliyor.</p>}
          <p>Örnek ve varsayılan değerler bu görünümde toplanmaz.</p>
        </details>
      </li>)}</ul>
    </>}
    <Button disabled={!current} onClick={() => retry((n) => n + 1)}>Kataloğu yenile</Button>
  </section></ConnectorDialog>;
}
