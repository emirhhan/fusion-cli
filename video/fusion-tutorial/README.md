# Fusion CLI — Eğitim Videosu (Remotion)

Sıfırdan öğrenen biri için Fusion CLI'yi anlatan, kod ile üretilen bir eğitim videosu.

## Çalıştırma

```bash
cd video/fusion-tutorial
npm install

# Canlı önizleme (tarayıcıda Remotion Studio)
npm start

# Tek kare önizleme (out/preview.png)
npm run still

# Tam videoyu render et (out/fusion-tutorial.mp4)
npm run build
```

- Çözünürlük: 1920×1080, 30fps.
- Kompozisyon kimliği: `FusionTutorial`.

## İçerik (sahneler)

1. Açılış / kimlik
2. Fusion nedir? (iki motor, öz-öğrenme, ücretsiz)
3. Kurulum (`make setup`)
4. İki motor: `agent` vs `fusion`
5. Çalışma profilleri (`/mode` · auto/low/medium/high/max)
6. Reasoning effort (`/effort`, mode ≠ effort)
7. Model seçimi (`/model`, `/development`, eligibility rozetleri)
8. Sağlayıcılar (`/providers`, `/providers add`)
9. Otomatik sağlamlık (`/health`, circuit breaker, güvenilirlik)
10. Güvenlik / geri alma / öğrenme (`/plan`, `/undo`, `/verify`, `/good`)
11. En verimli kullanım
12. Kapanış

## Not — web sağlayıcıları

Video, sağlayıcıları **gerçek durumuyla** anlatır: resmî OpenAI/Gemini/Anthropic API'leri
ve kendi barındırdığın uçlar çalışır. ChatGPT/Gemini gibi tüketici **web** arayüzleri
`/providers`'da "framework (adaptör yok)" olarak görünür; bağlanması kullanıcının kendi
yetkili transport'unu gerektirir (bkz. `docs/WEB_PROVIDERS.md`).
