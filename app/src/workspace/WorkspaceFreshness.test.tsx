import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ProtocolClient } from '../protocol/client';
import type { ProcessController } from '../processes/useProcesses';
import { TestsPanel } from './TestsPanel';
import { PreviewPanel } from './PreviewPanel';
afterEach(cleanup);
it('aynı istemcide dosya revizyonu değişince komut ve Git durumu yeniden okunur', async () => {
  let changed = 1;
  const request = vi.fn(async (name: string) => name === 'proje.komut_onerileri' ? { ok: true, komutlar: [{ tur: 'test', ad: 'Test', komut: `test-${changed}` }] } : { ok: true, git: true, branch: 'main', degisen: changed, ileride: 0, geride: 0 });
  const client = { request } as unknown as ProtocolClient;
  const processes = { busy: false, processes: [] } as unknown as ProcessController;
  const { rerender } = render(<TestsPanel client={client} processes={processes} revision={0} />);
  await screen.findByText('test-1');
  changed = 2;
  rerender(<TestsPanel client={client} processes={processes} revision={1} />);
  await screen.findByText('test-2');
  expect(screen.queryByText('test-1')).toBeNull();
  expect(request).toHaveBeenCalledTimes(4);
});
it('aynı dosya yolu yeni revizyonda eski metni göstermeyi sürdürmez', async () => {
  let text = 'Old snapshot';
  const request = vi.fn(async () => ({ ok: true, yol: 'README.md', tur: 'text', mime: 'text/plain', boyut: text.length, base64: btoa(text) }));
  const client = { request } as unknown as ProtocolClient;
  const { rerender } = render(<PreviewPanel client={client} selectedPath="README.md" revision={0} />);
  await screen.findByText('Old snapshot');
  text = 'New snapshot';
  rerender(<PreviewPanel client={client} selectedPath="README.md" revision={1} />);
  await screen.findByText('New snapshot');
  expect(screen.queryByText('Old snapshot')).toBeNull();
  await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
});

it('dosya güncellenirken kullanıcının açık Web sekmesi korunur', async () => {
  const client = { request: vi.fn(async () => ({ ok: true, yol: 'README.md', tur: 'text', mime: 'text/plain', boyut: 1, base64: btoa('a') })) } as unknown as ProtocolClient;
  const { rerender } = render(<PreviewPanel client={client} selectedPath="README.md" revision={0} />);
  await screen.findByText('a');
  fireEvent.click(screen.getByRole('tab', { name: 'Web' }));
  rerender(<PreviewPanel client={client} selectedPath="README.md" revision={1} />);
  await waitFor(() => expect(client.request).toHaveBeenCalledTimes(2));
  expect(screen.getByRole('tab', { name: 'Web' }).getAttribute('aria-selected')).toBe('true');
});
