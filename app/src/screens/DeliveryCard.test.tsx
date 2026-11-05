import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {decodeDeliveryEvidence} from '../protocol/deliveryEvidence';
import {DeliveryCard} from './DeliveryCard';

afterEach(cleanup);

it('ölçülmeyen tarayıcı kontrolünü başarı kartında saklamaz', () => {
  const evidence = decodeDeliveryEvidence({schema_version:1, dogrulandi:false, engelliyor:false,
    yanlis_iddia:false, degisen:['index.html'], degisen_sayisi:1, sorunlar:[],
    uyarilar:['Tarayıcı ölçülemedi: Playwright kurulu değil']});
  if (!evidence) throw new Error('Kanıt çözülmedi');
  render(<DeliveryCard evidence={evidence}/>);
  expect(screen.getByText('Tarayıcı ölçülemedi: Playwright kurulu değil')).toBeTruthy();
  expect(screen.queryByText('Bildirilen kontroller geçti')).toBeNull();
});

it('belge kanıtı kapalı yerel ayrıntıda durur; dosya bağlantısı çalışır', () => {
  const evidence = decodeDeliveryEvidence({schema_version:1,dogrulandi:true,engelliyor:false,yanlis_iddia:false,
    degisen:['rapor.html'],degisen_sayisi:1,sorunlar:[],sunum:'document',kontroller:['Tarayıcıda açıldı'],
    oneriler:['Main önerisi'],degisiklik_ozeti:['67 yeni satır'],ayrintilar_kisaltildi:true});
  if (!evidence) throw new Error('Kanıt çözülmedi');
  const open = vi.fn();
  render(<DeliveryCard evidence={evidence} onOpenFile={open}/>);
  const summary=screen.getByText('Doğrulama ayrıntıları');
  const details=summary.closest('details')!;
  expect(details.open).toBe(false);
  fireEvent.click(summary);
  expect(details.open).toBe(true);
  expect(within(details).getByText('Tarayıcıda açıldı')).toBeTruthy();
  expect(within(details).getByText('Main önerisi')).toBeTruthy();
  expect(within(details).getByText('67 yeni satır')).toBeTruthy();
  expect(within(details).getByText(/kısaltıldı/)).toBeTruthy();
  fireEvent.click(screen.getByText('Değişen dosyalar (1)'));
  fireEvent.click(screen.getByRole('button',{name:'rapor.html dosyasını aç'}));
  expect(open).toHaveBeenCalledWith('rapor.html');
});

it('öneri metnini HTML olarak çalıştırmaz ve şüpheli belge işaretini kartta da reddeder', () => {
  const evidence = decodeDeliveryEvidence({schema_version:1,dogrulandi:true,engelliyor:false,yanlis_iddia:false,
    degisen:[],degisen_sayisi:0,sorunlar:[],sunum:'document',oneriler:['<img src="https://example.test/private">']});
  if (!evidence) throw new Error('Kanıt çözülmedi');
  const {container,rerender}=render(<DeliveryCard evidence={evidence}/>);
  expect(container.querySelector('img')).toBeNull();
  rerender(<DeliveryCard evidence={{...evidence, blocking:true}}/>);
  expect(screen.queryByText('Doğrulama ayrıntıları')).toBeNull();
  expect(screen.getByText('Doğrulama geçmedi')).toBeTruthy();
});

it('uyarı ve ölçülemeyen kontroller kapalı ayrıntının arkasında saklanmaz', () => {
  const evidence = decodeDeliveryEvidence({schema_version:1,dogrulandi:true,engelliyor:false,yanlis_iddia:false,
    degisen:[],degisen_sayisi:0,sorunlar:[],sunum:'document',uyarilar:['Teslim doğrulanmadı'],
    olculmeyen:['Gerçek gönderim ölçülmedi']});
  if (!evidence) throw new Error('Kanıt çözülmedi');
  render(<DeliveryCard evidence={evidence}/>);
  expect(screen.getByText('Teslim doğrulanmadı').closest('details')).toBeNull();
  expect(screen.getByText('Gerçek gönderim ölçülmedi').closest('details')).toBeNull();
  expect(screen.queryByText('Bildirilen kontroller geçti')).toBeNull();
});
