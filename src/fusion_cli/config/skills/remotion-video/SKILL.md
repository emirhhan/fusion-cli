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
Kullanıcı bir çıktı yolu verdiyse (ör. `out/video.mp4`) o yol ÇALIŞMA KLASÖRÜNE göredir:
`video/` içinden `../out/video.mp4` diye render et. `video/out/` istenen yer DEĞİLDİR.

## Hareket kiti (ZORUNLU: sade "fade + yazı" slayt yapma)

Hazır, render'da test edilmiş bileşenler: `{SKILL_DIR}/kit`. Kurulumdan sonra kopyala:
`run_shell(command="cp -R '{SKILL_DIR}/kit' video/src/kit")`, logoyu `video/public/`a koy.
`import { Aurora, Particles, LightSweep, KineticText, CameraPush, Parallax, LogoReveal,
FeatureCard, FeatureScene, SceneFade } from "./kit";` — renkleri `kit/theme.ts`'ten markaya göre ayarla.
- Zeminde `<Aurora/>` + `<Particles/>`; özel içerik `<SceneFade><CameraPush>` içinde.
- Özelliklerde doğrudan `<FeatureScene title="Başlık" subtitle="Destek"
  cards={[{title:"Hız",body:"Kısa açıklama"}]} />` kullan: 1–3 eşit sütun tek satır.
  SceneFade/CameraPush/Parallax İÇİNDEDİR; dıştan tekrar sarma. Başlık 96, destek ve
  kart gövdesi 44 px; font sonrası doğal yükseklik sığmazsa metni/sahneyi böl.
  Font küçültme/kırpma/kapı kaldırma. Elle FeatureCard: bodyFontSize={44}, wrapText.
- Özel başlık: `<KineticText text=... gradient/>` (96 px).
- Açılış/kapanış `<LogoReveal src="logo.png" title=... subtitle=.../>`; vurguda `<LightSweep/>`.
- Hiçbir sahne 1 sn'den uzun donuk kalmasın: her an en az iki katman hareket etsin.
- Kit varsayılan kamera/derinlik hareketine göre güvenli yer ayırır; özel sahnede
  1920×1080 tuvalin 120 px iç payını TÜM dönüşümlerden sonra koru. Başlık/alt yazı
  üst üste binmesin. Parallax normal akıştadır; flex/grid gap kullan, kart width
  padding dahil dış genişliktir.
- En dış sabit AbsoluteFill'a data-fusion-canvas ekle; kamerayı İÇİNE koy.
- SceneFade içindeki LayoutAudit ilk 1 sn/son 0,5 sn dışında gerçek taşma,
  çakışma ve boş içeriği durdurur. Hata karesi/bileşenini oku; konumu, gap ve
  içerik miktarını düzelt, üst pay değişince altı ölç. Özel sahne SceneFade
  kullanmıyorsa Sequence İÇİNDE LayoutAudit kullan. Kit dışı anlamlı içeriğe
  data-fusion-content ekle, dekorlara ekleme. Denetimi kaldırma.
- Sahneyi tam doldur; son 7 saniyeye soluk yazı/boş buffer koyma. 4 kartı böl.
- Tam render öncesinde her sahneden giriş sonrasında ve çıkış öncesinde still al.
  Still'ler geçmeden tam render başlatma. Hata karesini yeniden ölç; denetim hatası
  kalan videoyu tamamlandı diye sunma.

## Kare tabanlı animasyon kuralları (render'da yalnız bunlar çalışır)

- Hareketi `useCurrentFrame()` + `interpolate()` / `spring()` ile hesapla.
- CSS `transition`, `animation`, `@keyframes` ve Tailwind `animate-*` KULLANMA: render
  kare kare yapılır, bunlar çalışmaz ve video donuk çıkar.
- fps ve süreyi `useVideoConfig()`'ten al; `<Composition>`'da `durationInFrames = saniye × fps`.
- Sahneleri `<Sequence from={...} durationInFrames={...}>` ile sırala; `premountFor={fps}`.
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
