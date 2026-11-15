---
name: remotion-video
description: Remotion React video/MP4 üretimi ve doğrulama.
---

# Remotion video
## Kit (fade + yazı yetmez)

Önce id/kind/duration planı:
`scaffold_remotion(path="video",composition_id="Video",timeout_s=120,scenes=[…])`.
Host `src/index.tsx`/uyumlu tsconfig üretir; yalnız `src/Composition.tsx` `Video` exportunu yaz;
giriş/kit değiştirme, rename etme. Süre=kare. Kit `{SKILL_DIR}/kit`; logo `video/public/`a.
Boş projede iskele → bağımlılık; ezme:
```
run_shell(command="cd video && npm init -y && npm install remotion @remotion/cli react react-dom && npm install -D typescript @types/react @types/react-dom", background=true)
job_status(id=..., wait_s=600)
```
Bileşenler: `import {FusionTimeline} from "./kit";`; marka: `kit/theme.ts`.
- Zemin `<Aurora/>` + `<Particles/>`; süre:
  `<FusionTimeline scenes={[{id:"features",kind:"feature",duration:120,props:{
  title:"Başlık",cards:[{title:"Hız",body:"Akıcı"}]}}]}/>`.
  Toplam=composition; `from`/örtüşme hesaplama. Özgün:
  `kind:"custom", component:Scene`; bağımsız içerik `<SceneFade><CameraPush>` içinde.
  İlk karede okunur başlık; opacity gecikmesiyle boşluk gizleme.
  Timeline keser, FeatureScene üretir; kopyalama.
- FeatureScene: 1–3 eşit sütun/tek satır; kamera/parallax/SceneFade içerir, dıştan sarma.
  Font sonrası taşanı/4 kartı böl; küçültme/kırpma/kapı kaldırma.
- Başlık `<KineticText text=... gradient/>`; açılış/kapanış
  `<LogoReveal src="logo.png" title=... subtitle=.../>`; vurgu `<LightSweep/>`.
- Her an ≥ 2 hareketli katman; 1 sn'den uzun donma yok.
- Kit kamera/derinlik payı ayırır. Özelde TÜM dönüşümler sonrası 120 px pay;
  Yazı çakışmasın. Parallax normal akış/gap; kart width padding dahil.
- Sabit dış AbsoluteFill'a data-fusion-canvas; kamera İÇİNDE.
- Timeline her kare boşluk/çoklu okunur sahneyi denetler; yerel grace körleştirmez.
  SceneFade/LayoutAudit ilk 1 sn/son 0,5 sn dışında taşma/çakışma/boş içerik/bölünen
  kelimeyi durdurur; hata karesini ölç/düzelt, kapıyı koru. Kit dışı anlamlı içeriğe
  data-fusion-content ekle; dekora ekleme.
- Sahneyi doldur; son 7 sn soluk yazı/boş buffer koyma.
- Tam render öncesi HER sahnede giriş sonrası/çıkış öncesi still geçsin.
  Hata karesini tekrar ölç; denetim hatasıyla teslim etme.
## Animasyon

- `useCurrentFrame()` + `interpolate()` / `spring()` kullan.
- CSS `transition`, `animation`, `@keyframes`, Tailwind `animate-*` KULLANMA:
  kare render'da çalışmaz, donar.
- fps/süre `useVideoConfig()`; host: plan toplamı, 1920×1080/30.
- 1080p: başlık ≥ 96/gövde ≥ 44 px; kenar 120 px.
- Ekran sade Türkçe; komut/yol/env yazma. Kullanıcının markası; "Fusion" asla ekleme.
- Görsel/font `public/` + `staticFile()`; Google: `@remotion/google-fonts`.
## Teslim öncesi doğrulama

```
render_remotion(output="out/video.mp4")
job_status(id=..., wait_s=600)
run_shell(command="ffprobe -v error -show_entries stream=width,height,r_frame_rate:format=duration -of json out/video.mp4")
```
Başlangıç başarı değildir: job_status çıkışı, tüm sahne kareleri ve teslim kanıtı gerekir.
Baş/orta/son kareyi al; boş ya da aynı kare çıkıyorsa animasyon çalışmıyor demektir.
Host girişini/kit kapısını değiştirerek render hatasını geçiştirme.
