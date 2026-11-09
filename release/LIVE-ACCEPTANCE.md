# Canlı frozen-runtime kabulü (K27)

Yayın kapısı `release_manifest.py --require-live-acceptance` komutudur. Eksik,
48 saatten eski, commit/sürüm/artefakt/görev/tekrar/source/scorer/model/config
kimliği uyuşmayan rapor durur. Yalnız JSON PASS alanı yeterli değildir: bağımsız
verifier imzası ve **rapordan ayrı güvenilir kanaldan alınmış** public-key SHA256
kimliği zorunludur. Raporun kendi anahtarı yetki kaynağı değildir. Geliştirme
manifesti bu bayrak olmadan `not_measured`, `claimsReady: false` kalabilir.

## Çalışan aşamalar

1. Build işi, checkout kaynak/puanlayıcı kimliğini `release-build.json` olarak
   gerçek PyInstaller onedir paketine ekler. Kimlik; Python kaynağı yanında
   paket verilerini/defaults, build/entrypoint/spec, frozen observer, release
   scripts, tests ve workflow girdilerini kapsar. Yol ve sıralama POSIX biçiminde,
   checkout metinleri LF'dir. Bu CI build kökenidir; rastgele yerel arşivin git
   kökenine dair bir kriptografik iddia değildir.
2. Her hedefin **aynı masaüstü kaynak arşivi**, hedef adıyla ayrıca gerçek yayın
   artefaktı olur. `release_live.py` bu arşivi SHA256/dosya kapsamı/bağlantı
   denetiminden geçirip çıkarır ve içindeki gerçek `fusion --release-observer
   app` ikilisini mevcut `evals.live_drive` stdio sürücüsüyle çalıştırır. Kaynak
   `python -m fusion_cli` çalıştırmasını paketli çalıştırma diye sunmaz.
3. Donmuş runtime, mevcut `ConfigObserver` üzerinden gerçekten seçilmiş model
   ve efektif config gözlemlerini yayınlar. Host sürücü çağrı olaylarını ve her
   görev/tekrarın son dosya özetini kaydeder. Actor bir kabul hükmü üretmez.
4. Ayrı, temiz Linux verifier işi; aynı aday artefaktları ve kayıtları alır.
   `release_verify.py`, mevcut `AgentTaskExecutor` temiz tohum/korunmuş kabul
   girdilerini kullanarak **her görev/tekrarın denetimini yeniden çalıştırır**.
   Her kabul subprocess'i bubblewrap ile ayrı PID/ağ namespace'inde; host salt
   okunur, yalnız temiz `/workspace` ve özel `/tmp` yazılabilir, ortam temizdir.
   Aday kodu host verifier kayıtlarını/anahtarını değiştiremez. MCP aday callback'i
   ayrıca ayrı süreçtedir; güvenilir ebeveyn gerçek MCP oturumundaki listeleme ve
   ping çağrılarının sahibidir. `SystemExit(0)`/`os._exit(0)` veya aday `json.py`
   dosyası doğrulamayı atlayıp kabul alamaz.
5. Verifier; gerçek çağrı/model kimliklerini, görev bütçesini, bağımsız denetim
   sonucunu, yürütme sonu bayt eşitliğini, platform kümesini ve onaylı config
   özetini kontrol eder. Sonra, actor işleri bittikten ve denetim namespace'leri
   kapandıktan sonra, yalnız kendi host'unda yeni Ed25519 anahtarı oluşturur.
   Kanıtı imzalar; private key yayın artefaktına veya actor ortamına girmez.
   Publication, public-key fingerprint'ini verifier **iş çıktısından** alır;
   actor artefaktından almaz. Dosyalar yayın öncesi tekrar özetlenir.

## Açık ve korunmuş kabul profili

`release/acceptance-profile.yaml` yalnız bu ölçüme aittir; kullanıcı ayarına
kurulmaz. Oturumda seçilmiş model korunur:
`nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b`, 8192 token, 600 sn istek timeout,
provider retry 0, AUTO effort ve self_review açık. Profilin sır içermeyen
onaylı kimlikleri anahtar/ortam/kullanıcı config yüklemeden hesaplanır:

```sh
PYTHONPATH=src:. python scripts/release_profile.py release/acceptance-profile.yaml
```

