---
name: remotion-video
description: Remotion ile kare tabanlı React video üretimi, MP4 render ve doğrulama.
---

# Remotion video

## Hareket kiti (sade "fade + yazı" yapma)

Üretimden önce sahne id/kind/duration planını
`scaffold_remotion(path="video",composition_id="Video",timeout_s=120,scenes=[…])` ile kaydet;
Host sabit `src/index.tsx` ve uyumlu tsconfig oluşturur. Yalnız `src/Composition.tsx`
`Video` exportunda sahneleri yaz; giriş/kit değiştirme, rename etme. Süre karedir.
Kit `{SKILL_DIR}/kit`; logoyu `video/public/`a koy.
Boş projede önce iskele; sonra yalnız bağımlılık kur, mevcut dosyaları ezme:
```
run_shell(command="cd video && npm init -y && npm install remotion @remotion/cli react react-dom && npm install -D typescript @types/react @types/react-dom", background=true)
job_status(id=..., wait_s=600)
```
`import {FusionTimeline} from "./kit";` — diğer kit bileşenleri de aynı kaynaktan.
Renkleri `kit/theme.ts`'ten markaya göre ayarla.
- Zeminde `<Aurora/>` + `<Particles/>`; süreleri `FusionTimeline` yönetir:
  `<FusionTimeline scenes={[{id:"features",kind:"feature",duration:120,props:{
  title:"Başlık",cards:[{title:"Hız",body:"Akıcı"}]}}]}/>`.
  Sürelerin toplamı composition süresiyle aynı; `from`/örtüşme hesaplama.
  `kind:"custom", component:Scene` özgün sahne içindir. İlk karede okunabilir
  başlık göster; opacity gecikmesiyle boşluğu gizleme. Timeline kesme yapar,
  gerçek FeatureScene oluşturur; bileşeni kopyalama, iç kit dosyalarını değiştirme.
  Bağımsız özel içerik `<SceneFade><CameraPush>` içinde.
- FeatureScene 1–3 eşit sütun tek satır; kamera/parallax içerir, dıştan sarma.
  Başlık 96, gövde 44 px. Font sonrası kapasite yetmezse sahneyi böl; küçültme/
  kırpma/kapı kaldırma. Bağımsız kullanımda SceneFade içerir.
- Özel başlık: `<KineticText text=... gradient/>` (96 px).
- Açılış/kapanış `<LogoReveal src="logo.png" title=... subtitle=.../>`; vurguda `<LightSweep/>`.
- Hiçbir sahne 1 sn'den uzun donuk kalmasın: her an en az iki katman hareket etsin.
- Kit varsayılan kamera/derinlik hareketine göre güvenli yer ayırır; özel sahnede
  120 px iç payı TÜM dönüşümlerden sonra koru; yazılar çakışmasın. Parallax
  normal akışta; gap kullan, kart width padding dahil dış genişliktir.
- En dış sabit AbsoluteFill'a data-fusion-canvas ekle; kamerayı İÇİNE koy.
- Timeline her kare boşluğu/çoklu okunabilir sahneyi denetler; yerel grace bu
  kapıyı körleştirmez. SceneFade içindeki LayoutAudit ilk 1 sn/son 0,5 sn dışında taşma,
  çakışma ve boş içeriği durdurur. Hata karesini ölç, konum/gap/içeriği düzelt.
  Kit dışı anlamlı içeriğe data-fusion-content ekle, dekorlara ekleme. Kapıyı koru.
- Sahneyi tam doldur; son 7 saniyeye soluk yazı/boş buffer koyma. 4 kartı böl.
- Tam render öncesinde her sahneden giriş sonrasında ve çıkış öncesinde still al.
  Still'ler geçmeden tam render başlatma. Hata karesini yeniden ölç; denetim hatası
  kalan videoyu tamamlandı diye sunma.

## Kare tabanlı animasyon

- Hareketi `useCurrentFrame()` + `interpolate()` / `spring()` ile hesapla.
- CSS `transition`, `animation`, `@keyframes` ve Tailwind `animate-*` KULLANMA: render
  kare kare yapılır, bunlar çalışmaz ve video donuk çıkar.
- fps/süre `useVideoConfig()`; host girişinde plan toplamı ve 1920×1080/30 sabittir.
- Metin: ana başlık ≥ 96 px, destek metni ≥ 44 px (1080p); kenarlarda 120 px güvenli alan.
- Görsel/font: `public/` + `staticFile()`; Google fontu `@remotion/google-fonts`.

## Render ve doğrulama (bitti demeden önce)

```
render_remotion(output="out/video.mp4")
job_status(id=..., wait_s=600)
run_shell(command="ffprobe -v error -show_entries stream=width,height,r_frame_rate:format=duration -of json out/video.mp4")
```
Kayıtlı plan/host browser ve yerel strict tsc kullanılır.
Başlangıç başarı değildir: job_status çıkışı, tüm sahne kareleri ve teslim kanıtı gerekir.
Baş/orta/son kareyi al; boş ya da aynı kare çıkıyorsa animasyon çalışmıyor demektir.
Host girişini/kit kapısını değiştirerek render hatasını geçiştirme.
