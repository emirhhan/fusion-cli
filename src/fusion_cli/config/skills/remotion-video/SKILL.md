---
name: remotion-video
description: Remotion ile React tabanlı video üretimi ve MP4 render. Proje kurulumu, kare tabanlı animasyon (useCurrentFrame, interpolate, spring), sahneler, uzun süren render'ı arka planda çalıştırma ve çıktıyı ffprobe ile doğrulama.
---

# Remotion video — kurulumdan doğrulanmış MP4'e

## Kurulum (uzun sürer: arka planda çalıştır)

```
run_shell(command="npx create-video@latest --yes --blank --no-tailwind video && cd video && npm i", background=true)
job_status(id=..., wait_s=600)
```
Çıktı yolu çalışma klasörüne göredir: `video/` içinden `../out/video.mp4` render et.

## Hareket kiti (ZORUNLU: sade "fade + yazı" slayt yapma)

Kurulumdan sonra kopyala:
`run_shell(command="cp -R '{SKILL_DIR}/kit' video/src/kit")`, logoyu `video/public/`a koy.
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

## Kare tabanlı animasyon kuralları (render'da yalnız bunlar çalışır)

- Hareketi `useCurrentFrame()` + `interpolate()` / `spring()` ile hesapla.
- CSS `transition`, `animation`, `@keyframes` ve Tailwind `animate-*` KULLANMA: render
  kare kare yapılır, bunlar çalışmaz ve video donuk çıkar.
- fps ve süreyi `useVideoConfig()`'ten al; `<Composition>`'da `durationInFrames = saniye × fps`.
- Sahne sürelerini FusionTimeline verisinde tanımla; elle Sequence örtüşmesi kurma.
- Metin: ana başlık ≥ 96 px, destek metni ≥ 44 px (1080p); kenarlarda 120 px güvenli alan.
- Görsel/font: `public/` + `staticFile()`; Google fontu `@remotion/google-fonts`.

## Render ve doğrulama (bitti demeden önce)

```
run_shell(command="cd video && npx remotion render <CompositionId> ../out/video.mp4", background=true)
job_status(id=..., wait_s=600)
run_shell(command="ffprobe -v error -show_entries stream=width,height,r_frame_rate:format=duration -of json out/video.mp4")
```
Süre, çözünürlük ve fps istenenle aynı olmalı. `npx remotion still <Id> --frame=<n> kare.png`
ile baş/orta/son kareyi al; boş ya da aynı kare çıkıyorsa animasyon çalışmıyor demektir.
