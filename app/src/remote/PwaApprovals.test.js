import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/dom';
import { approvalCard } from '../../../src/fusion_cli/remote/pwa/approvals.js';

beforeEach(() => document.body.replaceChildren());

it('teslim edilmeyen onay kartta hata gösterir, aynı kararı yeniden gönderir', async () => {
  const rpc = vi.fn().mockResolvedValueOnce({ok:true,data:{accepted:false}})
    .mockResolvedValueOnce({ok:true,data:{accepted:true}});
  const after = vi.fn();
  document.body.append(approvalCard({questionId:'q1',title:'Dosyayı yaz',options:['once','deny']},rpc,after));
  fireEvent.click(screen.getByRole('button',{name:'Bir kez izin ver'}));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/ulaşmadı|kabul edilmedi/i));
  expect(after).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Bir kez izin ver'}));
  await waitFor(() => expect(after).toHaveBeenCalledOnce());
  expect(rpc.mock.calls[0][1].decisionId).toBeTruthy();
  expect(rpc.mock.calls[1][1].decisionId).toBe(rpc.mock.calls[0][1].decisionId);
});

it('yüksek etkili onayı telefonda işlem ayrıntıları ve ikinci teyitle gönderir', async () => {
  const rpc=vi.fn(async method=>method==='approvals.challenge'?{ok:true,data:{challengeId:'challenge1'}}:{ok:true,data:{accepted:true}});
  document.body.append(approvalCard({questionId:'q2',title:'Komut çalıştır',stepUp:true,tool:'desktop_click',target:'Kaydet',reason:'Masaüstü işlemi',options:['once','deny']},rpc,vi.fn()));
  fireEvent.click(screen.getByRole('button',{name:'Bir kez izin ver'}));
  expect(rpc).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'İşlemi onayla'}));
  await waitFor(()=>expect(rpc).toHaveBeenCalledWith('approvals.respond',expect.objectContaining({questionId:'q2',choice:'once',confirmation:'challenge1'})));
});

it('alt ajanın onay isteğinde kart başlığı ajanı adlandırır (P-034)', () => {
  document.body.append(approvalCard({questionId:'q9',title:'Dosyayı yaz',agent:'denetci',options:['once','deny']},vi.fn(),vi.fn()));
  expect(screen.getByText('Alt ajan izin istiyor: denetci')).toBeTruthy();
  document.body.replaceChildren(approvalCard({questionId:'q10',title:'Dosyayı yaz',options:['once','deny']},vi.fn(),vi.fn()));
  expect(screen.getByText('İzin gerekiyor')).toBeTruthy();
});

it('masaüstü süreli onay yetkisi istiyor ve bu cihazda yoksa yalnız Reddet sunulur (P-040)', async () => {
  const rpc = vi.fn(async () => ({ ok: true, data: { accepted: true } }));
  document.body.append(approvalCard(
    { questionId: 'q3', title: 'Komut çalıştır', requiredScope: 'project.write', options: ['once', 'deny'] },
    rpc, vi.fn(), ['agent.run', 'project.write'], { required: true, secondsLeft: 0, canApprove: false },
  ));
  expect(screen.queryByRole('button', { name: 'Bir kez izin ver' })).toBeNull();
  expect(document.body.textContent).toMatch(/onay yetkisi verilmemiş/);
  fireEvent.click(screen.getByRole('button', { name: 'Reddet' }));
  await waitFor(() => expect(rpc).toHaveBeenCalledWith('approvals.respond', expect.objectContaining({ choice: 'deny' })));
});

it('süreli onay yetkisi varken kart eski kuralla onay düğmesini gösterir', () => {
  document.body.append(approvalCard(
    { questionId: 'q4', title: 'Komut', requiredScope: 'project.write', options: ['once', 'deny'] },
    vi.fn(), vi.fn(), ['project.write'], { required: true, secondsLeft: 3600, canApprove: true },
  ));
  expect(screen.getByRole('button', { name: 'Bir kez izin ver' })).toBeTruthy();
});