Yetki sınırı için açık ek kısıtlar vardır: root dışı okuma/yazma kapalı;
`write_root` shell sandbox ve `fail_if_unavailable` zorunlu; unsandboxed,
excluded command, extra write root ve zayıflatılmış namespace yoktur. Frozen
kabul girişinde yalnız native dosya araçları ve **sandbox içindeki** `run_shell`
açılır. MCP/process/browser başlatıcıları, otomatik dış doğrulama komutları ve
MCP bootstrap bu profile dahil değildir. Python çalıştırılacaksa aynı shell
sandbox'ından geçer. Gerçek MCP kontrolü ayrı bağımsız denetçiye aittir.

Mevcut shell sandbox genel temp dizinlerini yazılabilir tutar. Bu yüzden host
runtime/config ve observer çıktı kökleri `/tmp`, `TMPDIR` ve diğer
`temporary_roots` dışında olmalıdır; `release_live.py` bu koşulu doğrular.
Host scratch çıktı dizininin yanında oluşur. Profil değiştirilmez, orijinal
kullanıcı config dosyası yazılmaz. Yürütücü gerçekten gözlenen config özetini
onaylı profil projeksiyonuyla karşılaştırır; rapordan kendiliğinden onay türetmez.

## Yerel desteklenen frozen çalıştırma

Kaynak değişiklikleri tamamlanıp aynı checkout'tan runtime derlendikten sonra,
aşağıdaki actor komutu **gerçek sağlayıcı çağrısı yapar**. Bu düzeltme sırasında
çalıştırılmadı; testler sağlayıcısızdır. Gerekli sağlayıcı değişkeninin adı açık
olarak verilir; diğer host ortamı çocuğa aktarılmaz.

```sh
PYTHONPATH=src:. python scripts/release_live.py \
  --archive /absolute/fusion-runtime-aarch64-apple-darwin.tar.gz \
  --manifest /absolute/fusion-runtime-aarch64-apple-darwin.json \
  --config release/acceptance-profile.yaml \
  --version VERSION --commit FULL_SHA --provider-env NVIDIA_NIM_API_KEY \
  --out /absolute/non-temp/acceptance-run-aarch64
```

Ayrı Linux host/CI işinde, bubblewrap kurulu ve kullanılabilirken:

```sh
PYTHONPATH=src:. python scripts/release_verify.py \
  --runs /absolute/downloaded-runs --artifacts /absolute/exact-candidate \
  --config release/acceptance-profile.yaml --version VERSION --commit FULL_SHA \
  --target aarch64-apple-darwin --out /absolute/verifier-evidence
```

Bu tek hedef ölçümüdür. Tam desktop publication politikası iki Mac hedefi ve
Windows hedefinin tümünü gerektirir. Çıktının salt okunur dosya modu veya aynı
kullanıcı altında bir dizin yolu OS izolasyonu yerine geçmez. Yerel güven
sınırı ayrıca korunmalıdır; CI'da build/runner host'u ve ayrı verifier job kanalı
korunmuş yürütme tabanıdır.

`release_oracle.py` model çağırmadan kaydedilmiş çalışma dizinlerini yeniden
incelemek için ayrıca kullanılabilir. Tek başına ürettiği `evidence_only` kaydı
publication yetkisi değildir; imzalı verifier handoff'unun yerine geçmez.

## Gerçek kalan koşullar

- **K29 / Windows:** mevcut ürün shell sandbox'ı Windows için korunmuş actor
  sağlamaz. Windows frozen actor komutu sağlayıcı çağrısından önce açık hata
  verir; verifier bu hedefin aynı kullanıcıdan yazılmış kayıtlarını imzalamaz.
  CI tam platform kümesini zorunlu tuttuğu için bu gerçek platform açığı yayını
  durdurur. Windows kimlik/izolasyon kurulumu bu çalışmada yapılmadı.
- macOS Intel/Apple Silicon ve Linux verifier'ın gerçek frozen kabul koşuları
  henüz ölçülmedi. Kaynak dondurulduktan sonra gerçek ikiliyle koşulmalıdır.
- Ölçümün kapsamı **yayınlanan frozen-runtime arşividir**. DMG/NSIS installer'ı
  kurup uygulama arayüzüyle etkileşim, OS izinleri ve yükseltme kabulü ayrı
  koşullardır. İmzalı rapor ve manifest bu sınırlamayı taşır.
- CI, aynı hash'li aday arşivlerini saklar; başka koşuda yeniden derlenen paket
  aynı ölçülmüş aday sayılmaz. Her platformun paketlenen Kits manifesti ayrıca
  yüklenir ve üçünün aynı geçerli commit'i taşıması gerekir.
