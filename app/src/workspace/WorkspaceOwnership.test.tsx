import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ProtocolClient } from '../protocol/client';
import { useWorkspace } from './useWorkspace';
import { FileExplorer } from './FileExplorer';
afterEach(cleanup);
it('eski dosyanın save ack başka seçilen dosyanın içeriğini değiştiremez', async () => {
  let finish!: (value: Record<string, unknown>) => void;
  const client = { request: vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === 'proje.yaz') return new Promise<Record<string, unknown>>((resolve) => { finish = resolve; });
    if (name === 'proje.oku') return { ok: true, yol: data.yol, tur: 'metin', mime: 'text/plain', boyut: 1, sha256: 'base', icerik: `Content ${data.yol}`, kesildi: false };
    return { ok: true, girdiler: [] };
  }) } as unknown as ProtocolClient;
  const { result } = renderHook(() => useWorkspace(client, '/project'));
  await waitFor(() => expect(result.current.state.loading).toBe(false));
  await act(async () => { await result.current.selectFile('a.txt'); });
  let saving!: Promise<Record<string, unknown>>;
  act(() => { saving = result.current.saveSelected('Saved A'); });
  await act(async () => { await result.current.selectFile('b.txt'); });
  await act(async () => { finish({ ok: true, sha256: 'new-a' }); await saving; });
  expect(result.current.state.selected).toMatchObject({ yol: 'b.txt', icerik: 'Content b.txt', sha256: 'base' });
  expect((await saving).gorunum_guncel).toBe(false);
});

it('kaydetme sürerken yazılan yeni taslak eski ack ile kapatılmaz', async () => {
  let finish!: (value: Record<string, unknown>) => void;
  const client = { request: vi.fn(async (name: string) => {
    if (name === 'proje.yaz') return new Promise<Record<string, unknown>>((resolve) => { finish = resolve; });
    if (name === 'proje.oku') return { ok: true, yol: 'a.txt', tur: 'metin', mime: 'text/plain', boyut: 1, sha256: 'base', icerik: 'Base', kesildi: false };
    return { ok: true, girdiler: [{ ad: 'a.txt', yol: 'a.txt', tur: 'dosya', boyut: 1, degistirilme: 0 }] };
  }) } as unknown as ProtocolClient;
  render(<FileExplorer client={client} root='/project' />);
  fireEvent.click(await screen.findByRole('treeitem', { name: 'a.txt' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Düzenle' }));
  fireEvent.change(screen.getByLabelText('Dosya içeriği'), { target: { value: 'Sent' } });
  fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
  fireEvent.change(screen.getByLabelText('Dosya içeriği'), { target: { value: 'Newer draft' } });
  await act(async () => { finish({ ok: true, sha256: 'accepted' }); });
  expect((screen.getByLabelText('Dosya içeriği') as HTMLTextAreaElement).value).toBe('Newer draft');
});

it('eski dosyanın kayıt hatası yeni dosyanın editöründe gösterilmez', async () => {
  let fail!: (error: Error) => void;
  const client = { request: vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === 'proje.yaz') return new Promise<Record<string, unknown>>((_resolve, reject) => { fail = reject; });
    if (name === 'proje.oku') return { ok: true, yol: data.yol, tur: 'metin', mime: 'text/plain', boyut: 1, sha256: 'base', icerik: 'Base', kesildi: false };
    return { ok: true, girdiler: ['a.txt', 'b.txt'].map((ad) => ({ ad, yol: ad, tur: 'dosya', boyut: 1, degistirilme: 0 })) };
  }) } as unknown as ProtocolClient;
  render(<FileExplorer client={client} root='/project' />);
  fireEvent.click(await screen.findByRole('treeitem', { name: 'a.txt' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Düzenle' }));
  fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
  fireEvent.click(screen.getByRole('treeitem', { name: 'b.txt' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Düzenle' }));
  await act(async () => { fail(new Error('Old A failure')); });
  expect(screen.queryByText('Error: Old A failure')).toBeNull();
});
