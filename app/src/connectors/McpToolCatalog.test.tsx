import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ProtocolClient } from '../protocol/client';
import { McpToolCatalog } from './McpToolCatalog';
afterEach(cleanup);
const payload = (name: string) => ({ ok: true, schemaVersion: 1, total: 1, truncated: false, tools: [{ name, server: 'server', description: 'Sunucu açıklaması', effect: 'remote_read', parameters: [{ name: 'query', type: 'string', required: true, description: '' }], parametersTruncated: false }] });
it('kaynağı ve etkiyi gösterir; yalnız katalog isteği yapar', async () => {
  const request = vi.fn(async () => payload('server__lookup'));
  render(<McpToolCatalog client={{ request } as unknown as ProtocolClient} server='server' onClose={vi.fn()} />);
  await screen.findByText('server__lookup');
  expect(screen.getByText('Salt okuma')).toBeTruthy();
  fireEvent.click(screen.getByText('Parametre ayrıntıları'));
  expect(screen.getByText(/query/)).toBeTruthy();
  expect(request).toHaveBeenCalledExactlyOnceWith('baglanti.araclar', { ad: 'server' });
});
it('bilinmeyen şemayı doğrulanmış araç listesi gibi göstermez', async () => {
  render(<McpToolCatalog client={{ request: async () => ({ ...payload('unsafe'), schemaVersion: 99 }) } as unknown as ProtocolClient} server='server' onClose={vi.fn()} />);
  expect((await screen.findByRole('alert')).textContent).toContain('desteklenmiyor');
  expect(screen.queryByText('unsafe')).toBeNull();
});
it('eski istemcinin geç yanıtı güncel kataloğu değiştiremez', async () => {
  let finish!: (value: Record<string, unknown>) => void;
  const a = { request: () => new Promise((resolve) => { finish = resolve; }) } as unknown as ProtocolClient;
  const b = { request: async () => payload('new__lookup') } as unknown as ProtocolClient;
  const { rerender } = render(<McpToolCatalog client={a} server='server' onClose={vi.fn()} />);
  rerender(<McpToolCatalog client={b} server='server' onClose={vi.fn()} />);
  await screen.findByText('new__lookup');
  await act(async () => { finish(payload('old__lookup')); });
  expect(screen.queryByText('old__lookup')).toBeNull();
});
