import { useCallback, useEffect, useState } from 'react';
import type { ProtocolClient } from '../protocol/client';

// #246: Claude Code açılışta onaylanmamış her `.mcp.json` sunucusu için üç seçenek sorar.
type Pending = { ad: string; hedef: string };
type Choice = 'all' | 'one' | 'no';
const OPTIONS: Array<[Choice, string]> = [
  ['all', 'Bu ve gelecekteki bütün proje sunucularını kullan'],
  ['one', 'Bu sunucuyu kullan'],
  ['no', 'Bu sunucu olmadan devam et'],
];
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
function decode(value: unknown): Pending[] {
  if (!object(value) || value.ok !== true || !Array.isArray(value.sunucular)) return [];
  return value.sunucular.filter((row): row is Pending => object(row) && typeof row.ad === 'string' && typeof row.hedef === 'string');
}
export function ProjectMcpApprovals({ client, onChanged }: { client: ProtocolClient; onChanged?: () => void }) {
  const [rows, setRows] = useState<{ client: ProtocolClient; pending: Pending[] }>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    void client.request('baglanti.proje_bekleyen', {}).then((raw) => {
      if (active) setRows({ client, pending: decode(raw) });
    }).catch(() => { if (active) setRows({ client, pending: [] }); });
    return () => { active = false; };
  }, [client]);
  const choose = useCallback(async (ad: string, secim: Choice) => {
    setBusy(true);
    setError(undefined);
    try {
      const raw = await client.request('baglanti.proje_onay', { ad, secim });
      if (object(raw) && raw.ok === false) setError(typeof raw.metin === 'string' ? raw.metin : 'Seçim kaydedilemedi.');
      else { setRows({ client, pending: decode(raw) }); onChanged?.(); }
    } catch {
      setError('Seçim kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }, [client, onChanged]);
  const current = rows?.client === client ? rows.pending : [];
  const first = current[0];
  if (!first) return null;
  return <section className='project-mcp-approval' role='region' aria-label='Proje MCP sunucusu onayı'>
    <h3>Bu proje bir MCP sunucusu tanımlıyor: {first.ad}</h3>
    <p><code>{first.hedef}</code></p>
    <p>MCP sunucuları kod çalıştırabilir ve verine erişebilir; yalnız güvendiğin sunucuları kullan.</p>
    <div>{OPTIONS.map(([value, label]) => <button key={value} type='button' disabled={busy} onClick={() => void choose(first.ad, value)}>{label}</button>)}</div>
    {current.length > 1 && <p>{current.length - 1} sunucu daha onay bekliyor.</p>}
    {error && <p role='alert'>{error}</p>}
  </section>;
}
