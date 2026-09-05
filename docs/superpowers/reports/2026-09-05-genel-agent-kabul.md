# Genel Agent Güvenilirliği — teslim raporu

Tarih: 5 Eylül 2026. Plan: [genel-agent-guvenilirligi](../plans/2026-09-05-genel-agent-guvenilirligi.md).

## Teslim edilen

| Commit | İş |
|---|---|
| `bdc7336` | MCP içeriğinin agent ve sağlayıcılara kayıpsız taşınması |
| `6398138` | Başarı kriterlerinin gerçek gözlemlere bağlanması |
| `d0caf82` | Final onarımı, kanıtlı checkpoint, araç aileleri sınırı |
| `42881d0` | `evals/agent_runner.py` tip kapısı düzeltmesi |
| `5a8412f` | Sıfır çıkış kodunda gizlenen hata; skill kırpmasının bildirilmesi |
| `636628a` | Duyurulan skill ile enjekte edilen skill'in tek seçime bağlanması |

## Bu turda kapanan kusurlar

- **Kanıtsız kabul.** Adım doğrulaması dosya varlığını ve genel çağrı sayısını kanıt sayıyordu. Kriterler artık `passed / failed / unverified` taşıyor; komut kriteri gerçek `ToolUse` kaydıyla eşleşiyor, `echo git push` gibi taklitler ve `git push --dry-run` reddediliyor.
- **Kopuk onarım.** Final kapısı düştüğünde plan başarısız sonuçla çıkıyordu. Bozulan koşulun adımı ve bağımlıları yeniden açılıyor, kurtarma zarfı harcanarak onarılıyor, final yeniden ölçülüyor. `RetrySafety.NEVER` adımı tekrar çalıştırılmıyor; bağımsız tamamlanan adım korunuyor.
- **Checkpoint'te kanıt kaybı.** Devam kaydı kriter kanıtlarını, artifact parmak izlerini, gerçek araç kayıtlarını ve tüketilmiş zarfları taşıyor. Değişen dosya eski kanıtı geçersiz kılıyor.
- **Checkpoint'te sır ve boyut riski.** Diske yazılan kanıt metni maskeleniyor ve `MAX_CHECKPOINT_OUTPUT_CHARS` ile sınırlanıyor; devam kaydı ham araç çıktısı arşivi değil.
- **Araç kapsamının uygulanmaması.** `allowed_tool_families` yalnız şemada değil gerçek dispatcher'da da uygulanıyor; `OBSERVE_FIRST` kurtarması salt-okunur yürütme durumu alıyor.
- **Sıfır çıkış kodunda gizlenen hata.** Godot bozuk script'te ve çalışma zamanı hatasında `0` dönebiliyor; kapı artık araç adına bağlı dar bir işaret tablosuyla motorun kendi hata satırını yakalıyor.
- **Sessiz skill kırpması.** `read_skill` 6.000 karakterde iz bırakmadan kesiyordu; kırpma ve devam offseti bildiriliyor, araç `offset` alıyor. Sistem promptuna giren blok da düşen bölümleri bildiriyor.
- **Duyuru ile enjeksiyonun ayrışması.** Etkinleşen skill'i duyuran olay ile prompta giren blok farklı seçimlerden besleniyordu; ikisi tek fonksiyondan geçiyor.

## Doğrulama

- Depo kapısı her commit öncesi: Ruff + mypy (279 dosya) + **3027 test** + kilitlenme paketi. Tümü temiz.
- Masaüstü kapısı: **477 arayüz testi**, **74 Rust testi**, cargo fmt/clippy temiz.
- Paket: `Fusion.app` + `Fusion_0.3.0-alpha.8_aarch64.dmg`; kararlı imza `com.fusion.desktop` doğrulandı; bundle smoke `0.3.0a8 · aarch64-apple-darwin`; paketli runtime `runtime-health` → `ok: true`.
- Kimlik: yeni arşiv `41236498…`, önceki kurulu arşiv `a17ba6e0…`. Değişen dosyaların SHA-256'sı paket içinde bugünkü kaynakla eşleşti. Paketin `fusion-runtime.tar.gz` arşivinden çıkarılan modül çalıştırılarak kırpma/devam davranışı doğrudan pakette sınandı.
- Kurulum: `/Applications/Fusion.app` güncellendi; önceki sürüm `/Applications/Fusion-yedek-2026-09-05.app` olarak duruyor. Kurulu paketin imzası doğrulandı.

## Canlı kabul ölçümü (Gemini Web, `gemini_web/main/auto`)

### Kod ve kabuk seti (`evals/suite/starter.yaml`, 24 görev, temiz dizinler)

| Ölçüt | Değer |
|---|---|
| Başarı oranı | %79,2 (19/24) |
| İlk denemede başarı | %79,2 |
| Toplam yeniden deneme | 0 |
| Ortalama model çağrısı | 7,1 |
| Ortalama süre | 48,9 sn |

Düşen beş görevin tamamı okuma-anlama-düzeltme sınıfındandır: `test-ciktisini-okuyup-duzelt`, `traceback-okuyup-duzelt`, `kullanicinin-degisikligini-koru`, `erisilemeyen-kaynagi-uydurma`, `cok-dosyali-modul-kur`. Dosya üretme ve tek adımlı görevlerin tamamı geçti.

### Godot seti (üç koşu, her biri boş dizinde, elle müdahale yok)

| Koşu | Durduğu yer | Ürün |
|---|---|---|
| 1 | Yapı kapısı, adımın çağıramadığı MCP aracına yönlendirdi | Sahne üretilemedi |
| 2 | Son adımda `godot` komutu onaya takıldı (etkileşimsiz oturum) | Açılan, hatasız proje; 180 kare temiz |
| 3 | `player.gd` ile sahne düğüm tipi tutarsız; adım bütçesi doldu | Proje açılıyor, script çalışmıyor |

Üç koşunun hiçbiri tam otonom teslim değildir. Koşu 3'ün ürettiği proje `godot --headless --path . --quit` komutunu `0` çıkış koduyla bitirirken `SCRIPT ERROR: Parse Error` basıyor; bu turda eklenen kapı aynı projeye karşı `ok=False`, kanıt `failed` verdi — yani aynı çıktı artık başarı sayılamıyor.

Koşu 1 ve 2'nin ortaya çıkardığı iki tıkanma `add2c49` ile kapatıldı.

Ölçümün gösterdiği sınır artık araç ya da kanıt katmanı değil, modelin kendi ürettiği iki dosyayı tutarlı tutamamasıdır (sahne düğüm tipi ile script API'sinin uyuşmaması).

## Kalan sınırlamalar

- **Canlı kabul ölçümü yapılmadı.** Kod, MCP, tarayıcı ve Godot görevlerinin temiz dizinlerde gerçek sağlayıcıyla koşturulup provider/çağrı/kabul/artifact/insan-müdahalesi metriklerinin kaydedilmesi bekliyor. Bu yapılmadan "Fusion bu işi tek başına bitirir" denemez.
- **Depoda önceden var olan biçim/tip borcu.** Güncel Ruff, bu turun dışındaki 27 dosyayı yeniden biçimlemek istiyor; bu değişikliklere karıştırılmadı.
- **Notarization yok.** Paket yerel kararlı imzayla üretildi; Apple notarization ortam değişkenleri tanımlı değil.
- **Kanıt maskeleme agresiftir.** Sır deseni eşleşen araç çıktısı checkpoint'te bütünüyle `[gizlendi]` olur; bu, sızma riskine karşı bilinçli bir değiş tokuştur.
