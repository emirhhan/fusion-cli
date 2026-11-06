import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it} from 'vitest';
import {decodeDeliveryEvidence} from '../protocol/deliveryEvidence';
import fixtures from '../protocol/__fixtures__/verification-v39.json';
import {DeliveryCard} from './DeliveryCard';

afterEach(cleanup);
function card(payload: unknown) {
  const evidence=decodeDeliveryEvidence(payload);
  if(!evidence) throw new Error('Missing evidence');
  return render(<DeliveryCard evidence={evidence}/>);
}
const empty={schema_version:1,dogrulandi:null,engelliyor:false,yanlis_iddia:false,
  degisen:[],degisen_sayisi:0,sorunlar:[],sorun_sayisi:0,criteria_count:0,
  criteria_status_counts:{passed:0,failed:0,unverified:0},teslim_turu:'code'};

it('actual v38 unfinished research is neutral and preserves the passed checks in collapsed details',()=>{
  card(fixtures.reportIncomplete.evidence);
  expect(screen.getByText('Doğrulama tamamlanamadı')).toBeTruthy();
  expect(screen.queryByText('Doğrulama geçmedi')).toBeNull();
  const reason=screen.getByText('Olgusal kaynak denetimi tamamlanamadı.');
  const details=reason.closest('details')!;
  expect(details.open).toBe(false);
  fireEvent.click(screen.getByText('Doğrulama ayrıntıları'));
  expect(details.open).toBe(true);
  expect(screen.getByText('tarayıcı (1 sayfa, konsol temiz)').closest('details')).toBe(details);
});

it('ordinary no-criteria read-only chat has no empty delivery card even with default code kind',()=>{
  card(empty);
  expect(screen.queryByRole('region',{name:'Kanıt özeti'})).toBeNull();
});

it('zero-file research with an unverified criterion stays visible and neutral',()=>{
  card({...empty,engelliyor:true,criteria_count:1,criteria_status_counts:{passed:0,failed:0,unverified:1}});
  expect(screen.getByText('Doğrulama tamamlanamadı')).toBeTruthy();
  expect(screen.queryByText('Doğrulama geçmedi')).toBeNull();
});

it.each([
  {criteria_count:1,criteria_status_counts:{passed:0,failed:1,unverified:0}},
  {sorun_sayisi:2,ayrintilar_kisaltildi:true},
  {criteria_count:1,criteria:[{status:'failed'}]},
  {sorunlar:['Actual test failed'],sorun_sayisi:1},
])('real failure remains visible even without retained problem text: %j',change=>{
  card({...empty,...change});
  expect(screen.getByText('Doğrulama geçmedi')).toBeTruthy();
  expect(screen.queryByText('Doğrulama tamamlanamadı')).toBeNull();
});

it('false claim is never suppressed by empty file and criterion lists',()=>{
  card({...empty,yanlis_iddia:true});
  expect(screen.getByText('Başarı iddiası kanıtla uyuşmuyor')).toBeTruthy();
});

it.each([{schema_version:9},{engelliyor:'invalid'},{schema_version:undefined}])('unknown/invalid/legacy evidence remains an honest notice: %j',change=>{
  card({...empty,...change});
  expect(screen.getByRole('region',{name:'Kanıt özeti'})).toBeTruthy();
});

it('blocking without reported reason stays incomplete with an explicit missing-detail notice',()=>{
  card({...empty,engelliyor:true});
  expect(screen.getByText('Doğrulama tamamlanamadı')).toBeTruthy();
  fireEvent.click(screen.getByText('Doğrulama ayrıntıları'));
  expect(screen.getByText('Doğrulama engellendi; neden veya kontrol sonucu bildirilmedi.')).toBeTruthy();
});

it('actual Chrome passed-only source checks add no routine delivery card',()=>{
  card(fixtures.chromeReadOnly.evidence);
  expect(screen.queryByRole('region',{name:'Kanıt özeti'})).toBeNull();
});

it.each([
  {criteria:[{criterion_id:'test_suite',status:'passed'}]},
  {criteria_count:2},
  {criteria:[],ayrintilar_kisaltildi:true},
  {uyarilar:['Read-only audit caveat']},
])('meaningful audits and incomplete/truncated source metadata stay visible: %j',change=>{
  card({...fixtures.chromeReadOnly.evidence,...change});
  expect(screen.getByRole('region',{name:'Kanıt özeti'})).toBeTruthy();
  expect(screen.queryByText('Doğrulama geçmedi')).toBeNull();
});

it('invalid metadata cannot hide a known false claim',()=>{
  card({...empty,criteria_count:'invalid',yanlis_iddia:true});
  expect(screen.getByText('Başarı iddiası kanıtla uyuşmuyor')).toBeTruthy();
  expect(screen.getByText('Kanıt kaydı okunamadı')).toBeTruthy();
});

it.each([
  {keys:['criteria_count','criteria_status_counts','sorun_sayisi']},
  {keys:['sorun_sayisi']},
  {keys:['criteria_count']},
  {keys:['criteria_status_counts']},
  {keys:['criteria_count','criteria_status_counts']},
])('missing totals cannot hide a routine-looking source record: $keys',({keys})=>{
  const payload: Record<string,unknown>={...fixtures.chromeReadOnly.evidence};
  for(const key of keys) delete payload[key];
  card(payload);
  expect(screen.getByRole('region',{name:'Kanıt özeti'})).toBeTruthy();
});

it('truncated source-check text cannot hide the delivery notice',()=>{
  card({...fixtures.chromeReadOnly.evidence,
    criteria:fixtures.chromeReadOnly.evidence.criteria.map(row=>({...row,text_truncated:true}))});
  expect(screen.getByRole('region',{name:'Kanıt özeti'})).toBeTruthy();
  expect(screen.getByText('Bazı ayrıntılar gösterim sınırları nedeniyle kısaltıldı.')).toBeTruthy();
});

it.each([
  {keys:['criteria_count','criteria_status_counts','sorun_sayisi']},
  {keys:['sorun_sayisi']},
  {keys:['criteria_count']},
  {keys:['criteria_status_counts']},
  {keys:['criteria_count','criteria_status_counts']},
])('missing totals cannot hide a zero-criteria record: $keys',({keys})=>{
  const payload: Record<string,unknown>={...empty};
  for(const key of keys) delete payload[key];
  card(payload);
  expect(screen.getByRole('region',{name:'Kanıt özeti'})).toBeTruthy();
});
