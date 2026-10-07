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
Kurulum 120 sn'yi aşar; arka planda çalıştır.
Proje `video/`dadır; render komutları `cd video &&` ile çalışır.
Kullanıcı bir çıktı yolu verdiyse (ör. `out/video.mp4`) o yol ÇALIŞMA KLASÖRÜNE göredir:
`video/` içinden `../out/video.mp4` diye render et. `video/out/` istenen yer DEĞİLDİR.

## Hareket kiti (ZORUNLU: sade "fade + yazı" slayt yapma)

Hazır, render'da test edilmiş bileşenler: `{SKILL_DIR}/kit`. Kurulumdan sonra kopyala:
`run_shell(command="cp -R '{SKILL_DIR}/kit' video/src/kit")`, logoyu `video/public/`a koy.
`import { Aurora, Particles, LightSweep, KineticText, CameraPush, Parallax, LogoReveal,
FeatureCard, SceneFade } from "./kit";` — renkleri `kit/theme.ts`'ten markaya göre ayarla.
- Her sahne: zeminde `<Aurora/>` + `<Particles/>`, içerik `<SceneFade><CameraPush>` ile sarılı.
- Başlık `<KineticText text=... gradient/>` (≥96 px); özellikler `<FeatureCard index={i}/>`.
- Açılış/kapanış `<LogoReveal src="logo.png" title=... subtitle=.../>`; vurguda `<LightSweep/>`.
- Hiçbir sahne 1 sn'den uzun donuk kalmasın: her an en az iki katman hareket etsin.
- Bir sahnede en çok 3 kart; içerik 1920×1080'in 120 px iç payında kalsın (kenardan
  taşan/kesilen kart ya da başlık olmasın); başlık ile alt yazı üst üste binmesin.
- `Parallax` normal akışta bir `div`dir: başlık, alt yazı ve kartları aynı flex/grid
  sütununda, aralarında gap ile sırala. Kartın width değeri padding DAHİL dış genişliktir.
- Bileşimin en dıştaki sabit `<AbsoluteFill>` öğesine `data-fusion-canvas` ekle;
  kamera dönüşümlerini onun İÇİNE koy. Denetim güvenli alanı bu sabit tuvalde ölçer.
- `SceneFade` her sahnede gerçek DOM yerleşimini denetler: ilk 1 sn giriş ve son
  0,5 sn çıkış dışında taşma, çakışma ya da okunabilir içerik yoksa render HATA verir.
  Hata sınırlarını oku: üst/sol taşmada konumu düzelt; font küçültmek konumu düzeltmez.
  Başlık, kart ve gap toplamını güvenli yüksekliğe sığdır; üst payı artırınca altı ölç.
  Hatadaki kare ve bileşen adını okuyup yerleşimi DÜZELT; denetimi kaldırma. Özel
  sahne `SceneFade` kullanmıyorsa Sequence İÇİNDE `<LayoutAudit>` ile sar. Kit dışı
  içerik gruplarına `data-fusion-content="anlamlı ad"` ekle; dekorlara ekleme.
- Her sahneyi tam süreyle doldur; son 7 saniyeye soluk yazı/boş buffer koyma. Çok
  özellik varsa 4 kartı tek sahneye sıkıştırmak yerine ayrı sahneler kullan.
- Tam render öncesinde her sahneden giriş sonrasında ve çıkış öncesinde still al.
  Still'ler geçmeden tam render başlatma; hatayı düzelttikten sonra önce hata karesini
  yeniden ölç. Sonra MP4 render et; denetim hatası kalan videoyu tamamlandı diye sunma.

## Kare tabanlı animasyon kuralları (render'da yalnız bunlar çalışır)

- Hareketi `useCurrentFrame()` + `interpolate()` / `spring()` ile hesapla.
- CSS `transition`, `animation`, `@keyframes` ve Tailwind `animate-*` KULLANMA: render
  kare kare yapılır, bunlar çalışmaz ve video donuk çıkar.
- fps ve süreyi `useVideoConfig()`'ten al; `<Composition>`'da `durationInFrames = saniye × fps`.
- Sahneleri `<Sequence from={...} durationInFrames={...}>` ile sırala; `premountFor={fps}`.
- Metin: başlık ≥ 84 px, destek metni ≥ 44 px (1080p); kenarlarda 120 px güvenli alan.
- Görsel/font: `public/` + `staticFile()`; Google fontu `@remotion/google-fonts`.



## Render ve doğrulama (bitti demeden önce)

```
run_shell(command="cd video && npx remotion render <CompositionId> ../out/video.mp4", background=true)
job_status(id=..., wait_s=600)
run_shell(command="ffprobe -v error -show_entries stream=width,height,r_frame_rate:format=duration -of json out/video.mp4")
```
Süre, çözünürlük ve fps istenenle aynı olmalı. `npx remotion still <Id> --frame=<n> kare.png`
ile baş/orta/son kareyi al; boş ya da aynı kare çıkıyorsa animasyon çalışmıyor demektir.
