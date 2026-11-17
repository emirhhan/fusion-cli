# Fusion Masaüstü

Fusion'ın Tauri 2 + React tabanlı macOS uygulamasıdır. Uygulama, Python çalışma
zamanını ve Fusion çekirdeğini kendi paketinde taşır; son kullanıcıdan Terminal
veya CLI kurulumu istemez.

## Kullanıcı kurulumu

İmzalanmamış DMG'nin Finder üzerinden kurulumu ve ilk açılış adımları için
[KURULUM.md](KURULUM.md) belgesini izleyin.

## Geliştirici gereksinimleri

- Node.js 22
- Rust 1.90 veya üzeri (Tauri 2.12 gereksinimi)
- Python 3.11 veya üzeri ve depo kökündeki `.venv`
- Python ekstraları: `.[desktop,mcp,gateway]`

Depo kökünde:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,desktop,mcp,gateway]'
cd app
npm ci
```

## Sayfa düzeni: tam sayfa kuralı

Sohbet kenar çubuğu (Fusion başlığı, Yeni sohbet, Projeler) yalnız sohbet kabuğunda
görünür: sohbet ile komut paletinden açılan Görsel/Video oluştur. Sohbetle ilgisi
olmayan her yönetim ekranı — Ayarlar, Hesabım, Yardım, Kontrol Paneli, Beceriler ve
Ajanlar, MCP bağlantıları ve raydan açılan Zamanlananlar, Kitaplık, Kits — Ayarlar gibi
tam sayfa açılır ve "Kapat" önceki ekrana döner. Kural tek yerdedir:
`src/screens/pageLayout.ts` (`isFullPage`). Yeni sayfa, açıkça
`SOHBET_KABUGU_SAYFALARI`na eklenmedikçe tam sayfadır. Geri bildirim sayfa değil,
bulunulan ekranın üstünde açılan penceredir.

## Geliştirme ve doğrulama

```bash
npm run tauri dev   # yerel uygulamayı aç
npm run check       # React, TypeScript ve Rust kalite kapıları
npm run bundle:mac  # Kits + paketli runtime + imzasız Fusion.app ve DMG
```

`check` ve `check:ci`, Rust derlemesinden sonra `test:tauri-events` testini de
çalıştırır. Bu test kilitli Tauri sürümünün gerçek olay temizleme betiğini kullanır;
tek başına çalıştırmadan önce `src-tauri` içinde `cargo fetch --locked` gerekir.

Paket her zaman Fusion Kits'i içerir; `bundle:mac` önce `kits:prepare` ile Kits'i
son commit'ten derleyip paketler (Node 24+ için `FUSION_KITS_NODE`, ayrıntı:
`docs/UPDATES.md` › Kits paketlemesi).
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
