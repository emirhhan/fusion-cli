# Fusion Masaüstü

Fusion'ın Tauri 2 + React tabanlı macOS uygulamasıdır. Uygulama, Python çalışma
zamanını ve Fusion çekirdeğini kendi paketinde taşır; son kullanıcıdan Terminal
veya CLI kurulumu istemez.

## Kullanıcı kurulumu

İmzalanmamış DMG'nin Finder üzerinden kurulumu ve ilk açılış adımları için
[KURULUM.md](KURULUM.md) belgesini izleyin.

## Geliştirici gereksinimleri

- Node.js 22
- Güncel kararlı Rust toolchain
- Python 3.11 veya üzeri ve depo kökündeki `.venv`
- Python ekstraları: `.[desktop,mcp,gateway]`

Depo kökünde:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,desktop,mcp,gateway]'
cd app
npm ci
```

## Geliştirme ve doğrulama

```bash
npm run tauri dev   # yerel uygulamayı aç
npm run check       # React, TypeScript ve Rust kalite kapıları
npm run bundle:mac  # paketli runtime + imzasız Fusion.app ve DMG
```

Üretilen dosyalar `src-tauri/target/release/bundle/` altındadır. Apple Developer
hesabı kullanılmadığı için imzalama ve notarization yapılmaz.

## Desteklenen macOS dağıtımı

Fusion'ın macOS masaüstü sürümü yalnız doğrudan indirilen, imzasız/noterlenmemiş
`.app` ve DMG olarak desteklenir. Talk yardımcı penceresinin tek, saydam ve
yuvarlatılmış yüzeyi Tauri'nin `macOSPrivateApi` seçeneğini gerektirir. Bu seçenek
Mac App Store kurallarıyla uyumlu değildir; dolayısıyla Mac App Store dağıtımı bu
ürünün desteklenen kanalları arasında değildir. Apple Developer hesabı edinilse
bile App Store hedeflenirse önce Talk saydamlığı özel API kullanmadan yeniden
tasarlanmalı ve `macOSPrivateApi` kaldırılmalıdır.
