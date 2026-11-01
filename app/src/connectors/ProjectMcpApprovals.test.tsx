import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ProtocolClient } from '../protocol/client';
import { ProjectMcpApprovals } from './ProjectMcpApprovals';
afterEach(cleanup);
it('bekleyen proje sunucusu için üç seçeneği sorar ve seçimi kaydeder (#246)', async () => {
  const request = vi.fn(async (name: string) => name === 'baglanti.proje_bekleyen'
    ? { ok: true, sunucular: [{ ad: 'github', hedef: 'npx -y github' }, { ad: 'linear', hedef: 'npx linear' }] }
    : { ok: true, sunucular: [{ ad: 'linear', hedef: 'npx linear' }] });
  const onChanged = vi.fn();
  render(<ProjectMcpApprovals client={{ request } as unknown as ProtocolClient} onChanged={onChanged} />);
  expect(await screen.findByText('Bu proje bir MCP sunucusu tanımlıyor: github')).toBeTruthy();
  expect(screen.getByText('1 sunucu daha onay bekliyor.')).toBeTruthy();
  fireEvent.click(screen.getByText('Bu sunucuyu kullan'));
  expect(await screen.findByText('Bu proje bir MCP sunucusu tanımlıyor: linear')).toBeTruthy();
  expect(request).toHaveBeenCalledWith('baglanti.proje_onay', { ad: 'github', secim: 'one' });
  expect(onChanged).toHaveBeenCalledOnce();
});
it('bekleyen yoksa hiçbir şey göstermez', async () => {
  const request = vi.fn(async () => ({ ok: true, sunucular: [] }));
  const { container } = render(<ProjectMcpApprovals client={{ request } as unknown as ProtocolClient} />);
  await Promise.resolve();
  expect(container.textContent).toBe('');
});
