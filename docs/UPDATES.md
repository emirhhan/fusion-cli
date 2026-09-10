# Uygulama içi güncellemeler

Fusion 0.3.0-alpha.9 ile kontrol paneline imzalı güncelleme desteği eklenmiştir.
İlk kurulum DMG ile yapılır. Sonraki güncellemeler kontrol panelindeki
“Güncellemeleri kontrol et” ve “İndir, kur ve yeniden başlat” düğmeleriyle kurulur.
Kurulumdan önce çalışan görevleri tamamlayın. Uygulama yazılabilir bir klasörde olmalıdır.

Dağıtım GitHub Releases üzerinden ücretsizdir. Apple noter onayı değildir;
macOS ilk açılışta ayrıca uyarabilir. Güncellemeler Tauri imzasıyla doğrulanır.

## Sürüm yayımlama (macOS)

1. Python ve Tauri sürüm numaralarını birlikte artırın.
2. `app` içinde `npm run bundle:mac` çalıştırın; testleri ve runtime smoke kontrolünü geçirin.
3. Son imzalanmış uygulamadan güncelleme arşivini üretin:

```sh
.venv/bin/python desktop_build/macos/build_update.py \
  --app app/src-tauri/target/release/bundle/macos/Fusion.app \
  --output dagitim/update \
  --key /Users/motogate/.config/fusion-release/updater.key
```

4. `v<SÜRÜM>` GitHub Release'ine DMG, `.app.tar.gz`, `.sig` ve `latest.json`
dosyalarını birlikte yükleyin. Manifestteki sürüm, mimari ve URL yayımlanan
dosyalarla eşleşmelidir. Release'i “latest” olarak işaretleyin.
5. Önceki kurulu sürümde kontrol → indir → kur → yeniden başlat zincirini deneyin.

Özel imza anahtarını depoya veya Release'e yüklemeyin. Yedeğini koruyun;
kaybolursa mevcut kurulumlar yeni anahtarla imzalanan güncellemeyi kabul etmez.
İmza sonrası uygulama arşivini değiştirmeyin. Intel ve Apple Silicon manifestleri
tek `latest.json` altında birleştirilmelidir; tek mimari paket diğerini güncellemez.
Terminal kurulumu bu mekanizmadan bağımsızdır; `setup.sh` veya `install.ps1` ile yenilenir.

## Kimlik bilgileri

macOS'ta Fusion'ın API kasası kullanıcı veri dizinindeki `vault` altında tutulur.
Anahtar dosyası 0600, klasör 0700 izinlidir. Aynı macOS hesabındaki uygulamalara
karşı Keychain denetimi sağlamaz. Eski `secrets.enc` korunur; önceki izinle
sessizce okunabiliyorsa taşınır, aksi halde API anahtarları yeniden girilir.
Chrome web oturumları ayrı kalıcı profillerde, Chrome'un kendi çerez şifrelemesiyle kalır.
