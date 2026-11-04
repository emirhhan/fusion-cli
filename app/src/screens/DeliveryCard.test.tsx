import {render, screen} from '@testing-library/react';
import {expect, it} from 'vitest';
import {decodeDeliveryEvidence} from '../protocol/deliveryEvidence';
import {DeliveryCard} from './DeliveryCard';

it('ölçülmeyen tarayıcı kontrolünü başarı kartında saklamaz', () => {
  const evidence = decodeDeliveryEvidence({schema_version:1, dogrulandi:false, engelliyor:false,
    yanlis_iddia:false, degisen:['index.html'], degisen_sayisi:1, sorunlar:[],
    uyarilar:['Tarayıcı ölçülemedi: Playwright kurulu değil']});
  if (!evidence) throw new Error('Kanıt çözülmedi');
  render(<DeliveryCard evidence={evidence}/>);
  expect(screen.getByText('Tarayıcı ölçülemedi: Playwright kurulu değil')).toBeTruthy();
  expect(screen.queryByText('Bildirilen kontroller geçti')).toBeNull();
});
