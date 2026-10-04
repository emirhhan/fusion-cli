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
`npm i` ve Chromium indirmesi 120 sn'yi aşar; ön planda çalıştırırsan kesilir.

## Kare tabanlı animasyon kuralları (render'da yalnız bunlar çalışır)

- Hareketi `useCurrentFrame()` + `interpolate()` / `spring()` ile hesapla.
- CSS `transition`, `animation`, `@keyframes` ve Tailwind `animate-*` KULLANMA: render
  kare kare yapılır, bunlar çalışmaz ve video donuk çıkar.
- fps ve süreyi `useVideoConfig()`'ten al; `<Composition>`'da `durationInFrames = saniye × fps`.
- Sahneleri `<Sequence from={...} durationInFrames={...}>` ile sırala; `premountFor={fps}`.
- Metin: başlık ≥ 84 px, destek metni ≥ 44 px (1080p); kenarlarda 80 px güvenli alan.
- Görsel/font: `public/` + `staticFile()`; Google fontu `@remotion/google-fonts`.

```tsx
const frame = useCurrentFrame(); const { fps } = useVideoConfig();
const giris = spring({ frame, fps, config: { damping: 200 } });
const opaklik = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: 'clamp' });
return <AbsoluteFill style={{ opacity: opaklik, transform: `translateY(${(1 - giris) * 60}px)` }}>…</AbsoluteFill>;
```

## Render ve doğrulama (bitti demeden önce)

```
run_shell(command="npx remotion render <CompositionId> out/video.mp4", background=true)
job_status(id=..., wait_s=600)
run_shell(command="ffprobe -v error -show_entries stream=width,height,r_frame_rate:format=duration -of json out/video.mp4")
```
Süre, çözünürlük ve fps istenenle aynı olmalı. `npx remotion still <Id> --frame=<n> kare.png`
ile baş/orta/son kareyi al; boş ya da aynı kare çıkıyorsa animasyon çalışmıyor demektir.
