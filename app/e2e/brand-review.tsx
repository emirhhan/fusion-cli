import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/theme/tokens.css';
import { Logo } from '../src/brand/Logo';
import { RuntimeSetup } from '../src/screens/RuntimeSetup';
import reference from '../src/brand/reference-logo.png';
import { applyTheme } from '../src/theme/theme';
applyTheme(new URLSearchParams(location.search).get('theme') === 'dark' ? 'dark' : 'light');
function Review() {
  const [busy, setBusy] = useState(true);
  return <main style={{ padding: 32, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32 }}>
    <section><h1>Fusion marka uygulaması</h1><p>Orijinal referans</p><img src={reference} alt='Kullanıcının orijinal marka referansı' width={544} /><div style={{ display: 'flex', alignItems: 'center', gap: 24, margin: '24px 0' }}><Logo size={96} title='Fusion F işareti' /><Logo size={32} /><span className='fusion-wordmark' style={{ fontSize: 36 }}>Fusion</span></div><h2>Başlık — sistem SF ailesi</h2><p data-testid='inter-sample'>Arayüz — Inter · Türkçe: İ ı Ğ ğ Ş ş Ç ç Ö ö Ü ü</p><pre data-testid='mono-sample' style={{ fontFamily: 'var(--font-mono)' }}>const fusion = "Güvenli ve doğrulanmış iş";</pre><button onClick={() => setBusy(!busy)}>Yüklemeyi bitir / başlat</button><p>Bu sayfa yalnız görsel onay için test verisi içerir.</p></section>
    <RuntimeSetup state={busy ? 'denetleniyor' : 'hazir'} progress={42} message={busy ? 'Çalışma ortamı denetleniyor…' : 'Çalışma ortamı hazır.'} version='0.4.6' onRepair={() => {}} />
    <div data-testid='brand-native-icon'><Logo size={512} /></div>
  </main>;
}
createRoot(document.getElementById('root')!).render(<Review />);
