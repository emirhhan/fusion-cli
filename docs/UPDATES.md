# Uygulama içi güncellemeler

Fusion 0.3.0-alpha.9 ile kontrol paneline imzalı güncelleme desteği eklenmiştir.
İlk kurulum DMG ile yapılır. Sonraki güncellemeler kontrol panelindeki
“Güncellemeleri kontrol et” ve “İndir, kur ve yeniden başlat” düğmeleriyle kurulur.
Kurulumdan önce çalışan görevleri tamamlayın. Uygulama yazılabilir bir klasörde olmalıdır.

Dağıtım GitHub Releases üzerinden ücretsizdir. Apple noter onayı değildir;
macOS ilk açılışta ayrıca uyarabilir. Güncellemeler Tauri imzasıyla doğrulanır.

## Sürüm yayımlama (macOS)

1. Python ve Tauri sürüm numaralarını birlikte artırın.
2. `app` içinde `npm run bundle:mac` çalıştırın; testleri, runtime smoke kontrolünü ve
   `desktop_build/macos/smoke_app_bundle.py` paket denetimini geçirin. Paket her zaman
   Kits'i içerir (bkz. aşağıdaki "Kits paketlemesi"); Kits'siz paket üretmenin yolu yoktur.
3. Son imzalanmış uygulamadan güncelleme arşivini üretin:

```sh
.venv/bin/python desktop_build/macos/build_update.py \
  --app app/src-tauri/target/release/bundle/macos/Fusion.app \
  --output dagitim/update \
  --key /Users/kullanici/.config/fusion-release/updater.key
```

   Sürüm notu için `--notes "…"` ya da `--notes-file notlar.md` verin (P-066): manifestin
   `notes` alanına düz metin yazılır; uygulama Ayarlar › Güncellemeler'de "Sürüm notları ·
   <sürüm>" başlığında gösterir (HTML yorumlanmaz). Verilmezse genel bir cümle yazılır.
4. `v<SÜRÜM>` GitHub Release'ine DMG, `.app.tar.gz`, `.sig` ve `latest.json`
dosyalarını birlikte yükleyin. Manifestteki sürüm, mimari ve URL yayımlanan
dosyalarla eşleşmelidir. Release'i “latest” olarak işaretleyin.
5. Önceki kurulu sürümde kontrol → indir → kur → yeniden başlat zincirini deneyin.

Özel imza anahtarını depoya veya Release'e yüklemeyin. Yedeğini koruyun;
kaybolursa mevcut kurulumlar yeni anahtarla imzalanan güncellemeyi kabul etmez.
İmza sonrası uygulama arşivini değiştirmeyin. Intel ve Apple Silicon manifestleri
tek `latest.json` altında birleştirilmelidir; tek mimari paket diğerini güncellemez.
Terminal kurulumu bu mekanizmadan bağımsızdır; `setup.sh` veya `install.ps1` ile yenilenir.

## Kits paketlemesi

Masaüstü paketi (`bundle:mac`, `bundle:win`) Fusion Kits'i **her zaman** içerir;
indiren herkes Kits'i kurulu alır. `bundle:mac:kits` yalnız `bundle:mac` için geriye
uyumlu bir takma addır.

- `npm run kits:prepare` (`app/scripts/prepare-kits.mjs`) paket komutlarının ilk adımıdır.
  Kits deposunu (varsayılan: depo yanındaki `fusion-kits`, ya da `FUSION_KITS_DIR`)
  ana kopyanın çalışma ağacından değil **son commit'ten** paketler: geçici bir
  `git worktree` açar, ana kopyanın `node_modules`'üne bağlar, istemciyi orada
  `npm run build` ile yeniden derler, `scripts/kits-bundle.mjs` ile paketler ve
  geçici ağacı kaldırır. Kaydedilmemiş değişiklikler ve bayat `dist/` pakete girmez.
- Kits Node 24+ ister ve Node ikilisi pakete kopyalanır. macOS'ta ikili yalnız sistem
  kitaplıklarına bağlı olmalıdır; Homebrew `node`'u reddedilir (Homebrew'suz Mac'te
  açılmaz). Resmî ikiliyi şöyle gösterin:
  `FUSION_KITS_NODE="$(npx --yes --package=node@24.21.0 -- node -p process.execPath)" npm run bundle:mac`
- Kits deposu yoksa, git deposu değilse, `package.json`/`package-lock.json` HEAD'den
  sapmışsa ya da derleme düşerse betik açık hatayla durur; mevcut kaynaklar silinmez.
- Paketlenen Kits commit'i, commit tarihi ve Node sürümü
  `app/src-tauri/resources/kits/kits-manifest.json` dosyasına (pakette
  `Contents/Resources/kits/kits-manifest.json`) yazılır.
- `tauri.bundle.conf.json` ve `tauri.windows.bundle.conf.json` Kits kaynaklarını
  (`kits-manifest.json`, `node`/`node.exe`, `app/`) kendisi eşler; kaynak yoksa
  `tauri build` düşer.
- Kapılar: `smoke_app_bundle.py` ve `macos/build_update.py` paketteki Kits sunucusu,
  istemcisi, taşınabilir Node'u ve manifesti yoksa düşer; `windows/build_update.py`
  kurucuya giren Kits kaynağını doğrular; `scripts/release_manifest.py` Kits commit'i
  (`--kits-manifest` ya da `--kits-commit`) olmadan kanıt manifesti üretmez.

## Sürüm notları ve kanal (P-066)

Ayarlar › Güncellemeler kurulu sürümü ("Kurulu sürüm: 0.7.18 · kanal: kararlı") ve kontrol
sonrası manifestin `notes` alanını gösterir. Claude Code'un sürüm notları / beta kanalı
karşılığında **yalnız kararlı kanal** vardır: güncelleyicinin uç noktası `tauri.conf.json`'da
sabittir (`releases/latest/download/latest.json`). Beta kanalı için ayrı bir `beta.json`
yayımlamak ve Rust tarafında `updater_builder().endpoints()` ile ikinci uç nokta seçmek
gerekir; bu bir dağıtım kararıdır, arayüzde sahte bir seçici konmadı.

## Kimlik bilgileri

macOS'ta Fusion'ın API kasası kullanıcı veri dizinindeki `vault` altında tutulur.
Anahtar dosyası 0600, klasör 0700 izinlidir. Aynı macOS hesabındaki uygulamalara
karşı Keychain denetimi sağlamaz. Eski `secrets.enc` korunur; önceki izinle
sessizce okunabiliyorsa taşınır, aksi halde API anahtarları yeniden girilir.
Chrome web oturumları ayrı kalıcı profillerde, Chrome'un kendi çerez şifrelemesiyle kalır.
